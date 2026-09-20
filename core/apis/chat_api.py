"""
聊天相关 API — 超信 IM 会话列表等接口
"""
import base64
import json
import re
import random
import threading
import time

from core.logger import get_logger
from core.msync_client import MSyncClient, decode_message

logger = get_logger()

# 模块级全局凭证缓存，防止多实例/多线程并发刷新 token
_credentials_lock = threading.Lock()
_credentials_cache = {}
_credentials_ts = 0


class ChatAPI:
    """聊天 API 接口，依赖宿主提供 session、session_manager。"""

    _msync = None  # 类属性，避免 __init__ 未被调用的问题
    _msync_lock = threading.Lock()
    _msync_listener_lock = threading.Lock()
    _msync_message_listeners = {}
    _msync_error_listeners = {}
    _msync_close_listeners = {}

    @staticmethod
    def _api_data(payload):
        """返回 Chaoxing API 的 data/msg 对象，兼容直接返回对象。"""
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data") or payload.get("msg")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _first_value(payload, names):
        if not isinstance(payload, dict):
            return ""
        for name in names:
            value = payload.get(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def get_login_user(self):
        """获取当前 Chaoxing 登录用户信息。"""
        response = self.session.get(
            "https://im.chaoxing.com/apis/getLoginUser",
            params={"crossOrigin": "true", "detail": "1"},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Origin": "https://fe.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://fe.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        print(
            "ChatAPI.get_login_user response:",
            json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        if not isinstance(result, dict) or str(result.get("result")) not in {"1", "True", "true"}:
            raise RuntimeError("获取 Chaoxing 登录用户失败")

        user = self._api_data(result)
        if not user.get("puid"):
            raise RuntimeError("登录用户响应中缺少 puid")
        return user

    def get_user_im_token(self):
        """获取新版 IM Token，必须使用当前登录 Session 的 Cookie。"""
        response = self.session.get(
            "https://learn.chaoxing.com/apis/user/getUserImToken",
            params={"crossOrigin": "true"},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Origin": "https://fe.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://fe.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or str(result.get("result")) not in {"1", "True", "true"}:
            raise RuntimeError("获取 IM Token 失败")
        return result

    def refresh_im_credentials(self):
        """按新版流程获取并缓存登录用户、Easemob 用户名和 Token。"""
        user = self.get_login_user()
        token_result = self.get_user_im_token()
        token_data = self._api_data(token_result)
        token = self._first_value(token_data, ("hxToken", "token", "imToken", "userImToken", "access_token"))
        tuid = self._first_value(token_data, ("uid", "tuid", "imTuid", "username", "userName"))
        if not token or not tuid:
            raise RuntimeError("IM Token 响应中缺少 token 或 tuid")

        credentials = {
            "puid": str(user.get("puid") or ""),
            "fid": str(user.get("fid") or ""),
            "name": str(user.get("name") or ""),
            "tuid": tuid,
            "token": token,
        }
        self.session_manager.course_params.update({
            "im_puid": credentials["puid"],
            "im_fid": credentials["fid"],
            "im_tuid": credentials["tuid"],
            "im_token": credentials["token"],
            "im_user": user,
        })
        return credentials

    @staticmethod
    def _extract_class_chat_map(html: str):
        """从 /webim/me HTML 中提取 classChat 映射。"""
        if not html:
            return {}

        match = re.search(r"var\s+classChat\s*=\s*(\{.*?\})\s*;", html, re.S)
        if not match:
            return {}

        try:
            data = json.loads(match.group(1))
        except Exception:
            logger.debug("ChatAPI._extract_class_chat_map: classChat JSON 解析失败")
            return {}

        return data if isinstance(data, dict) else {}

    @staticmethod
    def _apply_class_chat_metadata(sessions: list, class_chat_map: dict):
        """将 /webim/me 中的群聊班级名补充到会话副标题。"""
        if not isinstance(sessions, list) or not isinstance(class_chat_map, dict) or not class_chat_map:
            return sessions

        enriched = []
        for session in sessions:
            if not isinstance(session, dict):
                enriched.append(session)
                continue

            item = dict(session)
            chat_id = str(item.get("chatId", "") or "")
            class_info = class_chat_map.get(f"chatid{chat_id}")
            if isinstance(class_info, dict):
                classname = str(class_info.get("classname", "") or "").strip()
                if classname:
                    item["subtitle"] = classname
                coursename = str(class_info.get("coursename", "") or "").strip()
                if coursename:
                    item["courseName"] = coursename
            enriched.append(item)

        return enriched

    @staticmethod
    def _normalize_channel_infos(channel_infos):
        """将 Easemob user_channels 响应转换为聊天视图使用的会话字段。"""
        sessions = []
        for channel in channel_infos or []:
            if not isinstance(channel, dict):
                continue
            meta = channel.get("meta") or {}
            try:
                payload = json.loads(meta.get("payload") or "{}")
            except (TypeError, ValueError):
                payload = {}
            ext = payload.get("ext") or {}
            class_info = ext.get("classInfo") or {}
            is_group = channel.get("session_type") == "groupchat"
            peer_id = str(channel.get("session_to") or "")
            if is_group:
                peer_id = str(class_info.get("chatid") or peer_id)
            name = (
                class_info.get("clazzName")
                or class_info.get("coursename")
                or peer_id
            ) if is_group else peer_id
            sessions.append({
                **channel,
                "chatId": peer_id,
                "chatName": str(name),
                "msgId": str(meta.get("id") or ""),
                "updateTime": channel.get("update_unread_msg_time") or meta.get("timestamp") or 0,
                "unreadCount": int(channel.get("unread_num") or 0),
                "isGroup": 1 if is_group else 0,
                "isPrivate": not is_group,
                "class_info": class_info,
            })
        return sessions

    def _get_session_top_list(self, puid):
        """获取消息页置顶会话；请求失败不影响普通会话列表。"""
        try:
            response = self.session.get(
                "https://im.chaoxing.com/webim/apis/message/getSessionTopList",
                params={"crossOrigin": "true", "puid": str(puid)},
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://fe.chaoxing.com",
                    "Referer": "https://fe.chaoxing.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            if isinstance(payload, dict):
                payload = payload.get("data")
            if not isinstance(payload, list):
                return {}
            result = {}
            for item in payload:
                if not isinstance(item, dict) or "sessionId" not in item or "sort" not in item:
                    continue
                try:
                    result[str(item["sessionId"])] = int(item["sort"])
                except (TypeError, ValueError):
                    continue
            return result
        except Exception as e:
            logger.warning(f"ChatAPI._get_session_top_list: 获取失败 - {e}")
            return {}

    @staticmethod
    def _apply_session_top_list(sessions, top_list):
        """按消息页置顶记录排序，未置顶会话保持接口返回顺序。"""
        if not top_list:
            return sessions
        ranked = []
        for index, session in enumerate(sessions):
            item = dict(session)
            session_id = str(item.get("chatId", "") or "")
            item["_topSort"] = top_list.get(session_id)
            ranked.append((item["_topSort"] is not None, item["_topSort"] or 0, -index, item))
        ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
        return [{key: value for key, value in item.items() if key != "_topSort"} for _, _, _, item in ranked]

    def _get_notification_mute_types(self, tuid, token):
        """获取当前用户的会话免打扰配置。"""
        try:
            response = self.session.get(
                f"https://a3-vip6.easemob.com/cx-dev/cxstudy/users/{tuid}/notification/mute/type",
                params={"limit": 100, "_v": int(time.time() * 1000)},
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                    "Cache-Control": "no-cache",
                    "Content-Type": "application/json",
                    "Origin": "https://fe.chaoxing.com",
                    "Pragma": "no-cache",
                    "Referer": "https://fe.chaoxing.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                    "Authorization": f"Bearer {str(token).removeprefix('Bearer ').strip()}",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return []
            payload = response.json()
            mute_types = payload.get("data") if isinstance(payload, dict) else None
            return mute_types if isinstance(mute_types, list) else []
        except Exception as e:
            logger.warning(f"ChatAPI._get_notification_mute_types: 获取失败 - {e}")
            return []

    def _get_encrypt_str_list(self, sessions):
        """为消息页会话获取加密字符串。"""
        chat_list = [
            {"chatId": str(session.get("chatId", "")), "isGroup": bool(session.get("isGroup"))}
            for session in sessions
            if isinstance(session, dict) and str(session.get("chatId", ""))
        ]
        if not chat_list:
            return {}
        try:
            response = self.session.post(
                "https://im.chaoxing.com/webim/message/getEncryptStrList",
                params={"crossOrigin": "true"},
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "application/json",
                    "Origin": "https://fe.chaoxing.com",
                    "Pragma": "no-cache",
                    "Referer": "https://fe.chaoxing.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                },
                data=json.dumps({"chatList": chat_list}, ensure_ascii=False, separators=(",", ":")),
                timeout=15,
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            items = data.get("list") if isinstance(data, dict) else None
            if not isinstance(items, list):
                return {}
            return {
                str(item["chatId"]): str(item["encryptStr"])
                for item in items
                if isinstance(item, dict) and item.get("chatId") is not None and item.get("encryptStr") is not None
            }
        except Exception as e:
            logger.warning(f"ChatAPI._get_encrypt_str_list: 获取失败 - {e}")
            return {}

    def _fetch_group_info(self, room_id: str):
        """获取群聊课程名称和成员数。"""
        try:
            response = self.session.get(
                "https://im.chaoxing.com/webim/huanxin/getGroupInfo",
                params={"crossOrigin": "true", "roomId": str(room_id)},
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://fe.chaoxing.com",
                    "Referer": "https://fe.chaoxing.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                },
                timeout=15,
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            return payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], dict) else {}
        except Exception as e:
            logger.warning(f"ChatAPI._fetch_group_info: 获取失败 room_id={room_id} error={e}")
            return {}

    # ── MSync 实时连接 ──

    @classmethod
    def _dispatch_msync_message(cls, message):
        listeners = []
        with cls._msync_listener_lock:
            listeners = list(cls._msync_message_listeners.values())
        for callback in listeners:
            if not callable(callback):
                continue
            try:
                callback(message)
            except Exception as e:
                logger.warning(f"ChatAPI._dispatch_msync_message: listener failed - {e}")

    @classmethod
    def _dispatch_msync_error(cls, error):
        listeners = []
        with cls._msync_listener_lock:
            listeners = list(cls._msync_error_listeners.values())
        for callback in listeners:
            if not callable(callback):
                continue
            try:
                callback(error)
            except Exception as e:
                logger.warning(f"ChatAPI._dispatch_msync_error: listener failed - {e}")

    @classmethod
    def _dispatch_msync_close(cls, code, message):
        listeners = []
        with cls._msync_listener_lock:
            listeners = list(cls._msync_close_listeners.values())
        for callback in listeners:
            if not callable(callback):
                continue
            try:
                callback(code, message)
            except Exception as e:
                logger.warning(f"ChatAPI._dispatch_msync_close: listener failed - {e}")

    @classmethod
    def _register_msync_listener(cls, store_name: str, callback, listener_key=None):
        if callback is None:
            return
        key = listener_key if listener_key is not None else callback
        with cls._msync_listener_lock:
            getattr(cls, store_name)[key] = callback

    @classmethod
    def _unregister_msync_listener(cls, listener_key):
        if listener_key is None:
            return
        with cls._msync_listener_lock:
            cls._msync_message_listeners.pop(listener_key, None)
            cls._msync_error_listeners.pop(listener_key, None)
            cls._msync_close_listeners.pop(listener_key, None)

    @classmethod
    def _attach_msync_dispatchers(cls):
        if not cls._msync:
            return
        if hasattr(cls._msync, "on_message"):
            cls._msync.on_message = cls._dispatch_msync_message
        if hasattr(cls._msync, "on_error"):
            cls._msync.on_error = cls._dispatch_msync_error
        if hasattr(cls._msync, "on_close"):
            cls._msync.on_close = cls._dispatch_msync_close

    def connect_msync(self, on_message=None, on_error=None, on_close=None, on_authenticated=None, listener_key=None):
        """
        建立 MSync WebSocket 实时连接。

        Returns:
            MSyncClient 实例，失败返回 None
        """
        cls = self.__class__
        cls._register_msync_listener("_msync_message_listeners", on_message, listener_key=listener_key)
        cls._register_msync_listener("_msync_error_listeners", on_error, listener_key=listener_key)
        cls._register_msync_listener("_msync_close_listeners", on_close, listener_key=listener_key)

        with cls._msync_lock:
            if cls._msync and hasattr(cls._msync, "is_running") and cls._msync.is_running():
                cls._attach_msync_dispatchers()
                return cls._msync

            token = self.session_manager.course_params.get("im_token")
            tuid = self.session_manager.course_params.get("im_tuid")

            if not all([tuid, token]):
                creds = self.get_im_credentials()
                if not creds:
                    logger.error(
                        "ChatAPI.connect_msync: 未获取到 IM 凭证 "
                        "tuid_present=%s token_present=%s",
                        bool(tuid),
                        bool(token),
                    )
                    return None
                tuid = creds["tuid"]
                token = creds["token"]

            try:
                # 提取 requests session 的 cookie 供 WebSocket 使用
                cookie_dict = self.session.cookies.get_dict()
                cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
                logger.info(f"ChatAPI.connect_msync: cookies_count={len(cookie_dict)}, keys={list(cookie_dict.keys())}")

                cls._msync = MSyncClient(
                    app_key="cx-dev#cxstudy",
                    domain="easemob.com",
                    platform=3,
                    transport="direct",
                    on_message=cls._dispatch_msync_message,
                    on_error=cls._dispatch_msync_error,
                    on_close=cls._dispatch_msync_close,
                    on_authenticated=on_authenticated,
                    cookies=cookie_str,
                )
                cls._msync.connect(token=token, username=tuid)
                return cls._msync
            except Exception as e:
                logger.exception(f"ChatAPI.connect_msync: 连接失败 - {e}")
                return None

    def disconnect_msync(self):
        """断开 MSync 连接。"""
        cls = self.__class__
        with cls._msync_lock:
            if cls._msync:
                cls._msync.disconnect()
                cls._msync = None

    def is_msync_connected(self) -> bool:
        """MSync 是否已连接。"""
        cls = self.__class__
        return cls._msync is not None and cls._msync.is_connected()

    def get_msync_resource(self) -> str:
        """返回当前 MSync 连接的 resource 标识。"""
        cls = self.__class__
        return str(getattr(cls._msync, "_resource", "") or "")

    def send_message_msync(self, target_user_id: str, content: str):
        """
        通过 MSync 发送实时消息。

        Args:
            target_user_id: 对方用户 ID / 路由 ID
            content: 消息内容

        Returns:
            bool: 是否发送成功
        """
        cls = self.__class__
        if not cls._msync or not cls._msync.is_connected():
            return False
        try:
            cls._msync.send_message(to_user=target_user_id, content=content)
            return True
        except Exception as e:
            print(f"ChatAPI.send_message_msync: 发送失败 - {e}")
            return False

    def request_history_msync(self, target_user_id: str):
        """通过 MSync 请求会话历史。"""
        cls = self.__class__
        if not cls._msync:
            return False
        try:
            return bool(cls._msync.request_history(target_user_id))
        except Exception as e:
            logger.warning(f"ChatAPI.request_history_msync: 请求失败 - {e}")
            return False

    def request_history_summary_msync(self, target_user_ids: list[str]):
        """通过 MSync 请求会话列表的历史汇总，用于未读计数。"""
        cls = self.__class__
        if not cls._msync:
            return False
        try:
            return bool(cls._msync.request_history_summary(target_user_ids))
        except Exception as e:
            logger.warning(f"ChatAPI.request_history_summary_msync: 请求失败 - {e}")
            return False

    def request_conversation_read_msync(self, target_user_id: str, message_id: str | int):
        """通过 MSync 同步会话已读位置。"""
        cls = self.__class__
        if not cls._msync:
            return False
        try:
            return bool(cls._msync.request_conversation_read(target_user_id, message_id))
        except Exception as e:
            logger.warning(f"ChatAPI.request_conversation_read_msync: 请求失败 - {e}")
            return False

    def get_group_members(self, room_id: str, tuid=None, token=None):
        """获取群聊成员列表。"""
        room_id = str(room_id or "")
        if not room_id:
            return []

        params = self._resolve_im_params(tuid=tuid, puid=None, token=token)
        if not params:
            return []

        try:
            url = (
                "https://a3-vip6.easemob.com/cx-dev/cxstudy/"
                f"chatgroups/{room_id}/users"
            )
            headers = {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Origin": "https://fe.chaoxing.com",
                "Referer": "https://fe.chaoxing.com/",
                "Authorization": f"Bearer {str(params['token']).removeprefix('Bearer ').strip()}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            }
            self.session.options(
                url,
                params={"version": "v3", "pagenum": 1, "pagesize": 1000, "_v": int(time.time() * 1000)},
                headers={
                    "Accept": "*/*",
                    "Origin": "https://fe.chaoxing.com",
                    "Referer": "https://fe.chaoxing.com/",
                    "Access-Control-Request-Headers": "authorization,content-type",
                    "Access-Control-Request-Method": "GET",
                    "User-Agent": headers["User-Agent"],
                },
                timeout=15,
            )

            resp = self.session.get(
                url,
                params={"version": "v3", "pagenum": 1, "pagesize": 1000, "_v": int(time.time() * 1000)},
                headers=headers,
                timeout=15,
            )
            logger.info(
                "ChatAPI.get_group_members: status=%s room_id=%s len=%s",
                resp.status_code,
                room_id,
                len(resp.text),
            )
            if resp.status_code != 200:
                logger.warning(f"ChatAPI.get_group_members: HTTP错误 {resp.status_code}, room_id={room_id}")
                return []

            result = resp.json()
            members = result.get("data", [])
            if not isinstance(members, list):
                return []

            normalized = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                member_tuid = str(member.get("member", "") or member.get("tuid", "") or "")
                if not member_tuid:
                    continue
                profile = self.get_im_user_info_by_tuid(member_tuid) or {}
                normalized.append({
                    "person_id": member_tuid,
                    "name": profile.get("name", "未知"),
                    "student_id": "",
                    "avatar_url": profile.get("icon", "") or profile.get("pic", "") or "",
                    "tuid": member_tuid,
                    "puid": str(profile.get("puid", "") or ""),
                })

            return normalized
        except Exception as e:
            logger.exception(f"ChatAPI.get_group_members: 获取失败 - {e}")
            return []

    def _resolve_im_params(self, tuid=None, puid=None, token=None):
        """统一获取 IM 鉴权参数，失败返回 None。"""
        if not all([tuid, puid, token]):
            tuid = tuid or self.session_manager.course_params.get("im_tuid")
            puid = puid or self.session_manager.course_params.get("im_puid")
            token = token or self.session_manager.course_params.get("im_token")

        if all([tuid, puid, token]):
            return {
                "tuid": tuid,
                "puid": puid,
                "token": token,
            }

        creds = self.get_im_credentials()
        if not creds:
            return None

        return {
            "tuid": creds["tuid"],
            "puid": creds["puid"],
            "token": creds["token"],
        }

    # ── 凭证获取 ──

    def get_im_credentials_cached(self):
        """仅从全局缓存读取凭证，不发起任何 HTTP 请求。

        命中返回 dict（与 get_im_credentials 同结构），未命中返回 None。
        用于 UI 主线程的快路径，避免阻塞主线程触发 Windows ghost window。
        """
        global _credentials_ts, _credentials_cache

        with _credentials_lock:
            now = time.time()
            if now - _credentials_ts < 30 and _credentials_cache:
                self.session_manager.course_params.update({
                    "im_tuid": _credentials_cache["tuid"],
                    "im_puid": _credentials_cache["puid"],
                    "im_token": _credentials_cache["token"],
                })
                if _credentials_cache.get("class_chat_map"):
                    self.session_manager.course_params["im_class_chat"] = dict(_credentials_cache["class_chat_map"])
                return dict(_credentials_cache)
        return None

    def get_im_credentials(self):
        """
        从 https://im.chaoxing.com/webim/me 页面提取 IM 凭证
        带全局锁防止并发重复请求导致 token 被刷新。

        Returns:
            dict: {"tuid": ..., "puid": ..., "fid": ..., "token": ...}，失败返回 None
        """
        global _credentials_ts, _credentials_cache

        with _credentials_lock:
            # 如果 30 秒内已获取过且缓存有效，直接返回缓存
            now = time.time()
            if now - _credentials_ts < 30 and _credentials_cache:
                logger.debug("ChatAPI.get_im_credentials: 使用全局缓存凭证")
                # 同时同步到当前 session_manager
                self.session_manager.course_params.update({
                    "im_tuid": _credentials_cache["tuid"],
                    "im_puid": _credentials_cache["puid"],
                    "im_token": _credentials_cache["token"],
                })
                if _credentials_cache.get("class_chat_map"):
                    self.session_manager.course_params["im_class_chat"] = dict(_credentials_cache["class_chat_map"])
                return dict(_credentials_cache)

        # 新版前端先获取登录用户，再获取 Easemob IM Token。
        try:
            credentials = self.refresh_im_credentials()
            with _credentials_lock:
                _credentials_cache = dict(credentials)
                _credentials_cache["class_chat_map"] = {}
                _credentials_ts = time.time()
            logger.info(
                "ChatAPI.get_im_credentials: 使用新版接口成功 tuid=%s, puid=%s",
                credentials["tuid"],
                credentials["puid"],
            )
            return credentials
        except Exception as e:
            logger.info("ChatAPI.get_im_credentials: 新版接口不可用，回退旧版凭证流程: %s", e)
            logger.error("ChatAPI.get_im_credentials: 新版凭证接口失败: %s", e)

        # 锁外执行 HTTP 请求（避免长时间持有锁）
        try:
            url = "https://im.chaoxing.com/webim/me"

            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://im.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            }

            resp = self.session.get(url, headers=headers, timeout=15)

            logger.info(f"ChatAPI.get_im_credentials: status={resp.status_code}, url={resp.url}, len={len(resp.text)}")

            if resp.status_code != 200:
                logger.error("ChatAPI.get_im_credentials: 旧版凭证页面 HTTP 状态异常: %s", resp.status_code)
                return None

            html = resp.text

            # 检查是否被重定向到登录页
            if "login" in resp.url.lower() or "passport" in resp.url.lower():
                logger.warning(f"ChatAPI.get_im_credentials: 被重定向到登录页 {resp.url}")
                logger.error("ChatAPI.get_im_credentials: 旧版凭证页面被重定向到登录页")
                return None

            # 提取凭证：支持 HTML <span id="myTuid">格式 和 JS var myTuid= 格式
            patterns = {
                "tuid": [
                    r'<span[^>]*id="myTuid"[^>]*>(\d+)</span>',
                    r'(?:var|let|const)\s+myTuid\s*=\s*["\']?(\d+)["\']?\s*;?',
                ],
                "puid": [
                    r'<span[^>]*id="myPuid"[^>]*>(\d+)</span>',
                    r'(?:var|let|const)\s+myPuid\s*=\s*["\']?(\d+)["\']?\s*;?',
                ],
                "fid": [
                    r'<span[^>]*id="myFid"[^>]*>(\d+)</span>',
                    r'(?:var|let|const)\s+myFid\s*=\s*["\']?(\d+)["\']?\s*;?',
                ],
                "token": [
                    r'<span[^>]*id="myToken"[^>]*>([^<]+)</span>',
                    r'(?:var|let|const)\s+myToken\s*=\s*["\']([^"\']+)["\']\s*;?',
                ],
            }

            creds = {}
            for key, pats in patterns.items():
                for pattern in pats:
                    match = re.search(pattern, html)
                    if match:
                        creds[key] = match.group(1)
                        break

            logger.info(f"ChatAPI.get_im_credentials: 提取到字段={list(creds.keys())}")

            # 打印 HTML 中包含 myTuid/myPuid/myToken 的行用于调试
            for line in html.split("\n"):
                stripped = line.strip()
                if any(k in stripped for k in ["myTuid", "myPuid", "myToken", "myFid"]):
                    logger.debug(f"  JS变量行: {stripped[:200]}")

            # 缺少关键字段则返回 None
            if "tuid" not in creds or "puid" not in creds or "token" not in creds:
                logger.warning(f"ChatAPI.get_im_credentials: 缺少关键字段 tuid={creds.get('tuid')}, puid={creds.get('puid')}, token={creds.get('token')}")
                logger.error(
                    "ChatAPI.get_im_credentials: 旧版凭证字段缺失 "
                    "tuid_present=%s puid_present=%s token_present=%s",
                    bool(creds.get("tuid")),
                    bool(creds.get("puid")),
                    bool(creds.get("token")),
                )
                logger.debug(f"  HTML前500字: {html[:500]}")
                return None

            class_chat_map = self._extract_class_chat_map(html)

            # 缓存到全局和 session_manager
            with _credentials_lock:
                _credentials_cache = {
                    "tuid": creds["tuid"],
                    "puid": creds["puid"],
                    "fid": creds.get("fid"),
                    "token": creds["token"],
                    "class_chat_map": class_chat_map,
                }
                _credentials_ts = now

            self.session_manager.course_params.update({
                "im_tuid": creds["tuid"],
                "im_puid": creds["puid"],
                "im_token": creds["token"],
                "im_class_chat": class_chat_map,
            })

            logger.info(f"ChatAPI.get_im_credentials: 成功 tuid={creds['tuid']}, puid={creds['puid']}")
            return creds

        except Exception as e:
            logger.exception(f"ChatAPI.get_im_credentials: 获取失败 - {e}")
            return None

    # ── 发送消息 ──

    def _fetch_im_user_info(self, target_tuid: str, puid: str, token: str):
        try:
            url = "https://im.chaoxing.com/webim/user/getUserInfoByTuid"
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Origin": "https://fe.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://fe.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            }
            params = {"crossOrigin": "true", "tuid": target_tuid}
            resp = self.session.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                return {}

            result = resp.json()
            if isinstance(result, dict):
                info = result.get("data") if isinstance(result.get("data"), dict) else result
            else:
                info = {}
            if not isinstance(info, dict):
                return {}
        except Exception as e:
            logger.warning(f"ChatAPI._fetch_im_user_info: 获取失败 - {e}")
            return {}

        return {
            "name": info.get("name") or info.get("userName") or info.get("nickName") or "",
            "icon": info.get("icon") or info.get("pic") or info.get("picUrl") or "",
        }

    def _get_im_profile(self, tuid: str, puid: str, token: str):
        """获取当前 IM 用户资料，至少包含 name/icon。"""
        cached = self.session_manager.course_params.get("im_my_info")
        if isinstance(cached, dict) and cached.get("name"):
            return cached

        profile = self._fetch_im_user_info(tuid, puid, token)
        if profile.get("name") or profile.get("icon"):
            self.session_manager.course_params["im_my_info"] = profile
        return profile

    def get_im_user_info_by_tuid(self, target_tuid: str, puid=None, token=None):
        """按 tuid 获取任意 IM 用户资料，结果会缓存在当前会话。"""
        target_tuid = str(target_tuid or "").strip()
        if not target_tuid:
            return {}

        params = self._resolve_im_params(tuid=None, puid=puid, token=token)
        if not params:
            return {}

        course_params = self.session_manager.course_params
        cache = course_params.setdefault("im_user_info_cache", {})
        cached = cache.get(target_tuid)
        if isinstance(cached, dict) and (cached.get("name") or cached.get("icon")):
            return cached

        profile = self._fetch_im_user_info(target_tuid, params["puid"], params["token"])
        if profile.get("name") or profile.get("icon"):
            cache[target_tuid] = profile
        return profile

    def _build_hx_msg_id(self) -> str:
        """构造浏览器风格的纯数字 hxMsgId。"""
        return str(time.time_ns() + random.randint(0, 9999))

    def send_message(
        self,
        target_user_id: str,
        content: str,
        msg_type: int = 1,
        target_name: str = "",
        history_chat_id: str = "",
    ):
        """
        发送消息到指定会话。
        仅在 MSync WebSocket 可用时执行真实发送；历史接口只用于保存消息记录。

        Args:
            target_user_id: 实时发送目标（私聊通常为对方用户 ID）
            content: 消息内容
            msg_type: 消息类型，1=文本
            history_chat_id: 历史归档使用的会话 ID；为空时回退到 target_user_id

        Returns:
            dict: {"status": "success"/"fail", "msg": ...}
        """
        if not self.is_msync_connected():
            return {"status": "fail", "msg": "实时消息连接未建立"}

        try:
            ok = self.send_message_msync(target_user_id, content)
            if not ok:
                return {"status": "fail", "msg": "实时消息发送失败"}

            history_result = self._add_message_history(
                history_chat_id or target_user_id,
                content,
                msg_type,
                target_name=target_name,
            )
            if history_result.get("status") != "success":
                logger.warning(
                    "ChatAPI.send_message: 实时发送成功，但保存历史失败 %s",
                    history_result,
                )
            return {"status": "success", "msg": "发送成功"}
        except Exception as e:
            logger.warning(f"ChatAPI.send_message: MSync 发送失败 - {e}")
            return {"status": "fail", "msg": f"实时消息发送失败: {e}"}

    def _add_message_history(self, target_chat_id: str, content: str, msg_type: int = 1, target_name: str = ""):
        """调用 addMessage API 保存消息历史。"""
        params = self._resolve_im_params()
        if not params:
            return {"status": "fail", "msg": "无法获取 IM 凭证"}

        tuid = params["tuid"]
        puid = params["puid"]
        token = params["token"]

        my_name = ""
        my_icon = ""
        my_info = self._get_im_profile(tuid, puid, token)
        if my_info:
            my_name = my_info.get("name", "")
            my_icon = my_info.get("icon", "")

        try:
            url = "https://im.chaoxing.com/webim/message/history/addMessage"

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://im.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://im.chaoxing.com/webim/me",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }

            import time
            msg_id = f"{tuid}+{target_chat_id}"
            hx_msg_id = self._build_hx_msg_id()

            data = {
                "msgType": msg_type,
                "content": content,
                "msgStatus": 1,
                "extType": 0,
                "isExt": 1,
                "msgId": msg_id,
                "hxMsgId": hx_msg_id,
                "tuid": tuid,
                "name": my_name,
                "icon": my_icon,
                "chatManId": target_chat_id,
                "chatManName": target_name or "",
            }

            resp = self.session.post(url, headers=headers, data=data, timeout=15)
            logger.info(f"ChatAPI._add_message_history: status={resp.status_code}")

            if resp.status_code != 200:
                return {"status": "fail", "msg": f"HTTP {resp.status_code}"}

            return resp.json()

        except Exception as e:
            logger.exception(f"ChatAPI._add_message_history: 失败 - {e}")
            return {"status": "fail", "msg": str(e)}

    # ── 会话列表 ──

    def get_history_messages(self, history_key: str, limit: int = 200, tuid=None, puid=None, token=None, is_group=False):
        """
        获取指定会话的历史消息。

        Args:
            history_key: 浏览器消息列表中的 msgId；无 msgId 时可回退到 chatId
            limit: 拉取条数

        Returns:
            list[dict]: 历史消息列表，失败返回空列表
        """
        if not history_key:
            return []

        try:
            params = self._resolve_im_params(tuid=tuid, puid=puid, token=token)
            if params and str(history_key).isdigit():
                queue_domain = "conference.easemob.com" if is_group else "easemob.com"
                queue = f"{history_key}@{queue_domain}"
                url = (
                    "https://a3-vip6.easemob.com/cx-dev/cxstudy/"
                    f"users/{params['tuid']}/messageroaming"
                )
                browser_headers = {
                    "Accept": "*/*",
                    "Origin": "https://fe.chaoxing.com",
                    "Referer": "https://fe.chaoxing.com/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                }
                try:
                    self.session.options(
                        url,
                        headers={
                            **browser_headers,
                            "Access-Control-Request-Headers": "authorization,content-type",
                            "Access-Control-Request-Method": "POST",
                        },
                        timeout=15,
                    )
                except Exception as error:
                    logger.warning(f"ChatAPI.get_history_messages: roaming 预检失败 error={error}")

                if not is_group:
                    try:
                        clear_response = self.session.post(
                            "https://specie.chaoxing.com/apis/message/clearNoRead",
                            params={"crossOrigin": "true", "msgId": str(history_key)},
                            headers={
                                **browser_headers,
                                "Accept": "application/json, text/plain, */*",
                                "Content-Type": "application/x-www-form-urlencoded",
                            },
                            timeout=15,
                        )
                        logger.info(
                            "ChatAPI.get_history_messages: clearNoRead status=%s, msg_id=%s",
                            clear_response.status_code,
                            history_key,
                        )
                    except Exception as error:
                        logger.warning(f"ChatAPI.get_history_messages: 清除未读失败 error={error}")

                headers = {
                    "Accept": "*/*",
                    "Content-Type": "application/json",
                    "Origin": "https://fe.chaoxing.com",
                    "Referer": "https://fe.chaoxing.com/",
                    "Authorization": f"Bearer {str(params['token']).removeprefix('Bearer ').strip()}",
                    "User-Agent": browser_headers["User-Agent"],
                }
                body = {
                    "queue": queue,
                    "start": -1,
                    "pull_number": min(int(limit or 20), 20),
                    "is_positive": False,
                    "msgType": "",
                    "end": -1,
                    "startTime": None,
                    "endTime": None,
                    "userId": None,
                }
                response = self.session.post(
                    url,
                    headers=headers,
                    data=json.dumps(body, separators=(",", ":")),
                    timeout=15,
                )
                if response.status_code != 200:
                    return []
                result = response.json()
                result_data = result.get("data") if isinstance(result, dict) else None
                raw_messages = result_data.get("msgs") if isinstance(result_data, dict) else None
                if not isinstance(raw_messages, list):
                    raw_messages = None
                if raw_messages is None:
                    raw_messages = []
                else:
                    decoder = MSyncClient(app_key="cx-dev#cxstudy", domain="easemob.com")
                    decoder._username = str(params["tuid"])
                    messages = []
                    for item in raw_messages:
                        if not isinstance(item, dict):
                            continue
                        encoded = item.get("msg")
                        if not encoded:
                            continue
                        try:
                            decoded = decode_message(base64.b64decode(encoded))
                            messages.extend(decoder._extract_batch_messages(decoded))
                        except Exception as error:
                            logger.warning(f"ChatAPI.get_history_messages: protobuf 解码失败 error={error}")
                    return messages

            url = "https://im.chaoxing.com/webim/message/history/getHistoryByMsgId"

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://im.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://im.chaoxing.com/webim/me",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }

            data = {"msgId": history_key}
            if "+" not in history_key:
                params = self._resolve_im_params(tuid=tuid, puid=puid, token=token)
                if not params:
                    return []
                data = {
                    "tuid": params["tuid"],
                    "puid": params["puid"],
                    "token": params["token"],
                    "chatId": history_key,
                    "limit": str(limit),
                }

            resp = self.session.post(url, headers=headers, data=data, timeout=15)
            logger.info(f"ChatAPI.get_history_messages: status={resp.status_code}, history_key={history_key}, len={len(resp.text)}")

            if resp.status_code != 200:
                logger.warning(f"ChatAPI.get_history_messages: HTTP错误 {resp.status_code}, history_key={history_key}")
                return []

            result = resp.json()
            raw_messages = result.get("data", [])
            messages = raw_messages if isinstance(raw_messages, list) else []
            logger.info(
                "ChatAPI.get_history_messages: status=%s, chat_id=%s, data_count=%s",
                result.get("status"),
                history_key,
                len(messages),
            )

            if result.get("status") != "success":
                logger.warning(f"ChatAPI.get_history_messages: 响应异常 {result.get('msg', '')}, 完整={str(result)[:300]}")
                return []

            return messages

        except Exception as e:
            logger.exception(f"ChatAPI.get_history_messages: 获取失败 - {e}")
            return []

    def get_message_list(self, tuid=None, puid=None, token=None):
        """
        获取 IM 会话列表

        Args:
            tuid: IM 用户 ID（可选，自动从缓存/凭证获取）
            puid: 超星用户 ID（可选，自动从缓存/凭证获取）
            token: IM token（可选，自动从缓存/凭证获取）

        Returns:
            list[dict]: 会话列表，每项含 chatId/chatName/avatar_url/updateTime/isGroup/isPrivate 等
                        失败返回空列表
        """
        params = self._resolve_im_params(tuid=tuid, puid=puid, token=token)
        if not params:
            return []

        try:
            url = (
                "https://a3-vip6.easemob.com/cx-dev/cxstudy/sdk/"
                f"user/{params['tuid']}/user_channels/list"
            )
            headers = {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "Origin": "https://fe.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://fe.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
                "Authorization": f"Bearer {str(params['token']).removeprefix('Bearer ').strip()}",
            }
            query = {
                "limit": 50,
                "cursor": "",
                "need_mark": "true",
                "needEmptySession": "true",
                "_v": int(time.time() * 1000),
            }

            resp = self.session.get(url, headers=headers, params=query, timeout=15)
            logger.info(f"ChatAPI.get_message_list: status={resp.status_code}, len={len(resp.text)}")

            if resp.status_code != 200:
                logger.warning(f"ChatAPI.get_message_list: HTTP错误 {resp.status_code}")
                return []

            result = resp.json()
            payload = result.get("data") if isinstance(result, dict) else None
            if isinstance(payload, dict):
                sessions = payload.get("channel_infos") or payload.get("channels")
            elif isinstance(payload, list):
                sessions = payload
            else:
                sessions = result.get("channels") if isinstance(result, dict) else None
            if not isinstance(sessions, list):
                logger.warning(f"ChatAPI.get_message_list: 响应缺少 channels, 完整={str(result)[:300]}")
                return []

            if sessions and isinstance(sessions[0], dict) and "channel_id" in sessions[0]:
                sessions = self._normalize_channel_infos(sessions)
                for session in sessions:
                    if session.get("isGroup") != 1:
                        peer_id = str(session.get("chatId") or "")
                        profile = self.get_im_user_info_by_tuid(peer_id)
                        if profile.get("name"):
                            session["chatName"] = profile["name"]
                        avatar_url = str(profile.get("icon") or profile.get("pic") or "").strip()
                        if avatar_url:
                            session["avatar_url"] = avatar_url
                        continue
                    group_info = self._fetch_group_info(session.get("chatId"))
                    if group_info.get("name"):
                        session["chatName"] = group_info["name"]
                    if group_info.get("members_count") is not None:
                        session["members_count"] = group_info["members_count"]
            sessions = self._apply_session_top_list(
                sessions,
                self._get_session_top_list(params["puid"]),
            )
            mute_types = self._get_notification_mute_types(params["tuid"], params["token"])
            self.session_manager.course_params["im_notification_mute_types"] = mute_types
            encrypt_strings = self._get_encrypt_str_list(sessions)
            for session in sessions:
                encrypt_str = encrypt_strings.get(str(session.get("chatId", "")))
                if encrypt_str:
                    session["encryptStr"] = encrypt_str
            self.session_manager.course_params["im_encrypt_str_map"] = encrypt_strings
            class_chat_map = self.session_manager.course_params.get("im_class_chat")
            return self._apply_class_chat_metadata(sessions, class_chat_map)

        except Exception as e:
            logger.exception(f"ChatAPI.get_message_list: 获取失败 - {e}")
            return []

    def refresh_msync_info(self):
        """请求 SockJS ws/info 握手信息。"""
        try:
            url = "https://im-api-vip6-v2.easecdn.com/ws/info"
            headers = {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Origin": "https://im.chaoxing.com",
                "Pragma": "no-cache",
                "Priority": "u=1, i",
                "Referer": "https://im.chaoxing.com/",
                "Sec-CH-UA": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"macOS"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            }
            resp = self.session.get(
                url,
                params={"t": str(int(time.time() * 1000))},
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("ChatAPI.refresh_msync_info: status=%s", resp.status_code)
                return {}
            result = resp.json()
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.warning(f"ChatAPI.refresh_msync_info: 请求失败 - {e}")
            return {}

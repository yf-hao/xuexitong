"""
聊天相关 API — 超信 IM 会话列表等接口
"""
import json
import re
import random
import threading
import time

from core.logger import get_logger
from core.msync_client import MSyncClient

logger = get_logger()

# 模块级全局凭证缓存，防止多实例/多线程并发刷新 token
_credentials_lock = threading.Lock()
_credentials_cache = {}
_credentials_ts = 0


class ChatAPI:
    """聊天 API 接口，依赖宿主提供 session、session_manager。"""

    _msync = None  # 类属性，避免 __init__ 未被调用的问题

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

    # ── MSync 实时连接 ──

    def connect_msync(self, on_message=None, on_error=None, on_close=None):
        """
        建立 MSync WebSocket 实时连接。

        Returns:
            MSyncClient 实例，失败返回 None
        """
        if self._msync and hasattr(self._msync, "is_running") and self._msync.is_running():
            if on_message is not None:
                self._msync.on_message = on_message
            if on_error is not None:
                self._msync.on_error = on_error
            if on_close is not None:
                self._msync.on_close = on_close
            return self._msync

        token = self.session_manager.course_params.get("im_token")
        tuid = self.session_manager.course_params.get("im_tuid")

        if not all([tuid, token]):
            creds = self.get_im_credentials()
            if not creds:
                return None
            tuid = creds["tuid"]
            token = creds["token"]

        try:
            # 提取 requests session 的 cookie 供 WebSocket 使用
            cookie_dict = self.session.cookies.get_dict()
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
            logger.info(f"ChatAPI.connect_msync: cookies_count={len(cookie_dict)}, keys={list(cookie_dict.keys())}")

            self._msync = MSyncClient(
                app_key="cx-dev#cxstudy",
                domain="easemob.com",
                platform=3,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                cookies=cookie_str,
            )
            self._msync.connect(token=token, username=tuid)
            return self._msync
        except Exception as e:
            logger.exception(f"ChatAPI.connect_msync: 连接失败 - {e}")
            return None

    def disconnect_msync(self):
        """断开 MSync 连接。"""
        if self._msync:
            self._msync.disconnect()
            self._msync = None

    def is_msync_connected(self) -> bool:
        """MSync 是否已连接。"""
        return self._msync is not None and self._msync.is_connected()

    def send_message_msync(self, target_user_id: str, content: str):
        """
        通过 MSync 发送实时消息。

        Args:
            target_user_id: 对方用户 ID / 路由 ID
            content: 消息内容

        Returns:
            bool: 是否发送成功
        """
        if not self._msync or not self._msync.is_connected():
            return False
        try:
            self._msync.send_message(to_user=target_user_id, content=content)
            return True
        except Exception as e:
            print(f"ChatAPI.send_message_msync: 发送失败 - {e}")
            return False

    def request_history_msync(self, target_user_id: str):
        """通过 MSync 请求会话历史。"""
        if not self._msync:
            return False
        try:
            return bool(self._msync.request_history(target_user_id))
        except Exception as e:
            logger.warning(f"ChatAPI.request_history_msync: 请求失败 - {e}")
            return False

    def request_history_summary_msync(self, target_user_ids: list[str]):
        """通过 MSync 请求会话列表的历史汇总，用于未读计数。"""
        if not self._msync:
            return False
        try:
            return bool(self._msync.request_history_summary(target_user_ids))
        except Exception as e:
            logger.warning(f"ChatAPI.request_history_summary_msync: 请求失败 - {e}")
            return False

    def request_conversation_read_msync(self, target_user_id: str, message_id: str | int):
        """通过 MSync 同步会话已读位置。"""
        if not self._msync:
            return False
        try:
            return bool(self._msync.request_conversation_read(target_user_id, message_id))
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
            url = "https://im.chaoxing.com/webim/group/getGroupInfoByCount"
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
            data = {
                "roomId": room_id,
                "token": params["token"],
                "tuid": params["tuid"],
            }

            resp = self.session.post(url, headers=headers, data=data, timeout=15)
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
            members = result.get("members", [])
            if not isinstance(members, list):
                return []

            normalized = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                normalized.append({
                    "person_id": str(member.get("tuid", "") or ""),
                    "name": member.get("name", "未知"),
                    "student_id": str(member.get("puid", "") or ""),
                    "avatar_url": member.get("pic", "") or "",
                    "tuid": str(member.get("tuid", "") or ""),
                    "puid": str(member.get("puid", "") or ""),
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
                return None

            html = resp.text

            # 检查是否被重定向到登录页
            if "login" in resp.url.lower() or "passport" in resp.url.lower():
                logger.warning(f"ChatAPI.get_im_credentials: 被重定向到登录页 {resp.url}")
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

    def _get_im_profile(self, tuid: str, puid: str, token: str):
        """获取当前 IM 用户资料，至少包含 name/icon。"""
        cached = self.session_manager.course_params.get("im_my_info")
        if isinstance(cached, dict) and cached.get("name"):
            return cached

        try:
            url = "https://im.chaoxing.com/webim/user/getUserInfoByTuid"
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://im.chaoxing.com",
                "Referer": "https://im.chaoxing.com/webim/me",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
            }
            data = {
                "tuid": tuid,
                "puid": puid,
                "token": token,
            }
            resp = self.session.post(url, headers=headers, data=data, timeout=15)
            if resp.status_code != 200:
                return {}

            result = resp.json()
            info = result.get("data", result) if isinstance(result, dict) else {}
            if not isinstance(info, dict):
                return {}

            profile = {
                "name": info.get("name") or info.get("userName") or info.get("nickName") or "",
                "icon": info.get("icon") or info.get("pic") or info.get("picUrl") or "",
            }
            if profile["name"] or profile["icon"]:
                self.session_manager.course_params["im_my_info"] = profile
            return profile
        except Exception as e:
            logger.warning(f"ChatAPI._get_im_profile: 获取失败 - {e}")
            return {}

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

    def get_history_messages(self, history_key: str, limit: int = 200, tuid=None, puid=None, token=None):
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
            list[dict]: 会话列表，每项含 chatId/chatName/chatIco/updateTime/isGroup/isPrivate 等
                        失败返回空列表
        """
        params = self._resolve_im_params(tuid=tuid, puid=puid, token=token)
        if not params:
            return []

        try:
            url = "https://im.chaoxing.com/webim/message/list/getMessageList"

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

            data = {
                "tuid": params["tuid"],
                "puid": params["puid"],
                "token": params["token"],
            }

            resp = self.session.post(url, headers=headers, data=data, timeout=15)
            logger.info(f"ChatAPI.get_message_list: status={resp.status_code}, len={len(resp.text)}")

            if resp.status_code != 200:
                logger.warning(f"ChatAPI.get_message_list: HTTP错误 {resp.status_code}")
                return []

            result = resp.json()
            logger.info(f"ChatAPI.get_message_list: status={result.get('status')}, data_count={len(result.get('data', []))}")

            if result.get("status") != "success" or "data" not in result:
                logger.warning(f"ChatAPI.get_message_list: 响应异常 {result.get('msg', '')}, 完整={str(result)[:300]}")
                return []

            class_chat_map = self.session_manager.course_params.get("im_class_chat")
            return self._apply_class_chat_metadata(result["data"], class_chat_map)

        except Exception as e:
            logger.exception(f"ChatAPI.get_message_list: 获取失败 - {e}")
            return []

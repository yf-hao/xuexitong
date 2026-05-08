"""
MSync over SockJS 客户端 — 环信 IM 实时消息收发

协议栈:
  SockJS WebSocket → wss://im-api-vip6-v2.easecdn.com/ws/{server}/{session}/websocket
  数据帧格式: a["base64 protobuf"]
  MSync 消息: Protobuf 编码 (手动实现, 无需 protoc)

依赖: websocket-client
"""
import base64
import json
import random
import string
import struct
import threading
import time
import urllib.parse
import urllib.request

import websocket

from core.logger import get_logger

logger = get_logger()


# ── Protobuf 编码辅助 ──────────────────────────────────

class ProtoBufWriter:
    """极简 Protobuf 编码器, 只支持 varint / length-delimited / fixed64."""

    def __init__(self):
        self._buf = bytearray()

    def _tag(self, field: int, wire: int):
        self.varint((field << 3) | wire)

    def varint(self, val: int):
        """编码无符号 varint."""
        while val >= 0x80:
            self._buf.append((val & 0x7f) | 0x80)
            val >>= 7
        self._buf.append(val)

    def svarint(self, val: int):
        """编码有符号 varint (zigzag)."""
        self.varint((val << 1) ^ (val >> 63))

    def string(self, field: int, text: str):
        """field 2 (length-delimited)."""
        b = text.encode("utf-8")
        self._tag(field, 2)
        self.varint(len(b))
        self._buf.extend(b)

    def bytes_field(self, field: int, data: bytes):
        self._tag(field, 2)
        self.varint(len(data))
        self._buf.extend(data)

    def uint32(self, field: int, val: int):
        """field 0 (varint)."""
        self._tag(field, 0)
        self.varint(val)

    def uint64(self, field: int, val: int):
        self._tag(field, 0)
        self.varint(val)

    def fixed64(self, field: int, val: int):
        """field 1 (64-bit fixed)."""
        self._tag(field, 1)
        self._buf.extend(struct.pack("<Q", val))

    def fixed32(self, field: int, val: int):
        """field 5 (32-bit fixed)."""
        self._tag(field, 5)
        self._buf.extend(struct.pack("<I", val))

    def embedded(self, field: int, sub: "ProtoBufWriter"):
        """嵌套消息 (length-delimited)."""
        self._tag(field, 2)
        b = sub.bytes()
        self.varint(len(b))
        self._buf.extend(b)

    def bytes(self) -> bytes:
        return bytes(self._buf)


# ── Protobuf 解码辅助 ──────────────────────────────────

def decode_varint(data: bytes, offset: int):
    """解码 varint, 返回 (value, new_offset)."""
    val = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        val |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, offset


def _merge_field(result: dict, field: int, value):
    """处理 protobuf 重复字段。"""
    if field not in result:
        result[field] = value
    elif isinstance(result[field], list):
        result[field].append(value)
    else:
        result[field] = [result[field], value]


def _is_printable_text(value: str) -> bool:
    return all(ch.isprintable() or ch in "\t\r\n" for ch in value)


def _decode_message_internal(data: bytes, strict: bool):
    result = {}
    offset = 0
    end = len(data)

    while offset < end:
        tag, offset = decode_varint(data, offset)
        field = tag >> 3
        wire = tag & 0x07
        if field <= 0:
            raise ValueError("invalid field number")

        if wire == 0:
            val, offset = decode_varint(data, offset)
            _merge_field(result, field, val)
        elif wire == 1:
            if offset + 8 > end:
                raise ValueError("truncated fixed64")
            val = struct.unpack("<Q", data[offset:offset + 8])[0]
            offset += 8
            _merge_field(result, field, val)
        elif wire == 2:
            length, offset = decode_varint(data, offset)
            if offset + length > end:
                raise ValueError("truncated length-delimited")
            raw = data[offset:offset + length]
            offset += length

            try:
                nested = _decode_message_internal(raw, strict=True)
            except Exception:
                nested = None

            if nested:
                _merge_field(result, field, nested)
                continue

            try:
                text = raw.decode("utf-8")
                if _is_printable_text(text):
                    _merge_field(result, field, text)
                else:
                    _merge_field(result, field, raw)
            except UnicodeDecodeError:
                _merge_field(result, field, raw)
        elif wire == 5:
            if offset + 4 > end:
                raise ValueError("truncated fixed32")
            val = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4
            _merge_field(result, field, val)
        else:
            raise ValueError(f"unsupported wire type {wire}")

    if strict and offset != end:
        raise ValueError("decode did not consume full message")
    return result


def decode_message(data: bytes):
    """解码 MSync 消息, 返回 dict."""
    return _decode_message_internal(data, strict=False)


# ── MSync 消息构造 ─────────────────────────────────────

def build_jid(app_key: str, username: str, domain: str, resource: str) -> ProtoBufWriter:
    """构造 JID 消息."""
    w = ProtoBufWriter()
    w.string(1, app_key)
    w.string(2, username)
    w.string(3, domain)
    w.string(4, resource)
    return w


def build_login_message(
    app_key: str,
    username: str,
    domain: str,
    resource: str,
    token: str,
    platform: int = 3,
    resource_ts: int = None,
) -> bytes:
    """
    构造 MSync 登录消息.

    结构 (根据抓包分析):
      field 1: version (varint 0)
      field 2: JID
      field 3: auth token (string, "$t$" + 环信token)
      field 8: platform (varint)
      field 9: Provision
        field 1: encryptType (varint 16)
        field 2: version (string "3.0.0")
        field 5: 0
        field 6: 0
        field 9: timestamp (string, 与 resource 中的时间戳一致)
        field 12: platform_name (string "webim")
        field 13: resource (string)
        field 14: token (string)
      field 10: 0
      field 11: 0
    """
    root = ProtoBufWriter()
    root.uint32(1, 0)  # version

    jid = build_jid(app_key, username, domain, resource)
    root.embedded(2, jid)

    auth_token = f"$t${token}"
    root.string(3, auth_token)
    root.uint32(8, platform)

    # Provision: timestamp 与 resource 中的时间戳保持一致
    ts = resource_ts if resource_ts else int(time.time() * 1000)
    prov = ProtoBufWriter()
    prov.uint32(1, 16)  # encryptType
    prov.string(2, "3.0.0")
    prov.uint32(5, 0)
    prov.uint32(6, 0)
    prov.string(9, str(ts))
    prov.string(12, "webim")
    prov.string(13, resource)
    prov.string(14, auth_token)
    root.embedded(9, prov)

    root.uint32(10, 0)
    root.uint32(11, 0)

    return root.bytes()


def build_send_message(
    app_key: str,
    from_user: str,
    to_user: str,
    domain: str,
    resource: str,
    content: str,
    msg_type: int = 0,
) -> bytes:
    """
    构造 MSync 发送消息.

    结构 (根据抓包分析):
      field 1: version (varint 0)
      field 2: from JID
      field 8: 0
      field 9: commSyncUL
        field 1: Meta
          field 1: timestamp
          field 2: from JID
          field 3: to JID
          field 5: msgType (varint 1)
          field 6: MessageBody
            field 1: msgType (varint 1)
            field 2: from (len-delimited, field 2 = username)
            field 3: to (len-delimited, field 2 = username)
            field 4: Content
              field 1: msgType (varint 0)
              field 2: text (string)
      field 11: 0
    """
    root = ProtoBufWriter()
    root.uint32(1, 0)

    from_jid = build_jid(app_key, from_user, domain, resource)
    root.embedded(2, from_jid)
    root.uint32(8, 0)

    # field 9 = commSyncUL → 嵌套一层 field 1 = Meta
    meta = ProtoBufWriter()
    meta.uint64(1, int(time.time() * 1000))

    fj = build_jid(app_key, from_user, domain, resource)
    meta.embedded(2, fj)

    tj = ProtoBufWriter()
    tj.string(1, app_key)
    tj.string(2, to_user)
    tj.string(3, domain)
    meta.embedded(3, tj)

    meta.uint32(5, 1)

    # MessageBody
    body = ProtoBufWriter()
    body.uint32(1, 1)

    from_inner = ProtoBufWriter()
    from_inner.string(2, from_user)
    body.embedded(2, from_inner)

    to_inner = ProtoBufWriter()
    to_inner.string(2, to_user)
    body.embedded(3, to_inner)

    # Content
    content_msg = ProtoBufWriter()
    content_msg.uint32(1, msg_type)
    content_msg.string(2, content)
    body.embedded(4, content_msg)

    meta.embedded(6, body)

    # 关键：field 9 嵌套 field 1 = meta
    comm_sync = ProtoBufWriter()
    comm_sync.embedded(1, meta)
    root.embedded(9, comm_sync)

    root.uint32(11, 0)

    return root.bytes()


def build_sync_reply(username: str) -> bytes:
    """构造登录后服务端同步提示的客户端回包。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 0)

    meta = ProtoBufWriter()
    user_ref = ProtoBufWriter()
    user_ref.string(2, username)
    meta.embedded(3, user_ref)
    root.embedded(9, meta)

    root.uint32(11, 0)
    return root.bytes()


def build_receive_ack(message_id: int, username: str) -> bytes:
    """构造收到下行消息后的 ACK。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 0)

    meta = ProtoBufWriter()
    meta.uint64(2, message_id)
    user_ref = ProtoBufWriter()
    user_ref.string(2, username)
    meta.embedded(3, user_ref)
    root.embedded(9, meta)

    root.uint32(11, 0)
    return root.bytes()


# ── SockJS 帧格式 ──────────────────────────────────────

def sockjs_encode(data: bytes) -> str:
    """SockJS 客户端发送帧: ["base64"]。"""
    b64 = base64.b64encode(data).decode("ascii")
    return json.dumps([b64], ensure_ascii=False, separators=(",", ":"))


def sockjs_decode(frame: str) -> bytes:
    """解析 SockJS 接收帧, 返回 protobuf bytes 或 b''."""
    if frame.startswith('a["') and frame.endswith('"]') or frame.startswith('a["') and '"]' in frame:
        # 处理 a["base64"] 或 a["base64","base64"]
        inner = frame[2:-1]  # 去掉 a[ 和 ]
        # 可能有多个消息
        parts = []
        for part in inner.split(','):
            part = part.strip().strip('"')
            if part:
                try:
                    parts.append(base64.b64decode(part))
                except Exception:
                    pass
        return b''.join(parts) if parts else b''
    elif frame.startswith('o'):
        # SockJS open
        return b''
    elif frame.startswith('h'):
        # SockJS heartbeat
        return b''
    elif frame.startswith('c['):
        # SockJS close
        return b''
    return b''


# ── MSync 客户端 ───────────────────────────────────────

class MSyncClient:
    """
    MSync over SockJS 客户端.

    Usage:
        client = MSyncClient(app_key="cx-dev#cxstudy", domain="easemob.com")
        client.connect(token="YWMt...", username="25278974")
        client.send_message(to_user="340857874", content="hello")
    """

    HTTP_URL = "https://im-api-vip6-v2.easecdn.com/ws"
    XMPP_URL = "wss://im-api-vip6-v2.easecdn.com/ws"

    def __init__(
        self,
        app_key: str,
        domain: str = "easemob.com",
        platform: int = 3,
        on_message=None,
        on_error=None,
        on_close=None,
        cookies: str = None,
    ):
        self.app_key = app_key
        self.domain = domain
        self.platform = platform
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.cookies = cookies

        self._ws = None
        self._thread = None
        self._running = False
        self._resource = None
        self._token = None
        self._username = None
        self._server = None
        self._session = None
        self._heartbeat_timer = None
        self._authenticated = False

    # ── 连接管理 ──

    def connect(self, token: str, username: str):
        """建立 SockJS + MSync 连接."""
        self._token = token
        self._username = username
        self._authenticated = False
        # resource 和登录帧中的 timestamp 保持一致
        ts = int(time.time() * 1000)
        self._resource = f"webim_{ts}"
        self._resource_ts = ts

        # 1. SockJS 握手: GET /ws/info
        info = self._sockjs_info()
        if not info:
            raise ConnectionError("SockJS info 握手失败")

        # 2. 生成 server / session
        self._server = self._choose_server(info)
        self._session = self._generate_session()

        # 3. WebSocket 连接
        ws_url = f"{self.XMPP_URL}/{self._server}/{self._session}/websocket"
        logger.info(f"MSync: connecting to {ws_url}")

        headers = {
            "Origin": "https://im.chaoxing.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        if self.cookies:
            headers["Cookie"] = self.cookies
            logger.debug(f"MSync: WebSocket headers Cookie={self.cookies[:100]}...")

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
            header=headers,
        )

        self._running = True
        self._thread = threading.Thread(target=self._ws.run_forever, kwargs={
            "ping_interval": 30,
            "ping_timeout": 10,
        }, daemon=True)
        self._thread.start()

    def disconnect(self):
        """断开连接."""
        self._running = False
        self._authenticated = False
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        if self._ws:
            self._ws.close()
        self._thread = None

    def is_connected(self) -> bool:
        return (
            self._authenticated
            and self._ws is not None
            and self._ws.sock is not None
            and self._ws.sock.connected
        )

    # ── 消息发送 ──

    def send_message(self, to_user: str, content: str, msg_type: int = 0):
        """发送消息."""
        if not self.is_connected():
            raise ConnectionError("未连接")

        pb = build_send_message(
            self.app_key,
            self._username,
            to_user,
            self.domain,
            self._resource,
            content,
            msg_type,
        )
        frame = sockjs_encode(pb)
        logger.info(f"MSync: send frame len={len(frame)}")
        self._ws.send(frame)

    def send_login(self):
        """发送登录消息."""
        pb = build_login_message(
            self.app_key,
            self._username,
            self.domain,
            self._resource,
            self._token,
            self.platform,
            getattr(self, "_resource_ts", None),
        )
        frame = sockjs_encode(pb)
        b64 = base64.b64encode(pb).decode("ascii")
        logger.info(f"MSync: login frame len={len(frame)} b64={b64}")
        logger.info(f"MSync: login hex={pb.hex()}")
        # 同时解码打印结构，方便对比
        decoded = decode_message(pb)
        logger.info(f"MSync: login decoded={decoded}")
        self._ws.send(frame)

    def send_sync_reply(self):
        """响应服务端登录后的同步提示。"""
        pb = build_sync_reply(self._username)
        frame = sockjs_encode(pb)
        logger.info("MSync: send sync reply")
        self._ws.send(frame)

    def send_receive_ack(self, message_id: int):
        """发送收到下行消息后的 ACK。"""
        pb = build_receive_ack(message_id, self._username)
        frame = sockjs_encode(pb)
        logger.info(f"MSync: send receive ack message_id={message_id}")
        self._ws.send(frame)

    # ── 内部方法 ──

    def _sockjs_info(self) -> dict:
        """SockJS info 握手."""
        try:
            url = f"{self.HTTP_URL}/info?t={int(time.time() * 1000)}"
            headers = {
                "Origin": "https://im.chaoxing.com",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
            if self.cookies:
                headers["Cookie"] = self.cookies
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"MSync: info error {e}")
            return {}

    def _choose_server(self, info: dict) -> str:
        """选择服务器 ID."""
        # 浏览器实际使用 299
        return "299"

    def _generate_session(self) -> str:
        """生成 SockJS session ID."""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choice(chars) for _ in range(8))

    def _start_heartbeat(self):
        """启动心跳定时器."""
        def beat():
            if self._running and self.is_connected():
                self._ws.send("[]")  # SockJS heartbeat
                self._heartbeat_timer = threading.Timer(25, beat)
                self._heartbeat_timer.start()

        self._heartbeat_timer = threading.Timer(25, beat)
        self._heartbeat_timer.start()

    def _first(self, value):
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def _extract_jid_username(self, value):
        item = self._first(value)
        if isinstance(item, dict):
            username = self._first(item.get(2))
            if isinstance(username, str):
                return username
        return ""

    def _extract_text_push(self, decoded: dict):
        meta = self._first(decoded.get(9))
        if not isinstance(meta, dict):
            return None

        payload = self._first(meta.get(4))
        if not isinstance(payload, dict):
            return None

        body = self._first(payload.get(6))
        if not isinstance(body, dict):
            return None

        content = self._first(body.get(4))
        if not isinstance(content, dict):
            return None

        text = self._first(content.get(2))
        if not isinstance(text, str) or text == "":
            return None

        from_user = self._extract_jid_username(payload.get(2))
        to_user = self._extract_jid_username(payload.get(3))
        timestamp = self._first(payload.get(1)) or self._first(meta.get(8)) or 0
        message_id = self._first(meta.get(5))

        return {
            "from": from_user,
            "to": to_user,
            "content": text,
            "timestamp": timestamp,
            "message_id": message_id,
        }

    # ── WebSocket 回调 ──

    def _on_ws_open(self, ws):
        logger.info("MSync: WebSocket opened")
        self.send_login()
        self._start_heartbeat()

    def _on_ws_message(self, ws, message):
        logger.debug(f"MSync: recv raw={message[:100]}...")
        data = sockjs_decode(message)
        if not data:
            return

        try:
            decoded = decode_message(data)
            logger.debug(f"MSync: decoded={decoded}")
            if decoded:
                self._authenticated = True

            message_type = self._first(decoded.get(8))
            meta = self._first(decoded.get(9))

            if message_type == 2 and isinstance(meta, dict) and self._first(meta.get(1)) is not None:
                self.send_sync_reply()
                return

            push = self._extract_text_push(decoded)
            if push:
                message_id = push.pop("message_id", None)
                if isinstance(message_id, int):
                    self.send_receive_ack(message_id)
                if self.on_message:
                    self.on_message(push)
                return

            # 检查是否是消息推送
            if isinstance(meta, dict):
                body = self._first(meta.get(6))
                if isinstance(body, dict):
                    content = self._first(body.get(4))
                    if isinstance(content, dict):
                        text = self._first(content.get(2)) or ""
                        from_user = self._extract_jid_username(body.get(2))
                        to_user = self._extract_jid_username(body.get(3))

                        if text and self.on_message:
                            self.on_message({
                                "from": from_user,
                                "to": to_user,
                                "content": text,
                                "timestamp": self._first(meta.get(1)) or 0,
                            })
        except Exception as e:
            logger.error(f"MSync: decode error {e}")

    def _on_ws_error(self, ws, error):
        self._authenticated = False
        logger.error(f"MSync: WebSocket error {error}")
        if self.on_error:
            self.on_error(error)

    def _on_ws_close(self, ws, close_status_code, close_msg):
        logger.info(f"MSync: WebSocket closed {close_status_code} {close_msg}")
        self._running = False
        self._authenticated = False
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        if self.on_close:
            self.on_close(close_status_code, close_msg)

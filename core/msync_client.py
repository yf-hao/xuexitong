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

MSYNC_SEND_EPOCH_MS = 1264953600000


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
    meta.uint64(1, max(0, int(time.time() * 1000) - MSYNC_SEND_EPOCH_MS))

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


def build_conversation_read(
    app_key: str,
    from_user: str,
    to_user: str,
    domain: str,
    resource: str,
    message_id: int,
    conversation_type: int = 1,
) -> bytes:
    """构造打开会话后的已读同步帧。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)

    from_jid = build_jid(app_key, from_user, domain, resource)
    root.embedded(2, from_jid)
    root.uint32(8, 0)

    meta = ProtoBufWriter()
    meta.uint64(1, max(0, int(time.time() * 1000) - MSYNC_SEND_EPOCH_MS))
    meta.embedded(2, build_jid(app_key, from_user, domain, resource))

    to_jid = ProtoBufWriter()
    to_jid.string(1, app_key)
    to_jid.string(2, to_user)
    to_jid.string(3, domain)
    meta.embedded(3, to_jid)
    meta.uint32(5, int(conversation_type or 1))

    body = ProtoBufWriter()
    body.uint32(1, 4)

    from_inner = ProtoBufWriter()
    from_inner.string(2, from_user)
    body.embedded(2, from_inner)

    to_inner = ProtoBufWriter()
    to_inner.string(2, to_user)
    body.embedded(3, to_inner)
    body.string(4, "")
    body.uint64(6, int(message_id or 0))
    meta.embedded(6, body)

    comm_sync = ProtoBufWriter()
    comm_sync.embedded(1, meta)
    root.embedded(9, comm_sync)

    root.uint32(11, 0)
    return root.bytes()


def build_history_open() -> bytes:
    """构造打开会话历史同步的起始帧。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 1)
    root.uint32(11, 0)
    return root.bytes()


def build_history_subject(subject: str) -> bytes:
    """构造会话历史同步的主题帧。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 0)
    meta = ProtoBufWriter()
    user_ref = ProtoBufWriter()
    user_ref.string(2, subject)
    meta.embedded(3, user_ref)
    root.embedded(9, meta)
    root.uint32(11, 0)
    return root.bytes()


def build_history_subject_sync(cursor: int, subject: str, domain: str = "") -> bytes:
    """构造二阶段逐 subject 历史同步请求帧。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 0)
    meta = ProtoBufWriter()
    meta.uint64(2, int(cursor or 0))
    subject_ref = ProtoBufWriter()
    subject_ref.string(2, subject)
    if domain:
        subject_ref.string(3, domain)
    meta.embedded(3, subject_ref)
    root.embedded(9, meta)
    root.uint32(11, 0)
    return root.bytes()


def build_history_sync(timestamp_ms: int) -> bytes:
    """构造会话历史同步请求帧。"""
    root = ProtoBufWriter()
    root.uint32(1, 0)
    root.uint32(8, 0)
    meta = ProtoBufWriter()
    sync = ProtoBufWriter()
    sync.uint64(1, timestamp_ms)
    sync.uint32(5, 0)
    body = ProtoBufWriter()
    body.uint32(1, 0)
    sync.embedded(6, body)
    meta.embedded(1, sync)
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
    messages = sockjs_decode_all(frame)
    return b"".join(messages) if messages else b""


def sockjs_decode_all(frame: str) -> list[bytes]:
    """解析 SockJS 接收帧, 返回 protobuf bytes 列表。"""
    if frame.startswith('a["') and frame.endswith('"]') or frame.startswith('a["') and '"]' in frame:
        inner = frame[2:-1]
        parts = []
        for part in inner.split(','):
            part = part.strip().strip('"')
            if part:
                try:
                    parts.append(base64.b64decode(part))
                except Exception:
                    pass
        return parts
    if frame.startswith('o') or frame.startswith('h') or frame.startswith('c['):
        return []
    return []


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
        self._pending_history_peers = []
        self._pending_history_summary_peers = []
        self._pending_subject_syncs = []
        self._pending_conversation_reads = []
        self._last_history_summary = None
        self._last_history_subject_acks = []

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

    def is_running(self) -> bool:
        return self._running and self._ws is not None

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

    def send_conversation_read(self, peer_id: str, message_id: int, conversation_type: int = 1):
        """发送会话已读同步。"""
        pb = build_conversation_read(
            app_key=self.app_key,
            from_user=self._username,
            to_user=str(peer_id or ""),
            domain=self.domain,
            resource=self._resource,
            message_id=int(message_id or 0),
            conversation_type=conversation_type,
        )
        frame = sockjs_encode(pb)
        logger.info(f"MSync: send conversation read peer_id={peer_id} message_id={message_id}")
        self._ws.send(frame)

    def send_history_subject_sync(self, subject: str, cursor: int, domain: str = ""):
        """发送二阶段逐 subject 历史同步请求。"""
        pb = build_history_subject_sync(cursor, subject, domain=domain)
        self._ws.send(sockjs_encode(pb))

    def _build_history_subjects(self, peer_ids):
        subjects = []
        for subject in [self._username, *(peer_ids or []), "admin", "easemob_chat"]:
            subject = str(subject or "")
            if subject and subject not in subjects:
                subjects.append(subject)
        return subjects

    def _send_history_request(self, peer_id: str):
        subjects = self._build_history_subjects([peer_id])
        frames = [build_history_open()]
        frames.extend(build_history_subject(subject) for subject in subjects)
        frames.append(build_history_sync(int(time.time() * 1000)))

        for pb in frames:
            self._ws.send(sockjs_encode(pb))

    def _send_history_summary_request(self, peer_ids):
        subjects = self._build_history_subjects(peer_ids)
        if not subjects:
            return

        frames = [build_history_open()]
        frames.extend(build_history_subject(subject) for subject in subjects)
        frames.append(build_history_sync(int(time.time() * 1000)))

        for pb in frames:
            self._ws.send(sockjs_encode(pb))

    def _send_history_subject_syncs(self, subject_syncs):
        for item in subject_syncs or []:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject") or "")
            cursor = item.get("cursor")
            if not subject or not isinstance(cursor, int):
                continue
            domain = str(item.get("domain") or "")
            self.send_history_subject_sync(subject, cursor, domain=domain)

    def _queue_history_request(self, peer_id: str):
        peer_id = str(peer_id or "")
        if not peer_id:
            return False
        if peer_id not in self._pending_history_peers:
            self._pending_history_peers.append(peer_id)
        return True

    def _queue_history_summary_request(self, peer_ids):
        queued = False
        for peer_id in peer_ids or []:
            peer_id = str(peer_id or "")
            if not peer_id:
                continue
            if peer_id not in self._pending_history_summary_peers:
                self._pending_history_summary_peers.append(peer_id)
            queued = True
        return queued

    def _queue_subject_syncs(self, subject_syncs):
        queued = False
        for item in subject_syncs or []:
            if not isinstance(item, dict):
                continue
            subject = str(item.get("subject") or "")
            cursor = item.get("cursor")
            if not subject or not isinstance(cursor, int):
                continue
            payload = {
                "subject": subject,
                "cursor": cursor,
                "domain": str(item.get("domain") or ""),
            }
            if payload not in self._pending_subject_syncs:
                self._pending_subject_syncs.append(payload)
            queued = True
        return queued

    def _queue_conversation_read(self, peer_id: str, message_id: int, conversation_type: int = 1):
        peer_id = str(peer_id or "")
        try:
            message_id = int(message_id or 0)
        except Exception:
            message_id = 0
        if not peer_id or message_id <= 0:
            return False
        payload = {
            "peer_id": peer_id,
            "message_id": message_id,
            "conversation_type": int(conversation_type or 1),
        }
        self._pending_conversation_reads = [
            item for item in self._pending_conversation_reads
            if not (item.get("peer_id") == peer_id and int(item.get("conversation_type") or 1) == payload["conversation_type"])
        ]
        self._pending_conversation_reads.append(payload)
        return True

    def _flush_pending_history_requests(self):
        if not self.is_connected():
            return
        if self._pending_history_summary_peers:
            peer_ids = list(self._pending_history_summary_peers)
            self._pending_history_summary_peers.clear()
            try:
                self._send_history_summary_request(peer_ids)
            except Exception as e:
                logger.warning(f"MSync: flush pending history summary failed peer_ids={peer_ids} error={e}")
        while self._pending_history_peers:
            peer_id = self._pending_history_peers.pop(0)
            try:
                self._send_history_request(peer_id)
            except Exception as e:
                logger.warning(f"MSync: flush pending history failed peer_id={peer_id} error={e}")
        while self._pending_subject_syncs:
            payload = self._pending_subject_syncs.pop(0)
            try:
                self._send_history_subject_syncs([payload])
            except Exception as e:
                logger.warning(f"MSync: flush pending subject sync failed payload={payload} error={e}")
        while self._pending_conversation_reads:
            payload = self._pending_conversation_reads.pop(0)
            try:
                self.send_conversation_read(
                    payload.get("peer_id"),
                    int(payload.get("message_id") or 0),
                    conversation_type=int(payload.get("conversation_type") or 1),
                )
            except Exception as e:
                logger.warning(f"MSync: flush pending conversation read failed payload={payload} error={e}")

    def request_history(self, peer_id: str):
        """请求某个会话的历史同步。"""
        if self.is_connected():
            self._send_history_request(peer_id)
            return True
        if self.is_running():
            return self._queue_history_request(peer_id)
        raise ConnectionError("未连接")

    def request_history_summary(self, peer_ids):
        """请求消息列表里一批会话的历史汇总，用于未读计数。"""
        if self.is_connected():
            self._send_history_summary_request(peer_ids)
            return True
        if self.is_running():
            return self._queue_history_summary_request(peer_ids)
        raise ConnectionError("未连接")

    def request_history_subject_syncs(self, subject_syncs):
        """请求二阶段逐 subject 历史同步。"""
        if self.is_connected():
            self._send_history_subject_syncs(subject_syncs)
            return True
        if self.is_running():
            return self._queue_subject_syncs(subject_syncs)
        raise ConnectionError("未连接")

    def request_conversation_read(self, peer_id: str, message_id: int, conversation_type: int = 1):
        """请求同步某个会话的已读位置。"""
        try:
            message_id = int(message_id or 0)
        except Exception:
            message_id = 0
        if message_id <= 0:
            return False
        if self.is_connected():
            self.send_conversation_read(peer_id, message_id, conversation_type=conversation_type)
            return True
        if self.is_running():
            return self._queue_conversation_read(peer_id, message_id, conversation_type=conversation_type)
        raise ConnectionError("未连接")

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
        if isinstance(item, str):
            return item
        if isinstance(item, list):
            for part in item:
                username = self._extract_jid_username(part)
                if username:
                    return username
        if isinstance(item, dict):
            username = self._first(item.get(2))
            if isinstance(username, str):
                return username
            nested = self._first(item.get(1))
            if isinstance(nested, dict):
                username = self._first(nested.get(2))
                if isinstance(username, str):
                    return username
        return ""

    def _iter_dict_nodes(self, value, ancestors=None):
        ancestors = ancestors or []
        if isinstance(value, dict):
            yield value, ancestors
            next_ancestors = ancestors + [value]
            for child in value.values():
                yield from self._iter_dict_nodes(child, next_ancestors)
        elif isinstance(value, list):
            for child in value:
                yield from self._iter_dict_nodes(child, ancestors)

    def _iter_string_values(self, value):
        if isinstance(value, str):
            yield value
            return
        if isinstance(value, dict):
            for child in value.values():
                yield from self._iter_string_values(child)
            return
        if isinstance(value, list):
            for child in value:
                yield from self._iter_string_values(child)

    def _normalize_class_info(self, value):
        if not isinstance(value, dict):
            return None
        chat_id = str(value.get("chatid") or value.get("chatId") or "").strip()
        class_name = str(value.get("clazzName") or value.get("classname") or "").strip()
        course_name = str(value.get("coursename") or value.get("courseName") or "").strip()
        if not (chat_id or class_name or course_name):
            return None
        return {
            "chat_id": chat_id,
            "class_name": class_name,
            "course_name": course_name,
            "class_id": str(value.get("classid") or value.get("classId") or "").strip(),
            "course_id": str(value.get("courseid") or value.get("courseId") or "").strip(),
            "image_url": str(value.get("imageUrl") or value.get("chatIco") or "").strip(),
            "teacher_factor": str(value.get("teacherfactor") or value.get("teacherFactor") or "").strip(),
            "role": int(value.get("role") or 0) if str(value.get("role") or "").isdigit() else value.get("role") or 0,
            "is_teacher": bool(value.get("isTeacher", False)),
        }

    def _extract_class_info(self, *values):
        for value in values:
            for text in self._iter_string_values(value):
                text = str(text or "").strip()
                if not text.startswith("{") or not text.endswith("}"):
                    continue
                if not any(key in text for key in ('"chatid"', '"chatId"', '"clazzName"', '"classname"', '"coursename"', '"courseName"')):
                    continue
                try:
                    parsed = json.loads(text)
                except Exception:
                    continue
                normalized = self._normalize_class_info(parsed)
                if normalized:
                    return normalized
        return None

    def _extract_text_content(self, value):
        item = self._first(value)
        if isinstance(item, list):
            for part in item:
                text = self._extract_text_content(part)
                if text:
                    return text
        if isinstance(item, dict):
            direct = self._first(item.get(2))
            if isinstance(direct, str) and direct and 3 not in item:
                return direct
            for key in (4, 6, 1):
                text = self._extract_text_content(item.get(key))
                if text:
                    return text
        return ""

    def _extract_message_body_text(self, body: dict):
        if not isinstance(body, dict):
            return ""
        for candidate in (body.get(4), body.get(6), body.get(1)):
            text = self._extract_text_content(candidate)
            if text:
                return text
        return ""

    def _extract_command_name(self, body: dict):
        if not isinstance(body, dict):
            return ""
        command = self._first(body.get(4))
        if not isinstance(command, dict):
            return ""
        name = self._first(command.get(10))
        return name if isinstance(name, str) else ""

    def _extract_command_argument_value(self, arg: dict):
        if not isinstance(arg, dict):
            return None
        for field in (6, 3, 4, 2):
            value = self._first(arg.get(field))
            if isinstance(value, (str, int)):
                return value
        return None

    def _extract_command_arguments(self, body: dict):
        args = {}
        if not isinstance(body, dict):
            return args
        entries = body.get(5)
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return args

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = self._first(entry.get(1))
            if not isinstance(key, str) or not key:
                continue
            value = self._extract_command_argument_value(entry)
            if value is not None:
                args[key] = value
        return args

    def _select_timestamp(self, *values):
        for value in values:
            candidate = self._first(value)
            if isinstance(candidate, int) and candidate >= 10**11:
                return candidate
        return 0

    def _select_message_id(self, *values):
        for value in values:
            candidate = self._first(value)
            if isinstance(candidate, int) and candidate >= 10**12:
                return candidate
        return None

    def _iter_meta_dicts(self, decoded: dict):
        metas = decoded.get(9)
        if isinstance(metas, list):
            for meta in metas:
                if isinstance(meta, dict):
                    yield meta
        elif isinstance(metas, dict):
            yield metas

    def _resolve_peer_from_users(self, primary_from: str, primary_to: str, body_from: str, body_to: str):
        current = str(self._username or "")
        for from_user, to_user in (
            (body_from, body_to),
            (primary_from, primary_to),
            (body_to, body_from),
            (primary_to, primary_from),
        ):
            if from_user == current and to_user:
                return to_user
            if to_user == current and from_user:
                return from_user
            if from_user and from_user == to_user:
                return from_user
        return body_from or primary_from or body_to or primary_to

    def _extract_batch_messages(self, decoded: dict):
        messages = []
        for meta in self._iter_meta_dicts(decoded):
            entries = meta.get(4)
            if isinstance(entries, dict):
                entries = [entries]
            if not isinstance(entries, list):
                continue

            meta_timestamp = self._first(meta.get(8))
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                body = self._first(entry.get(6))
                if not isinstance(body, dict):
                    continue
                body_type = self._first(body.get(1))
                if body_type != 1:
                    continue
                text = self._extract_message_body_text(body)
                if not text:
                    continue

                route_from = self._extract_jid_username(entry.get(2))
                route_to = self._extract_jid_username(entry.get(3))
                body_from = self._extract_jid_username(body.get(2))
                body_to = self._extract_jid_username(body.get(3))
                peer_id = self._resolve_peer_from_users(route_from, route_to, body_from, body_to)
                message = {
                    "from": route_from or body_from,
                    "to": route_to or body_to,
                    "peer_id": peer_id,
                    "content": text,
                    "timestamp": self._select_timestamp(entry.get(4), meta_timestamp),
                    "message_id": self._select_message_id(entry.get(1), meta.get(5)),
                    "history_sync": True,
                }
                class_info = self._extract_class_info(entry, body)
                if class_info:
                    message["class_info"] = class_info
                messages.append(message)
        return messages

    def _extract_read_acks(self, decoded: dict):
        events = []
        seen = set()
        for node, ancestors in self._iter_dict_nodes(decoded):
            body_candidates = []
            for key in (6, 4):
                value = node.get(key)
                if isinstance(value, dict):
                    body_candidates.append(value)
                elif isinstance(value, list):
                    body_candidates.extend(part for part in value if isinstance(part, dict))
            if not body_candidates:
                continue

            for body in body_candidates:
                command_name = self._extract_command_name(body)
                if command_name != "CMD_READ_ACK":
                    continue

                args = self._extract_command_arguments(body)
                message_id = args.get("messageId")
                if message_id is None:
                    continue

                route_from = self._extract_jid_username(node.get(2)) or self._extract_jid_username(body.get(2))
                route_to = self._extract_jid_username(node.get(3)) or self._extract_jid_username(body.get(3))
                body_from = self._extract_jid_username(body.get(2))
                body_to = self._extract_jid_username(body.get(3))
                peer_id = str(args.get("conversationId") or self._resolve_peer_from_users(route_from, route_to, body_from, body_to) or "")

                timestamp = args.get("timestamp")
                if isinstance(timestamp, str):
                    try:
                        timestamp = int(timestamp)
                    except Exception:
                        timestamp = 0
                elif not isinstance(timestamp, int):
                    timestamp = self._select_timestamp(
                        node.get(1),
                        node.get(8),
                        *[ancestor.get(1) for ancestor in reversed(ancestors)],
                        *[ancestor.get(8) for ancestor in reversed(ancestors)],
                    )

                conversation_type = args.get("conversationType")
                if isinstance(conversation_type, str):
                    try:
                        conversation_type = int(conversation_type)
                    except Exception:
                        conversation_type = 0
                elif not isinstance(conversation_type, int):
                    conversation_type = 0

                unread_count = args.get("unreadCount")
                if isinstance(unread_count, str):
                    try:
                        unread_count = int(unread_count)
                    except Exception:
                        unread_count = None
                elif not isinstance(unread_count, int):
                    unread_count = None

                event = {
                    "event": "read_ack",
                    "command": command_name,
                    "peer_id": peer_id,
                    "from": route_from or body_from,
                    "to": route_to or body_to,
                    "from_puid": str(args.get("fromPuid") or ""),
                    "message_id": str(message_id),
                    "timestamp": int(timestamp or 0),
                    "conversation_type": conversation_type,
                }
                if unread_count is not None:
                    event["unread_count"] = unread_count
                identity = (event["message_id"], event["timestamp"], event["peer_id"])
                if identity in seen:
                    continue
                seen.add(identity)
                events.append(event)
        return events

    def _extract_history_summary(self, decoded: dict):
        """提取历史同步汇总帧中的 subject/count 列表。"""
        if not isinstance(decoded, dict):
            return None

        message_type = self._first(decoded.get(8))
        meta = self._first(decoded.get(9))
        if message_type != 1 or not isinstance(meta, dict):
            return None

        entries = meta.get(2)
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return None

        subjects = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            subject = self._extract_jid_username(entry.get(1))
            count = self._first(entry.get(2))
            if not subject or not isinstance(count, int):
                continue
            subjects.append({
                "subject": subject,
                "count": count,
            })

        if not subjects:
            return None

        timestamp = self._first(meta.get(3))
        if not isinstance(timestamp, int):
            timestamp = 0

        event = {
            "event": "history_summary",
            "subjects": subjects,
            "timestamp": timestamp,
        }
        self._last_history_summary = event
        return event

    def _extract_history_subject_acks(self, decoded: dict):
        """提取二阶段逐 subject 同步确认帧。"""
        if not isinstance(decoded, dict):
            return []

        message_type = self._first(decoded.get(8))
        meta = self._first(decoded.get(9))
        if message_type != 0 or not isinstance(meta, dict):
            return []

        subject_ref = self._first(meta.get(6))
        if not isinstance(subject_ref, dict):
            return []

        subject = self._extract_jid_username(subject_ref)
        if not subject:
            return []

        domain = str(self._first(subject_ref.get(3)) or "")
        if isinstance(self._first(meta.get(7)), int):
            ack_field = 7
            ack_code = self._first(meta.get(7))
        elif isinstance(self._first(meta.get(11)), int):
            ack_field = 11
            ack_code = self._first(meta.get(11))
        else:
            ack_field = 0
            ack_code = 0
        if ack_field == 0:
            return []

        timestamp = self._first(meta.get(8))
        if not isinstance(timestamp, int):
            timestamp = 0

        event = {
            "event": "history_subject_ack",
            "subject": subject,
            "domain": domain,
            "ack_code": int(ack_code or 0),
            "ack_field": ack_field,
            "timestamp": timestamp,
        }
        self._last_history_subject_acks.append(event)
        return [event]

    def _extract_text_push(self, decoded: dict):
        fallback_push = None
        for node, ancestors in self._iter_dict_nodes(decoded):
            body_candidates = []
            for key in (6, 4):
                value = node.get(key)
                if isinstance(value, dict):
                    body_candidates.append(value)
                elif isinstance(value, list):
                    body_candidates.extend(part for part in value if isinstance(part, dict))
            if not body_candidates:
                body_candidates = [node]

            for body in body_candidates:
                text = self._extract_message_body_text(body)
                if not text:
                    continue

                from_user = self._extract_jid_username(node.get(2)) or self._extract_jid_username(body.get(2))
                to_user = self._extract_jid_username(node.get(3)) or self._extract_jid_username(body.get(3))
                if not (from_user or to_user):
                    continue

                push = {
                    "from": from_user,
                    "to": to_user,
                    "content": text,
                    "timestamp": self._select_timestamp(
                        node.get(1),
                        node.get(8),
                        *[ancestor.get(1) for ancestor in reversed(ancestors)],
                        *[ancestor.get(8) for ancestor in reversed(ancestors)],
                    ),
                    "message_id": self._select_message_id(
                        node.get(5),
                        node.get(2),
                        *[ancestor.get(5) for ancestor in reversed(ancestors)],
                        *[ancestor.get(2) for ancestor in reversed(ancestors)],
                    ),
                }
                class_info = self._extract_class_info(node, body, ancestors)
                if class_info:
                    push["class_info"] = class_info

                if from_user and to_user:
                    return push
                if fallback_push is None:
                    fallback_push = push
        return fallback_push

    # ── WebSocket 回调 ──

    def _on_ws_open(self, ws):
        logger.info("MSync: WebSocket opened")
        self.send_login()
        self._start_heartbeat()

    def _on_ws_message(self, ws, message):
        logger.debug(f"MSync: recv raw={message[:100]}...")
        frames = sockjs_decode_all(message)
        if not frames:
            return

        for data in frames:
            try:
                decoded = decode_message(data)
                logger.debug(f"MSync: decoded={decoded}")
                if decoded:
                    self._authenticated = True

                message_type = self._first(decoded.get(8))
                meta = self._first(decoded.get(9))

                if message_type == 2 and isinstance(meta, dict) and self._first(meta.get(1)) is not None:
                    self.send_sync_reply()
                    self._flush_pending_history_requests()
                    continue

                self._flush_pending_history_requests()

                read_acks = self._extract_read_acks(decoded)
                if read_acks and self.on_message:
                    for event in read_acks:
                        self.on_message(event)

                history_summary = self._extract_history_summary(decoded)
                if history_summary and self.on_message:
                    self.on_message(history_summary)
                    if read_acks:
                        continue

                subject_acks = self._extract_history_subject_acks(decoded)
                if subject_acks and self.on_message:
                    for event in subject_acks:
                        self.on_message(event)
                    if read_acks:
                        continue

                batch_messages = self._extract_batch_messages(decoded)
                if batch_messages:
                    for push in batch_messages:
                        if self.on_message:
                            self.on_message(push)
                    if read_acks or subject_acks:
                        continue
                    continue

                push = self._extract_text_push(decoded)
                if push:
                    message_id = push.pop("message_id", None)
                    if isinstance(message_id, int):
                        self.send_receive_ack(message_id)
                    if self.on_message:
                        self.on_message(push)
                    continue

                if read_acks or subject_acks:
                    continue

                logger.debug(f"MSync: unrecognized message structure {decoded}")
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

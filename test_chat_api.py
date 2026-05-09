import unittest
import base64
import threading
from types import SimpleNamespace
from unittest.mock import patch

from core.apis.chat_api import ChatAPI
from core.msync_client import (
    MSyncClient,
    build_history_open,
    build_history_subject,
    build_history_sync,
    build_send_message,
    build_receive_ack,
    build_sync_reply,
    decode_message,
    sockjs_encode,
)
from ui.views.chat_view import ChatView


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": headers or {},
            "timeout": timeout,
            "method": "GET",
        })
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": headers or {},
            "data": data or {},
            "timeout": timeout,
            "method": "POST",
        })
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


class _FakeChatAPI(ChatAPI):
    def __init__(self, session, course_params=None):
        self._session = session
        self.session_manager = SimpleNamespace(course_params=course_params or {})
        self._connected = False
        self._send_ok = True
        self._last_msync_target = None

    @property
    def session(self):
        return self._session

    def is_msync_connected(self):
        return self._connected

    def send_message_msync(self, target_chat_id: str, content: str):
        self._last_msync_target = target_chat_id
        return self._send_ok


class _FakeCrawlerForView:
    def __init__(self):
        self.session_manager = SimpleNamespace(course_params={"im_tuid": "25278974"})
        self.connect_calls = 0
        self.connected = False

    def is_msync_connected(self):
        return self.connected

    def connect_msync(self, on_message=None, on_error=None, on_close=None):
        self.connect_calls += 1
        return SimpleNamespace()


class ChatAPITests(unittest.TestCase):
    def test_sockjs_encode_uses_client_array_frame(self):
        self.assertEqual(sockjs_encode(b"\x01\x02"), '["AQI="]')

    def test_build_sync_reply_matches_captured_frame(self):
        frame = base64.b64encode(build_sync_reply("25278974")).decode()
        self.assertEqual(frame, "CABAAEoMGgoSCDI1Mjc4OTc0WAA=")

    def test_build_receive_ack_matches_captured_frame(self):
        frame = base64.b64encode(build_receive_ack(1549112508483111976, "25278974")).decode()
        self.assertEqual(frame, "CABAAEoWEKiYgIrns+O/FRoKEggyNTI3ODk3NFgA")

    def test_build_history_frames_match_captured_frames(self):
        self.assertEqual(base64.b64encode(build_history_open()).decode(), "CABAAVgA")
        self.assertEqual(base64.b64encode(build_history_subject("25278974")).decode(), "CABAAEoMGgoSCDI1Mjc4OTc0WAA=")
        self.assertEqual(base64.b64encode(build_history_subject("340857874")).decode(), "CABAAEoNGgsSCTM0MDg1Nzg3NFgA")
        self.assertEqual(base64.b64encode(build_history_subject("admin")).decode(), "CABAAEoJGgcSBWFkbWluWAA=")
        self.assertEqual(base64.b64encode(build_history_subject("easemob_chat")).decode(), "CABAAEoQGg4SDGVhc2Vtb2JfY2hhdFgA")
        self.assertEqual(
            base64.b64encode(build_history_sync(1778250648847)).decode(),
            "CABAAEoPCg0Ij5r+v+AzKAAyAggAWAA=",
        )

    def test_build_send_message_matches_captured_browser_frame(self):
        with patch("core.msync_client.time.time", return_value=1778249614.196):
            frame = base64.b64encode(
                build_send_message(
                    app_key="cx-dev#cxstudy",
                    from_user="25278974",
                    to_user="340857874",
                    domain="easemob.com",
                    resource="webim_1778249600538",
                    content="2341",
                    msg_type=0,
                )
            ).decode()

        self.assertEqual(
            frame,
            "CAASPAoOY3gtZGV2I2N4c3R1ZHkSCDI1Mjc4OTc0GgtlYXNlbW9iLmNvbSITd2ViaW1fMTc3ODI0OTYwMDUzOEAASpsBCpgBCPS2zpb4DhI8Cg5jeC1kZXYjY3hzdHVkeRIIMjUyNzg5NzQaC2Vhc2Vtb2IuY29tIhN3ZWJpbV8xNzc4MjQ5NjAwNTM4GigKDmN4LWRldiNjeHN0dWR5EgkzNDA4NTc4NzQaC2Vhc2Vtb2IuY29tKAEyJQgBEgoSCDI1Mjc4OTc0GgsSCTM0MDg1Nzg3NCIICAASBDIzNDFYAA==",
        )

    def test_decode_message_recursively_decodes_text_push_payload(self):
        raw = base64.b64decode(
            "CABAAEqNAgoCCAAi6QEIqJiAiuez478VEjwKDmN4LWRldiNjeHN0dWR5EggyNTI3ODk3NBoL"
            "ZWFzZW1vYi5jb20iE3dlYmltXzE3NzgyNDU2NTQ2MzcaJwoOY3gtZGV2I2N4c3R1ZHkSCDI1"
            "Mjc4OTc0GgtlYXNlbW9iLmNvbSD17c294DMoATIpCAESChIIMjUyNzg5NzQaChIIMjUyNzg5"
            "NzQiCQgAEgUxMjM0NUoCe31CGwoRY2hhdF9yb3V0ZV90YXJnZXQQBzIEc2VsZkIUCgljbGll"
            "bnRfaWQQBBiH0M294DNKD3siaXNfb25saW5lIjoxfSiomICK57PjvxUyChIIMjUyNzg5NzRA"
            "+/LNveAz"
        )
        decoded = decode_message(raw)
        payload = decoded[9][4]
        self.assertEqual(payload[2][2], "25278974")
        self.assertEqual(payload[3][2], "25278974")
        self.assertEqual(payload[6][4][2], "12345")

    def test_extract_text_push_returns_message_and_ack_id(self):
        raw = base64.b64decode(
            "CABAAEqNAgoCCAAi6QEIqJiAiuez478VEjwKDmN4LWRldiNjeHN0dWR5EggyNTI3ODk3NBoL"
            "ZWFzZW1vYi5jb20iE3dlYmltXzE3NzgyNDU2NTQ2MzcaJwoOY3gtZGV2I2N4c3R1ZHkSCDI1"
            "Mjc4OTc0GgtlYXNlbW9iLmNvbSD17c294DMoATIpCAESChIIMjUyNzg5NzQaChIIMjUyNzg5"
            "NzQiCQgAEgUxMjM0NUoCe31CGwoRY2hhdF9yb3V0ZV90YXJnZXQQBzIEc2VsZkIUCgljbGll"
            "bnRfaWQQBBiH0M294DNKD3siaXNfb25saW5lIjoxfSiomICK57PjvxUyChIIMjUyNzg5NzRA"
            "+/LNveAz"
        )
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = decode_message(raw)
        push = client._extract_text_push(decoded)

        self.assertEqual(push["from"], "25278974")
        self.assertEqual(push["to"], "25278974")
        self.assertEqual(push["content"], "12345")
        self.assertEqual(push["message_id"], 1549112508483111976)

    def test_extract_text_push_supports_body_level_refs(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            9: {
                1: 1778245654637,
                5: 1549112508483111976,
                6: {
                    2: {2: "340857874"},
                    3: {2: "25278974"},
                    4: {2: "reply"},
                },
            }
        }

        push = client._extract_text_push(decoded)

        self.assertEqual(push["from"], "340857874")
        self.assertEqual(push["to"], "25278974")
        self.assertEqual(push["content"], "reply")
        self.assertEqual(push["timestamp"], 1778245654637)
        self.assertEqual(push["message_id"], 1549112508483111976)

    def test_extract_text_push_supports_meta_field_one_payload(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            9: {
                8: 1778245654637,
                1: {
                    2: {2: "340857874"},
                    3: {2: "25278974"},
                    6: {
                        4: {2: "reply-2"},
                    },
                },
            }
        }

        push = client._extract_text_push(decoded)

        self.assertEqual(push["from"], "340857874")
        self.assertEqual(push["to"], "25278974")
        self.assertEqual(push["content"], "reply-2")
        self.assertEqual(push["timestamp"], 1778245654637)

    def test_extract_text_push_does_not_treat_user_id_as_content(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            9: {
                4: {
                    2: {2: "340857874"},
                    3: {2: "25278974"},
                    6: {
                        2: {2: "340857874"},
                        3: {2: "25278974"},
                        4: {1: 0, 2: "hello"},
                    },
                },
                6: {2: "25278974"},
            }
        }

        push = client._extract_text_push(decoded)

        self.assertEqual(push["from"], "340857874")
        self.assertEqual(push["to"], "25278974")
        self.assertEqual(push["content"], "hello")

    def test_extract_text_push_ignores_ios_resource_string(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            9: {
                4: {
                    2: {2: "340857874", 4: "ios_ddf20fd9-c17e-3646-c585-bc811f62432e"},
                    3: {2: "25278974"},
                    6: {
                        2: {2: "340857874"},
                        3: {2: "25278974"},
                        4: {1: 0, 2: "1235"},
                    },
                }
            }
        }

        push = client._extract_text_push(decoded)

        self.assertEqual(push["content"], "1235")
        self.assertEqual(push["from"], "340857874")
        self.assertEqual(push["to"], "25278974")

    def test_extract_batch_messages_returns_self_history(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._username = "25278974"
        decoded = {
            9: {
                4: [{
                    1: 1549133423325482008,
                    2: {2: "25278974"},
                    3: {2: "25278974"},
                    4: 1778250284057,
                    6: {
                        1: 1,
                        2: {2: "25278974"},
                        3: {2: "25278974"},
                        4: {1: 0, 2: "123"},
                    },
                }]
            }
        }

        messages = client._extract_batch_messages(decoded)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["peer_id"], "25278974")
        self.assertEqual(messages[0]["content"], "123")

    def test_extract_read_ack_returns_event_payload(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._username = "25278974"
        decoded = {
            9: {
                4: {
                    2: {2: "25278974"},
                    3: {2: "25278974"},
                    6: {
                        1: 1,
                        2: {2: "25278974"},
                        3: {2: "25278974"},
                        4: {1: 6, 10: "CMD_READ_ACK"},
                        5: [
                            {1: "conversationId", 6: "340857874"},
                            {1: "conversationType", 3: 0},
                            {1: "fromPuid", 6: "30047383"},
                            {1: "messageId", 6: "1549133423325482008"},
                            {1: "timestamp", 3: 1778249900000},
                        ],
                    },
                }
            }
        }

        events = client._extract_read_acks(decoded)
        ack = events[0]

        self.assertEqual(len(events), 1)
        self.assertEqual(ack["event"], "read_ack")
        self.assertEqual(ack["command"], "CMD_READ_ACK")
        self.assertEqual(ack["peer_id"], "340857874")
        self.assertEqual(ack["message_id"], "1549133423325482008")
        self.assertEqual(ack["from_puid"], "30047383")
        self.assertEqual(ack["timestamp"], 1778249900000)

    def test_request_history_queues_while_connecting(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._username = "25278974"
        client._running = True
        client._ws = SimpleNamespace(send=lambda frame: None)

        queued = client.request_history("340857874")

        self.assertTrue(queued)
        self.assertEqual(client._pending_history_peers, ["340857874"])

    def test_on_ws_message_dispatches_read_ack_and_batch_message(self):
        events = []
        client = MSyncClient(app_key="cx-dev#cxstudy", on_message=events.append)
        client._username = "25278974"
        decoded = {
            9: {
                4: [
                    {
                        2: {2: "25278974"},
                        3: {2: "25278974"},
                        4: 1778250284057,
                        6: {
                            1: 1,
                            2: {2: "25278974"},
                            3: {2: "25278974"},
                            4: {1: 6, 10: "CMD_READ_ACK"},
                            5: [
                                {1: "conversationId", 6: "25278974"},
                                {1: "messageId", 6: "1549133423325482008"},
                                {1: "timestamp", 3: 1778249900000},
                            ],
                        },
                    },
                    {
                        1: 1549133423325482008,
                        2: {2: "25278974"},
                        3: {2: "25278974"},
                        4: 1778250284057,
                        6: {
                            1: 1,
                            2: {2: "25278974"},
                            3: {2: "25278974"},
                            4: {1: 0, 2: "123"},
                        },
                    },
                ]
            }
        }

        with patch("core.msync_client.sockjs_decode", return_value=b"x"), patch("core.msync_client.decode_message", return_value=decoded):
            client._on_ws_message(None, 'a["eA=="]')

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "read_ack")
        self.assertEqual(events[1]["content"], "123")

    def test_get_history_messages_posts_msg_id_for_existing_session(self):
        response = _FakeResponse(
            payload={
                "status": "success",
                "data": [{"msgId": "1", "from": "100", "content": "hello"}],
            }
        )
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        messages = api.get_history_messages("100+chat-1", limit=20)

        self.assertEqual(messages, [{"msgId": "1", "from": "100", "content": "hello"}])
        self.assertTrue(session.calls[0]["url"].endswith("/webim/message/history/getHistoryByMsgId"))
        self.assertEqual(session.calls[0]["data"], {"msgId": "100+chat-1"})

    def test_get_history_messages_falls_back_to_chat_id_payload(self):
        response = _FakeResponse(
            payload={
                "status": "success",
                "data": [{"msgId": "1", "from": "100", "content": "hello"}],
            }
        )
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        messages = api.get_history_messages("chat-1", limit=20)

        self.assertEqual(messages, [{"msgId": "1", "from": "100", "content": "hello"}])
        self.assertEqual(
            session.calls[0]["data"],
            {
                "tuid": "100",
                "puid": "200",
                "token": "token-1",
                "chatId": "chat-1",
                "limit": "20",
            },
        )

    def test_get_history_messages_returns_empty_on_api_error(self):
        response = _FakeResponse(payload={"status": "fail", "msg": "bad token"})
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        messages = api.get_history_messages("chat-1")

        self.assertEqual(messages, [])

    def test_get_group_members_posts_room_id_and_normalizes_members(self):
        response = _FakeResponse(
            payload={
                "members": [
                    {
                        "puid": 30047383,
                        "name": "郝玉锋",
                        "tuid": 25278974,
                        "pic": "http://photo.example/avatar.png",
                    }
                ]
            }
        )
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        members = api.get_group_members("306927744647171")

        self.assertEqual(
            members,
            [{
                "person_id": "25278974",
                "name": "郝玉锋",
                "student_id": "30047383",
                "avatar_url": "http://photo.example/avatar.png",
                "tuid": "25278974",
                "puid": "30047383",
            }],
        )
        self.assertTrue(session.calls[0]["url"].endswith("/webim/group/getGroupInfoByCount"))
        self.assertEqual(
            session.calls[0]["data"],
            {"roomId": "306927744647171", "token": "token-1", "tuid": "100"},
        )

    def test_extract_class_chat_map_from_me_html(self):
        html = (
            '<html><script>var classChat={"chatid306927944925186":'
            '{"classname":"4.03计科2班、区块链1班","coursename":"离散数学（2025-2026-2）"}};</script></html>'
        )

        result = ChatAPI._extract_class_chat_map(html)

        self.assertEqual(
            result,
            {
                "chatid306927944925186": {
                    "classname": "4.03计科2班、区块链1班",
                    "coursename": "离散数学（2025-2026-2）",
                }
            },
        )

    def test_get_message_list_applies_classname_as_subtitle(self):
        response = _FakeResponse(
            payload={
                "status": "success",
                "data": [
                    {
                        "chatId": "306927944925186",
                        "chatName": "离散数学（2025-2026-2）",
                        "isGroup": 0,
                    },
                    {
                        "chatId": "peer-1",
                        "chatName": "张三",
                        "isGroup": 1,
                    },
                ],
            }
        )
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={
                "im_tuid": "100",
                "im_puid": "200",
                "im_token": "token-1",
                "im_class_chat": {
                    "chatid306927944925186": {
                        "classname": "4.03计科2班、区块链1班",
                        "coursename": "离散数学（2025-2026-2）",
                    }
                },
            },
        )

        sessions = api.get_message_list()

        self.assertEqual(sessions[0]["subtitle"], "4.03计科2班、区块链1班")
        self.assertEqual(sessions[0]["courseName"], "离散数学（2025-2026-2）")
        self.assertNotIn("subtitle", sessions[1])

    def test_add_message_history_matches_browser_payload_shape(self):
        response = [
            _FakeResponse(payload={"data": {"name": "郝玉锋", "icon": "http://photo.example/avatar.png"}}),
            _FakeResponse(payload={"status": "success"}),
        ]
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        result = api._add_message_history("chat-1", "hello", target_name="张三")

        self.assertEqual(result, {"status": "success"})
        self.assertTrue(session.calls[0]["url"].endswith("/webim/user/getUserInfoByTuid"))
        self.assertTrue(session.calls[1]["url"].endswith("/webim/message/history/addMessage"))
        self.assertEqual(session.calls[1]["data"]["tuid"], "100")
        self.assertEqual(session.calls[1]["data"]["content"], "hello")
        self.assertEqual(session.calls[1]["data"]["chatManId"], "chat-1")
        self.assertEqual(session.calls[1]["data"]["chatManName"], "张三")
        self.assertEqual(session.calls[1]["data"]["name"], "郝玉锋")
        self.assertEqual(session.calls[1]["data"]["icon"], "http://photo.example/avatar.png")
        self.assertNotIn("puid", session.calls[1]["data"])
        self.assertNotIn("token", session.calls[1]["data"])
        self.assertNotIn("chatId", session.calls[1]["data"])

    def test_send_message_fails_without_realtime_connection(self):
        session = _FakeSession(_FakeResponse(payload={"status": "success"}))
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        result = api.send_message("chat-1", "hello", target_name="张三")

        self.assertEqual(result["status"], "fail")
        self.assertIn("实时消息连接未建立", result["msg"])
        self.assertEqual(session.calls, [])

    def test_send_message_requires_realtime_connection_before_history_write(self):
        response = [
            _FakeResponse(payload={"data": {"name": "郝玉锋", "icon": "http://photo.example/avatar.png"}}),
            _FakeResponse(payload={"status": "success"}),
        ]
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )
        api._connected = True

        result = api.send_message("chat-1", "hello", target_name="张三")

        self.assertEqual(result["status"], "success")
        self.assertTrue(session.calls[0]["url"].endswith("/webim/user/getUserInfoByTuid"))
        self.assertTrue(session.calls[1]["url"].endswith("/webim/message/history/addMessage"))

    def test_send_message_uses_history_chat_id_for_history_write(self):
        response = [
            _FakeResponse(payload={"data": {"name": "郝玉锋", "icon": "http://photo.example/avatar.png"}}),
            _FakeResponse(payload={"status": "success"}),
        ]
        session = _FakeSession(response)
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )
        api._connected = True

        result = api.send_message("peer-123", "hello", target_name="张三", history_chat_id="chat-456")

        self.assertEqual(result["status"], "success")
        self.assertEqual(api._last_msync_target, "peer-123")
        self.assertEqual(session.calls[1]["data"]["chatManId"], "chat-456")

    def test_connect_msync_reuses_running_client(self):
        session = _FakeSession(_FakeResponse(payload={}))
        api = _FakeChatAPI(session, course_params={"im_tuid": "100", "im_token": "token-1"})
        running_client = SimpleNamespace(
            is_running=lambda: True,
            on_message=None,
            on_error=None,
            on_close=None,
        )
        api._msync = running_client

        result = api.connect_msync(on_message="msg", on_error="err", on_close="close")

        self.assertIs(result, running_client)
        self.assertEqual(running_client.on_message, "msg")
        self.assertEqual(running_client.on_error, "err")
        self.assertEqual(running_client.on_close, "close")

    def test_chat_view_ensure_msync_connected_starts_single_background_connect(self):
        crawler = _FakeCrawlerForView()
        with patch("ui.views.chat_view.threading.Thread") as mock_thread:
            thread_instance = SimpleNamespace(start=lambda: None)
            mock_thread.return_value = thread_instance
            view = SimpleNamespace(
                crawler=crawler,
                _msync_connecting=False,
                _msync_connect_lock=threading.Lock(),
                _current_target_id="",
            )

            ChatView._ensure_msync_connected(view)
            ChatView._ensure_msync_connected(view)

        self.assertEqual(mock_thread.call_count, 1)


if __name__ == "__main__":
    unittest.main()

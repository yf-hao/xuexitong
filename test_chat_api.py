import unittest
from types import SimpleNamespace

from core.apis.chat_api import ChatAPI
from core.msync_client import sockjs_encode


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

    def post(self, url, headers=None, data=None, timeout=None):
        self.calls.append({
            "url": url,
            "headers": headers or {},
            "data": data or {},
            "timeout": timeout,
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

    @property
    def session(self):
        return self._session

    def is_msync_connected(self):
        return self._connected

    def send_message_msync(self, target_chat_id: str, content: str):
        return self._send_ok


class ChatAPITests(unittest.TestCase):
    def test_sockjs_encode_uses_client_array_frame(self):
        self.assertEqual(sockjs_encode(b"\x01\x02"), '["AQI="]')

    def test_get_history_messages_posts_expected_payload(self):
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
        self.assertTrue(session.calls[0]["url"].endswith("/webim/message/history/getHistoryByMsgId"))
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


if __name__ == "__main__":
    unittest.main()

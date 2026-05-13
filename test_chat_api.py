import json
import unittest
import base64
import threading
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PyQt6.QtCore import Qt

from core.apis.chat_api import ChatAPI
from core.apis.activity_api import ActivityAPI
from core.apis.question_bank_api import QuestionBankAPI
from core.apis.teacher_api import TeacherAPI
from core.communication_manager import CommunicationManager
from core.group_members_cache import build_group_members_cache_path, resolve_student_from_group_cache
from core.rendering.katex_snapshot import KaTeXSnapshotRenderer
from models.attendance_record import AttendanceDetail
from core.msync_client import (
    MSyncClient,
    build_conversation_read,
    build_history_open,
    build_history_subject,
    build_history_subject_sync,
    build_history_sync,
    build_send_message,
    build_receive_ack,
    build_sync_reply,
    decode_message,
    sockjs_encode,
    sockjs_decode_all,
)
from ui.views.chat_view import ChatView
from ui.views.activities_view import ActivitiesView
from ui.views.study_status_view import StudyStatusView, NumericTableWidgetItem
from ui.dialogs.absence_stats_dialog import AbsenceStatsDialog
from ui.dialogs.homework_reminder_dialog import DEFAULT_ABSENCE_REMINDER_TEMPLATE, DEFAULT_HOMEWORK_REMINDER_TEMPLATE
from ui.dialogs.qrcode_dialog import QRCodeDialog
from ui.dialogs.student_message_dialog import StudentMessageDialog


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": params or {},
            "headers": headers or {},
            "timeout": timeout,
            "method": "GET",
        })
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response

    def post(self, url, params=None, headers=None, data=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": params or {},
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
        self.__class__._msync = None
        self.__class__._msync_message_listeners = {}
        self.__class__._msync_error_listeners = {}
        self.__class__._msync_close_listeners = {}
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


class _FakeQuestionBankAPI(QuestionBankAPI):
    def __init__(self, session, course_params=None):
        self._session = session
        self.session_manager = SimpleNamespace(course_params=course_params or {})

    @property
    def session(self):
        return self._session

    def upload_cover_image(self, path, upload_variant="question"):
        return {"success": True, "url": f"https://img.example/{Path(path).name}"}


class _FakeCrawlerForView:
    def __init__(self):
        self.session_manager = SimpleNamespace(course_params={"im_tuid": "25278974"})
        self.connect_calls = 0
        self.connected = False

    def is_msync_connected(self):
        return self.connected

    def connect_msync(self, on_message=None, on_error=None, on_close=None, listener_key=None):
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

    def test_build_conversation_read_matches_captured_frame(self):
        with patch("core.msync_client.time.time", return_value=1778320752.883):
            frame = base64.b64encode(
                build_conversation_read(
                    app_key="cx-dev#cxstudy",
                    from_user="25278974",
                    to_user="247836588",
                    domain="easemob.com",
                    resource="webim_1778318788491",
                    message_id=1549317683114151060,
                )
            ).decode()
        self.assertEqual(
            frame,
            "CAASPAoOY3gtZGV2I2N4c3R1ZHkSCDI1Mjc4OTc0GgtlYXNlbW9iLmNvbSITd2ViaW1fMTc3ODMxODc4ODQ5MUAASp0BCpoBCPOxxLj4DhI8Cg5jeC1kZXYjY3hzdHVkeRIIMjUyNzg5NzQaC2Vhc2Vtb2IuY29tIhN3ZWJpbV8xNzc4MzE4Nzg4NDkxGigKDmN4LWRldiNjeHN0dWR5EgkyNDc4MzY1ODgaC2Vhc2Vtb2IuY29tKAEyJwgEEgoSCDI1Mjc4OTc0GgsSCTI0NzgzNjU4OCIAMJSZgJKWh5LAFVgA",
        )

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

    def test_build_history_subject_sync_matches_captured_frames(self):
        self.assertEqual(
            base64.b64encode(build_history_subject_sync(1549416979549404396, "247836588")).decode(),
            "CABAAEoXEOz5gJiK0ajAFRoLEgkyNDc4MzY1ODhYAA==",
        )
        self.assertEqual(
            base64.b64encode(
                build_history_subject_sync(
                    1549420076426333220,
                    "313439014682626",
                    domain="conference.easemob.com",
                )
            ).decode(),
            "CABAAEo1EKSYgPqaq6nAFRopEg8zMTM0MzkwMTQ2ODI2MjYaFmNvbmZlcmVuY2UuZWFzZW1vYi5jb21YAA==",
        )

    def test_sockjs_decode_all_splits_multiple_messages(self):
        decoded = sockjs_decode_all('a["QQ==","Qg=="]')
        self.assertEqual(decoded, [b"A", b"B"])

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

    def test_extract_read_ack_includes_unread_count(self):
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
                            {1: "conversationId", 6: "25278974"},
                            {1: "messageId", 6: "1549287205527104536"},
                            {1: "timestamp", 6: "1778286337275"},
                            {1: "unreadCount", 3: 1},
                        ],
                    },
                }
            }
        }

        events = client._extract_read_acks(decoded)

        self.assertEqual(events[0]["unread_count"], 1)

    def test_extract_history_summary_returns_subject_counts(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            1: 0,
            8: 1,
            9: {
                1: {1: 0},
                2: [
                    {1: {2: "247836588"}, 2: 4},
                    {1: {2: "25278974"}, 2: 3},
                    {1: {2: "358566558"}, 2: 5},
                    {1: {2: "easemob_chat"}, 2: 1},
                ],
                3: 1778316224885,
            },
        }

        event = client._extract_history_summary(decoded)

        self.assertEqual(
            event,
            {
                "event": "history_summary",
                "subjects": [
                    {"subject": "247836588", "count": 4},
                    {"subject": "25278974", "count": 3},
                    {"subject": "358566558", "count": 5},
                    {"subject": "easemob_chat", "count": 1},
                ],
                "timestamp": 1778316224885,
            },
        )
        self.assertEqual(client._last_history_summary, event)

    def test_extract_history_subject_ack_ignores_batch_history_frame(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            1: 0,
            8: 0,
            9: {
                4: [{
                    1: 1549416979549404396,
                    2: {2: "25278974"},
                    3: {2: "247836588"},
                    4: 1778316552653,
                    6: {1: 4, 2: {2: "25278974"}, 3: {2: "247836588"}, 4: "", 6: 1549317683114151060},
                }],
                5: 1549416979549404396,
                6: {2: "247836588"},
                8: 1778317529391,
            },
        }

        events = client._extract_history_subject_acks(decoded)

        self.assertEqual(events, [])

    def test_extract_history_subject_ack_returns_subject_timestamp_and_flag(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            1: 0,
            8: 0,
            9: {
                1: {1: 0},
                6: {2: "313439014682626", 3: "conference.easemob.com"},
                11: 1,
                8: 1778317531421,
            },
        }

        events = client._extract_history_subject_acks(decoded)

        self.assertEqual(
            events,
            [{
                "event": "history_subject_ack",
                "subject": "313439014682626",
                "domain": "conference.easemob.com",
                "ack_code": 1,
                "ack_field": 11,
                "timestamp": 1778317531421,
            }],
        )
        self.assertEqual(client._last_history_subject_acks[-1], events[0])

    def test_extract_batch_messages_includes_class_info(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._username = "25278974"
        decoded = {
            9: {
                4: [{
                    1: 1549133423325482008,
                    2: {2: "358566558"},
                    3: {2: "25278974"},
                    4: 1778250284057,
                    6: {
                        1: 1,
                        2: {2: "358566558"},
                        3: {2: "25278974"},
                        4: {1: 0, 2: "老师说明天上课"},
                        8: (
                            '{"chatid":"306927744647171","clazzName":"4.01计科3班、4班",'
                            '"coursename":"离散数学（2025-2026-2）","imageUrl":"https://photo.example/group.png"}'
                        ),
                    },
                }]
            }
        }

        messages = client._extract_batch_messages(decoded)

        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0]["class_info"],
            {
                "chat_id": "306927744647171",
                "class_name": "4.01计科3班、4班",
                "course_name": "离散数学（2025-2026-2）",
                "class_id": "",
                "course_id": "",
                "image_url": "https://photo.example/group.png",
                "teacher_factor": "",
                "role": 0,
                "is_teacher": False,
            },
        )

    def test_extract_text_push_includes_class_info(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        decoded = {
            9: {
                4: {
                    2: {2: "358574049"},
                    3: {2: "25278974"},
                    6: {
                        2: {2: "358574049"},
                        3: {2: "25278974"},
                        4: {1: 0, 2: "好的老师"},
                        8: (
                            '{"chatid":"306927944925186","clazzName":"4.03计科2班、区块链1班",'
                            '"coursename":"离散数学（2025-2026-2）"}'
                        ),
                    },
                }
            }
        }

        push = client._extract_text_push(decoded)

        self.assertEqual(push["content"], "好的老师")
        self.assertEqual(push["class_info"]["chat_id"], "306927944925186")
        self.assertEqual(push["class_info"]["class_name"], "4.03计科2班、区块链1班")

    def test_request_history_queues_while_connecting(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._username = "25278974"
        client._running = True
        client._ws = SimpleNamespace(send=lambda frame: None)

        queued = client.request_history("340857874")

        self.assertTrue(queued)
        self.assertEqual(client._pending_history_peers, ["340857874"])

    def test_request_history_summary_queues_while_connecting(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._running = True
        client._ws = SimpleNamespace(send=lambda frame: None)

        queued = client.request_history_summary(["247836588", "358566558"])

        self.assertTrue(queued)
        self.assertEqual(client._pending_history_summary_peers, ["247836588", "358566558"])

    def test_request_history_subject_syncs_queues_while_connecting(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._running = True
        client._ws = SimpleNamespace(send=lambda frame: None)

        queued = client.request_history_subject_syncs([
            {"subject": "247836588", "cursor": 1549416979549404396},
            {"subject": "313439014682626", "domain": "conference.easemob.com", "cursor": 1549420076426333220},
        ])

        self.assertTrue(queued)
        self.assertEqual(
            client._pending_subject_syncs,
            [
                {"subject": "247836588", "cursor": 1549416979549404396, "domain": ""},
                {"subject": "313439014682626", "cursor": 1549420076426333220, "domain": "conference.easemob.com"},
            ],
        )

    def test_request_conversation_read_queues_while_connecting(self):
        client = MSyncClient(app_key="cx-dev#cxstudy")
        client._running = True
        client._ws = SimpleNamespace(send=lambda frame: None)

        queued = client.request_conversation_read("247836588", 1549317683114151060)

        self.assertTrue(queued)
        self.assertEqual(
            client._pending_conversation_reads,
            [{"peer_id": "247836588", "message_id": 1549317683114151060, "conversation_type": 1}],
        )

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

        with patch("core.msync_client.decode_message", return_value=decoded):
            client._on_ws_message(None, 'a["eA=="]')

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "read_ack")
        self.assertEqual(events[1]["content"], "123")

    def test_on_ws_message_dispatches_history_summary(self):
        events = []
        client = MSyncClient(app_key="cx-dev#cxstudy", on_message=events.append)
        decoded = {
            1: 0,
            8: 1,
            9: {
                1: {1: 0},
                2: [
                    {1: {2: "358566558"}, 2: 5},
                    {1: {2: "easemob_chat"}, 2: 1},
                ],
                3: 1778316224885,
            },
        }

        with patch("core.msync_client.decode_message", return_value=decoded):
            client._on_ws_message(None, 'a["eA=="]')

        self.assertEqual(
            events,
            [{
                "event": "history_summary",
                "subjects": [
                    {"subject": "358566558", "count": 5},
                    {"subject": "easemob_chat", "count": 1},
                ],
                "timestamp": 1778316224885,
            }],
        )

    def test_on_ws_message_dispatches_multiple_history_subject_acks(self):
        events = []
        client = MSyncClient(app_key="cx-dev#cxstudy", on_message=events.append)
        decoded_frames = [
            {
                1: 0,
                8: 0,
                9: {
                    1: {1: 0},
                    6: {2: "247836588"},
                    7: 1,
                    8: 1778317531380,
                },
            },
            {
                1: 0,
                8: 0,
                9: {
                    1: {1: 0},
                    6: {2: "313439014682626", 3: "conference.easemob.com"},
                    11: 1,
                    8: 1778317531421,
                },
            },
        ]

        with patch("core.msync_client.decode_message", side_effect=decoded_frames):
            client._on_ws_message(None, 'a["QQ==","Qg=="]')

        self.assertEqual(
            events,
            [
                {
                    "event": "history_subject_ack",
                    "subject": "247836588",
                    "domain": "",
                    "ack_code": 1,
                    "ack_field": 7,
                    "timestamp": 1778317531380,
                },
                {
                    "event": "history_subject_ack",
                    "subject": "313439014682626",
                    "domain": "conference.easemob.com",
                    "ack_code": 1,
                    "ack_field": 11,
                    "timestamp": 1778317531421,
                },
            ],
        )

    def test_chat_view_store_class_info_metadata_updates_sessions(self):
        row_updates = []
        view = SimpleNamespace(
            _session_meta_by_peer={},
            _history_id_by_peer={},
            _unread_count_by_peer={},
            _raw_sessions=[{
                "chatId": "358566558",
                "chatName": "离散数学（2025-2026-2）",
                "chatIco": "",
            }],
        )
        view._resolve_session_peer_id = lambda session: str(session.get("chatId", "") or "")
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._merge_session_metadata = lambda session: ChatView._merge_session_metadata(view, session)
        view._update_session_row = lambda peer_id="", history_id="", session=None: row_updates.append((peer_id, history_id, session))

        changed = ChatView._store_class_info_metadata(
            view,
            "358566558",
            {
                "chat_id": "306927744647171",
                "class_name": "4.01计科3班、4班",
                "course_name": "离散数学（2025-2026-2）",
                "image_url": "https://photo.example/group.png",
            },
        )

        self.assertTrue(changed)
        self.assertEqual(view._session_meta_by_peer["358566558"]["subtitle"], "4.01计科3班、4班")
        self.assertEqual(view._history_id_by_peer["358566558"], "306927744647171")
        self.assertEqual(view._raw_sessions[0]["subtitle"], "4.01计科3班、4班")
        self.assertEqual(view._raw_sessions[0]["chatIco"], "https://photo.example/group.png")
        self.assertEqual(len(row_updates), 1)
        self.assertEqual(row_updates[0][0], "306927744647171")
        self.assertEqual(row_updates[0][1], "306927744647171")

    def test_chat_view_store_class_info_metadata_can_skip_avatar_updates(self):
        row_updates = []
        view = SimpleNamespace(
            _session_meta_by_peer={},
            _history_id_by_peer={},
            _unread_count_by_peer={},
            _raw_sessions=[{
                "chatId": "358566558",
                "chatName": "离散数学（2025-2026-2）",
                "chatIco": "https://photo.example/original.png",
            }],
        )
        view._resolve_session_peer_id = lambda session: str(session.get("chatId", "") or "")
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._merge_session_metadata = lambda session: ChatView._merge_session_metadata(view, session)
        view._update_session_row = lambda peer_id="", history_id="", session=None: row_updates.append((peer_id, history_id, session))

        changed = ChatView._store_class_info_metadata(
            view,
            "358566558",
            {
                "chat_id": "306927744647171",
                "class_name": "4.01计科3班、4班",
                "course_name": "离散数学（2025-2026-2）",
                "image_url": "https://photo.example/group.png",
            },
            allow_avatar_update=False,
        )

        self.assertTrue(changed)
        self.assertEqual(view._raw_sessions[0]["chatIco"], "https://photo.example/original.png")
        self.assertNotIn("chatIco", view._session_meta_by_peer["358566558"])

    def test_chat_view_store_class_info_metadata_carries_unread_count_to_chat_id(self):
        view = SimpleNamespace(
            _session_meta_by_peer={},
            _history_id_by_peer={},
            _unread_count_by_peer={"358566558": 5},
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "离散数学", "chatIco": ""}],
        )
        view._resolve_session_peer_id = lambda session: str(session.get("chatId", "") or "")
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._merge_session_metadata = lambda session: ChatView._merge_session_metadata(view, session)
        view._update_session_row = lambda peer_id="", history_id="", session=None: True

        ChatView._store_class_info_metadata(
            view,
            "358566558",
            {"chat_id": "306927744647171", "class_name": "4.01计科3班、4班"},
        )

        self.assertEqual(view._unread_count_by_peer["306927744647171"], 5)

    def test_chat_view_history_summary_updates_rows_without_refresh(self):
        row_updates = []
        refreshed = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _history_id_by_peer={"358566558": "306927744647171"},
            _unread_count_by_peer={},
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "离散数学"}],
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._apply_history_summary_unread = lambda subjects: ChatView._apply_history_summary_unread(view, subjects)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))
        view._refresh_session_list = lambda sessions=None: refreshed.append(True)

        ChatView._on_msync_message(
            view,
            {
                "event": "history_summary",
                "subjects": [{"subject": "358566558", "count": 0}],
            },
        )

        self.assertEqual(row_updates, [("358566558", "306927744647171", 0)])
        self.assertEqual(refreshed, [])

    def test_chat_view_history_summary_keeps_open_conversation_unread_at_zero(self):
        row_updates = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="306927744647171",
            _current_history_id="306927744647171",
            _history_id_by_peer={"358566558": "306927744647171"},
            _unread_count_by_peer={"358566558": 2, "306927744647171": 2},
            _locally_read_conversations=set(),
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "离散数学"}],
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._apply_history_summary_unread = lambda subjects: ChatView._apply_history_summary_unread(view, subjects)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))

        ChatView._on_msync_message(
            view,
            {
                "event": "history_summary",
                "subjects": [{"subject": "358566558", "count": 2}],
            },
        )

        self.assertEqual(view._unread_count_by_peer["358566558"], 0)
        self.assertEqual(row_updates, [("358566558", "306927744647171", 0)])

    def test_chat_view_history_summary_does_not_restore_locally_cleared_unread(self):
        row_updates = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="other-chat",
            _current_history_id="other-chat",
            _history_id_by_peer={"358566558": "306927744647171"},
            _unread_count_by_peer={"358566558": 0, "306927744647171": 0},
            _locally_read_conversations={"358566558", "306927744647171"},
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "离散数学"}],
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._apply_history_summary_unread = lambda subjects: ChatView._apply_history_summary_unread(view, subjects)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))

        ChatView._on_msync_message(
            view,
            {
                "event": "history_summary",
                "subjects": [{"subject": "358566558", "count": 3}],
            },
        )

        self.assertEqual(view._unread_count_by_peer["358566558"], 0)
        self.assertEqual(row_updates, [])

    def test_chat_view_realtime_row_update_preserves_existing_avatar_widget(self):
        class _FakeItem:
            def __init__(self):
                self._data = {}
                self.size_hint = None

            def data(self, role):
                return self._data.get(role)

            def setData(self, role, value):
                self._data[role] = value

            def setSizeHint(self, size_hint):
                self.size_hint = size_hint

        class _FakeWidget:
            def __init__(self):
                self.updated = []

            def update_display(self, name, time_str="", subtitle="", unread_count=0, session=None):
                self.updated.append({
                    "name": name,
                    "time_str": time_str,
                    "subtitle": subtitle,
                    "unread_count": unread_count,
                    "session": session,
                })

            def sizeHint(self):
                return "existing-size"

        class _FakeListWidget:
            def __init__(self, item, widget):
                self._item = item
                self._widget = widget
                self.replaced = []

            def count(self):
                return 1

            def item(self, index):
                return self._item if index == 0 else None

            def itemWidget(self, item):
                return self._widget if item is self._item else None

            def setItemWidget(self, item, widget):
                self.replaced.append((item, widget))

        item = _FakeItem()
        item.setData(Qt.ItemDataRole.UserRole, "peer-1")
        item.setData(Qt.ItemDataRole.UserRole + 3, "history-1")
        existing_widget = _FakeWidget()
        list_widget = _FakeListWidget(item, existing_widget)
        built_widget = SimpleNamespace(
            time_label=SimpleNamespace(text=lambda: "15:43"),
            sizeHint=lambda: "built-size",
        )
        built_session = {"chatId": "history-1", "chatName": "张三", "subtitle": "4.01计科3班", "updateTime": 123}
        view = SimpleNamespace(
            chat_list=list_widget,
            _suppress_avatar_refresh=True,
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._build_session_item_components = lambda session: (
            built_session,
            built_widget,
            "peer-1",
            "张三",
            "history-1",
            2,
            "https://photo.example/avatar.png",
        )

        updated = ChatView._update_session_row(view, "peer-1", "history-1", session=built_session)

        self.assertTrue(updated)
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole + 1), "张三")
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole + 2), built_session)
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole + 4), 2)
        self.assertEqual(item.size_hint, "existing-size")
        self.assertEqual(list_widget.replaced, [])
        self.assertEqual(
            existing_widget.updated,
            [{
                "name": "张三",
                "time_str": "15:43",
                "subtitle": "4.01计科3班",
                "unread_count": 2,
                "session": built_session,
            }],
        )

    def test_chat_view_resolve_session_peer_id_uses_history_mapping_for_groups(self):
        view = SimpleNamespace(
            _history_id_by_peer={"358566558": "306927744647171"},
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
        )
        view._resolve_peer_id_by_history_id = lambda history_id: ChatView._resolve_peer_id_by_history_id(view, history_id)

        peer_id = ChatView._resolve_session_peer_id(
            view,
            {"chatId": "306927744647171", "chatName": "离散数学"},
        )

        self.assertEqual(peer_id, "358566558")

    def test_chat_view_merge_session_metadata_applies_unread_count(self):
        view = SimpleNamespace(
            _session_meta_by_peer={},
            _unread_count_by_peer={"358566558": 3},
            _history_id_by_peer={"358566558": "306927744647171"},
        )
        view._resolve_session_peer_id = lambda session: str(session.get("chatId", "") or "")
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)

        merged = ChatView._merge_session_metadata(
            view,
            {"chatId": "306927744647171", "chatName": "离散数学", "updateTime": 1},
        )

        self.assertEqual(merged["unread_count"], 3)

    def test_chat_view_merge_session_metadata_replaces_stale_group_chat_id_with_real_history_id(self):
        view = SimpleNamespace(
            _session_meta_by_peer={"358566558": {"chatId": "306927744647171", "courseName": "离散数学（2025-2026-2）"}},
            _unread_count_by_peer={},
            _history_id_by_peer={"358566558": "306927744647171"},
        )
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)

        merged = ChatView._merge_session_metadata(
            view,
            {"chatId": "358566558", "chatName": "离散数学", "updateTime": 1},
        )

        self.assertEqual(merged["chatId"], "306927744647171")
        self.assertEqual(merged["courseName"], "离散数学（2025-2026-2）")

    def test_chat_view_resolve_session_history_id_prefers_preserved_history_key(self):
        history_id = ChatView._resolve_session_history_id(
            SimpleNamespace(),
            {"_historyKey": "306927744647171", "chatId": "358566558"},
        )

        self.assertEqual(history_id, "306927744647171")

    def test_chat_view_resolve_history_key_candidates_prefers_history_keys_before_peer(self):
        view = SimpleNamespace(
            _history_id_by_peer={"358566558": "306927744647171"},
            _session_meta_by_peer={"358566558": {"chatId": "306927744647171"}},
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._resolve_peer_id_by_history_id = lambda history_id: ChatView._resolve_peer_id_by_history_id(view, history_id)

        candidates = ChatView._resolve_history_key_candidates(
            view,
            session={"chatId": "358566558", "_historyKey": "100+chat-1"},
            peer_id="358566558",
            history_id="358566558",
        )

        self.assertEqual(candidates, ["100+chat-1", "306927744647171", "358566558"])

    def test_chat_view_on_read_ack_does_not_update_unread_count(self):
        row_updates = []
        view = SimpleNamespace(
            _pending_read_acks={},
            _history_id_by_peer={"25278974": "25278974"},
            _unread_count_by_peer={},
            _message_cache={},
            _raw_sessions=[{"chatId": "25278974", "chatName": "自己"}],
        )
        view._conversation_key = lambda: ""
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))

        ChatView._on_read_ack(
            view,
            {
                "message_id": "1549287205527104536",
                "timestamp": 1778286337275,
                "peer_id": "25278974/webim_1778286327053",
                "unread_count": 1,
            },
        )

        self.assertEqual(view._pending_read_acks["1549287205527104536"], 1778286337275)
        self.assertEqual(view._unread_count_by_peer, {})
        self.assertEqual(row_updates, [])

    def test_chat_view_on_read_ack_marks_self_messages_read_by_conversation_when_id_differs(self):
        rendered = []
        view = SimpleNamespace(
            _pending_read_acks={},
            _history_id_by_peer={"358572378": "history-1"},
            _unread_count_by_peer={},
            _message_cache={
                "history-1": [
                    {
                        "sender_id": "25278974",
                        "sender_name": "我",
                        "content": "hello",
                        "is_self": True,
                        "timestamp": 1000,
                        "message_id": "",
                        "read_state": "unread",
                        "read_at": 0,
                    }
                ]
            },
            _current_target_id="358572378",
            _current_history_id="history-1",
            _current_target_name="张三",
            _current_session_display_name="张三",
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._mark_previous_self_messages_read = lambda conversation_key, read_at=0: ChatView._mark_previous_self_messages_read(view, conversation_key, read_at)
        view._render_cached_messages = lambda conversation_key=None: rendered.append(conversation_key)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: None

        ChatView._on_read_ack(
            view,
            {
                "message_id": "1549287205527104536",
                "timestamp": 1778286337275,
                "peer_id": "358572378",
            },
        )

        self.assertEqual(view._message_cache["history-1"][0]["read_state"], "read")
        self.assertEqual(view._message_cache["history-1"][0]["read_at"], 1778286337275)
        self.assertEqual(rendered, ["history-1"])

    def test_chat_view_clear_current_unread_count_updates_row_without_refresh(self):
        row_updates = []
        refreshed = []
        view = SimpleNamespace(
            _current_target_id="25278974",
            _current_history_id="25278974",
            _history_id_by_peer={"25278974": "25278974"},
            _unread_count_by_peer={"25278974": 3},
            _raw_sessions=[{"chatId": "25278974", "chatName": "自己", "unread_count": 3}],
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))
        view._refresh_session_list = lambda sessions=None: refreshed.append(True)

        changed = ChatView._clear_current_unread_count(view)

        self.assertTrue(changed)
        self.assertEqual(view._unread_count_by_peer["25278974"], 0)
        self.assertEqual(row_updates, [("25278974", "25278974", 0)])
        self.assertEqual(refreshed, [])

    def test_chat_view_clear_current_unread_count_uses_history_mapping_for_group_peer(self):
        row_updates = []
        view = SimpleNamespace(
            _current_target_id="306927744647171",
            _current_history_id="306927744647171",
            _history_id_by_peer={"358566558": "306927744647171"},
            _unread_count_by_peer={"358566558": 2, "306927744647171": 2},
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "离散数学", "unread_count": 2}],
        )
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._update_session_unread_row = lambda peer_id="", history_id="", unread_count=0: row_updates.append((peer_id, history_id, unread_count))

        changed = ChatView._clear_current_unread_count(view)

        self.assertTrue(changed)
        self.assertEqual(view._unread_count_by_peer["358566558"], 0)
        self.assertEqual(view._unread_count_by_peer["306927744647171"], 0)
        self.assertEqual(row_updates, [("358566558", "306927744647171", 0)])

    def test_chat_view_on_messages_loaded_requests_unread_summary(self):
        requested = []
        view = SimpleNamespace(
            loading_hint=SimpleNamespace(hide=lambda: None),
            chat_list=SimpleNamespace(setEnabled=lambda enabled: None, clear=lambda: None, addItem=lambda item: None),
            _current_history_id=None,
            _current_target_id=None,
            _raw_sessions=[],
            _suppress_unread_summary_request=False,
            crawler=SimpleNamespace(request_history_summary_msync=lambda peer_ids: requested.append(peer_ids)),
        )
        view._merge_session_metadata = lambda session: session
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._request_unread_summary = lambda sessions: ChatView._request_unread_summary(view, sessions)
        view._add_session_item = lambda session: None
        view._restore_selected_chat = lambda chat_id: None

        ChatView._on_messages_loaded(
            view,
            [
                {"chatId": "358566558", "chatName": "离散数学", "updateTime": 2, "isGroup": 0},
                {"chatId": "358574049", "chatName": "另一个群", "updateTime": 1, "isGroup": 0},
            ],
        )

        self.assertEqual(requested, [["358566558", "358574049"]])

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

    def test_add_question_renders_sum_formula_option_without_float_resize_error(self):
        session = _FakeSession(_FakeResponse(payload={"status": True, "msg": "ok", "id": "q1"}))
        api = _FakeQuestionBankAPI(
            session,
            course_params={"courseid": "course-1", "clazzid": "class-1", "cpi": "cpi-1"},
        )

        with patch("core.rendering.katex_snapshot.KaTeXSnapshotRenderer.render_to_png", return_value=None):
            result = api.add_question(
                "folder-1",
                {
                    "content": "在无向图中，握手定理的公式是？",
                    "q_type": 0,
                    "options": [
                        {"key": "A", "value": "$∑d(v_i)=m$"},
                        {"key": "B", "value": "$∑d(v_i)=2m$"},
                    ],
                    "answer": "B",
                    "analysis": "",
                },
            )

        self.assertTrue(result["success"])
        self.assertIn("<img", session.calls[0]["data"]["A"])
        self.assertNotIn("$", session.calls[0]["data"]["A"])

    def test_katex_snapshot_reset_shared_view_clears_renderer_state(self):
        class _FakeView:
            def __init__(self):
                self.hidden = 0
                self.deleted = 0

            def hide(self):
                self.hidden += 1

            def deleteLater(self):
                self.deleted += 1

        fake_view = _FakeView()
        old_state = (
            KaTeXSnapshotRenderer._shared_view,
            KaTeXSnapshotRenderer._page_ready,
            KaTeXSnapshotRenderer._is_initializing,
            KaTeXSnapshotRenderer._render_in_progress,
        )
        try:
            KaTeXSnapshotRenderer._shared_view = fake_view
            KaTeXSnapshotRenderer._page_ready = True
            KaTeXSnapshotRenderer._is_initializing = True
            KaTeXSnapshotRenderer._render_in_progress = True

            KaTeXSnapshotRenderer._reset_shared_view()

            self.assertIsNone(KaTeXSnapshotRenderer._shared_view)
            self.assertFalse(KaTeXSnapshotRenderer._page_ready)
            self.assertFalse(KaTeXSnapshotRenderer._is_initializing)
            self.assertFalse(KaTeXSnapshotRenderer._render_in_progress)
            self.assertEqual(fake_view.hidden, 1)
            self.assertEqual(fake_view.deleted, 1)
        finally:
            (
                KaTeXSnapshotRenderer._shared_view,
                KaTeXSnapshotRenderer._page_ready,
                KaTeXSnapshotRenderer._is_initializing,
                KaTeXSnapshotRenderer._render_in_progress,
            ) = old_state

    def test_katex_snapshot_renderer_reloads_shared_page_after_failed_render(self):
        old_state = (
            KaTeXSnapshotRenderer._shared_view,
            KaTeXSnapshotRenderer._page_ready,
            KaTeXSnapshotRenderer._is_initializing,
            KaTeXSnapshotRenderer._render_in_progress,
        )
        try:
            KaTeXSnapshotRenderer._shared_view = object()
            KaTeXSnapshotRenderer._page_ready = True
            KaTeXSnapshotRenderer._is_initializing = False
            KaTeXSnapshotRenderer._render_in_progress = False

            fake_app = SimpleNamespace(processEvents=lambda: None)
            def _ensure_ready():
                KaTeXSnapshotRenderer._page_ready = True
                return True

            with patch("core.rendering.katex_snapshot.QApplication.instance", return_value=fake_app), \
                 patch.object(KaTeXSnapshotRenderer, "_ensure_shared_view_ready", side_effect=_ensure_ready) as ensure_mock, \
                 patch.object(KaTeXSnapshotRenderer, "_render_with_shared_view", side_effect=[None, (b'png', 12, 8)]) as render_mock:
                result = KaTeXSnapshotRenderer._render_to_png_in_gui_thread("x^2", display_mode=False)

            self.assertEqual(result, (b'png', 12, 8))
            self.assertEqual(ensure_mock.call_count, 2)
            self.assertEqual(render_mock.call_count, 2)
            self.assertTrue(KaTeXSnapshotRenderer._page_ready)
            self.assertFalse(KaTeXSnapshotRenderer._render_in_progress)
        finally:
            (
                KaTeXSnapshotRenderer._shared_view,
                KaTeXSnapshotRenderer._page_ready,
                KaTeXSnapshotRenderer._is_initializing,
                KaTeXSnapshotRenderer._render_in_progress,
            ) = old_state

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
                "student_id": "",
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

    def test_chat_view_load_group_members_uses_persisted_cache_file(self):
        room_id = "306927744647171"
        room_name = "离散数学（2025-2026-2）"
        class_name = "4.03计科2班、区块链1班"
        cache_name = f"{room_name}-{class_name}"
        members = [{
            "person_id": "25278974",
            "name": "郝玉锋",
            "student_id": "",
            "avatar_url": "http://photo.example/avatar.png",
            "tuid": "25278974",
            "puid": "30047383",
        }]
        rendered = []
        selected_tabs = []

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "group_members"
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_dir / f"{cache_name}.json", "w", encoding="utf-8") as f:
                json.dump(members, f, ensure_ascii=False, indent=2)

            view = SimpleNamespace(
                _current_group_room_id="",
                _current_group_room_name="",
                _current_group_cache_name="",
                _group_members_cache={},
                _group_name_by_room_id={},
                _group_cache_name_by_room_id={},
                _group_members_cache_dir=cache_dir,
                _group_members_worker=None,
                _pending_group_room_id="",
                student_tab=object(),
                tab_widget=SimpleNamespace(setCurrentWidget=lambda widget: selected_tabs.append(widget)),
            )
            view._resolve_group_room_id = lambda session: ChatView._resolve_group_room_id(view, session)
            view._resolve_group_room_name = lambda session: ChatView._resolve_group_room_name(view, session)
            view._resolve_group_cache_name = lambda session: ChatView._resolve_group_cache_name(view, session)
            view.set_students = lambda students: rendered.append(students)

            ChatView._load_group_members(view, {"roomId": room_id, "chatName": room_name, "subtitle": class_name})

            self.assertEqual(view._group_members_cache[room_id], members)
            self.assertEqual(rendered, [members])
            self.assertEqual(selected_tabs, [view.student_tab])

    def test_chat_view_group_members_are_persisted_after_successful_load(self):
        room_id = "306927744647171"
        room_name = "离散数学（2025-2026-2）"
        class_name = "4.03计科2班、区块链1班"
        cache_name = f"{room_name}-{class_name}"
        members = [{
            "person_id": "25278974",
            "name": "郝玉锋",
            "student_id": "",
            "avatar_url": "http://photo.example/avatar.png",
            "tuid": "25278974",
            "puid": "30047383",
        }]
        rendered = []
        selected_tabs = []

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "group_members"
            view = SimpleNamespace(
                _group_members_cache={},
                _group_members_cache_dir=cache_dir,
                _current_group_room_id=room_id,
                _current_group_room_name=room_name,
                _current_group_cache_name=cache_name,
                _group_name_by_room_id={room_id: room_name},
                _group_cache_name_by_room_id={room_id: cache_name},
                _pending_group_room_id="",
                student_tab=object(),
                tab_widget=SimpleNamespace(setCurrentWidget=lambda widget: selected_tabs.append(widget)),
            )
            view.set_students = lambda students: rendered.append(students)

            ChatView._on_group_members_loaded(view, room_id, members)

            cache_file = cache_dir / f"{cache_name}.json"
            self.assertTrue(cache_file.exists())
            with open(cache_file, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), members)
            self.assertEqual(rendered, [members])
            self.assertEqual(selected_tabs, [view.student_tab])

    def test_chat_view_refresh_current_group_members_clears_cache_and_reloads(self):
        room_id = "306927744647171"
        room_name = "离散数学（2025-2026-2）"
        class_name = "4.03计科2班、区块链1班"
        cache_name = f"{room_name}-{class_name}"
        started = []
        selected_tabs = []
        loading_calls = []

        class _FakeSignal:
            def __init__(self):
                self.callbacks = []

            def connect(self, callback):
                self.callbacks.append(callback)

        class _FakeGroupMembersWorker:
            def __init__(self, crawler, current_room_id):
                self.crawler = crawler
                self.room_id = current_room_id
                self.members_ready = _FakeSignal()
                self._running = False

            def isRunning(self):
                return self._running

            def start(self):
                started.append(self.room_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "group_members"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / f"{cache_name}.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump([{"person_id": "25278974", "name": "郝玉锋"}], f, ensure_ascii=False, indent=2)

            view = SimpleNamespace(
                crawler=SimpleNamespace(),
                _current_group_room_id=room_id,
                _current_group_room_name=room_name,
                _current_group_cache_name=cache_name,
                _group_members_cache={room_id: [{"person_id": "25278974", "name": "旧缓存"}], "other": [{"person_id": "1"}]},
                _group_name_by_room_id={room_id: room_name},
                _group_cache_name_by_room_id={room_id: cache_name},
                _group_members_cache_dir=cache_dir,
                _group_members_worker=None,
                _pending_group_room_id="",
                student_tab=object(),
                tab_widget=SimpleNamespace(setCurrentWidget=lambda widget: selected_tabs.append(widget)),
                _on_group_members_loaded=lambda *args, **kwargs: None,
            )
            view._show_group_members_loading = lambda: loading_calls.append(room_id)

            with patch("ui.views.chat_view.ChatGroupMembersWorker", _FakeGroupMembersWorker):
                ChatView._refresh_current_group_members(view)

            self.assertFalse(cache_file.exists())
            self.assertNotIn(room_id, view._group_members_cache)
            self.assertIn("other", view._group_members_cache)
            self.assertEqual(loading_calls, [room_id])
            self.assertEqual(started, [room_id])
            self.assertEqual(selected_tabs, [view.student_tab])

    def test_chat_view_group_cache_filename_uses_sanitized_group_name(self):
        cache_dir = Path("/tmp/group_members")
        view = SimpleNamespace(_group_members_cache_dir=cache_dir, _current_group_cache_name="")

        cache_file = ChatView._group_members_cache_file(view, "306927744647171", '离散数学:/2025*群聊?-4.03/计科2班')

        self.assertEqual(cache_file, cache_dir / "离散数学_2025_群聊_-4.03_计科2班.json")

    def test_chat_view_update_group_tab_title_formats_count(self):
        titles = []
        student_tab = object()
        tab_widget = SimpleNamespace(
            indexOf=lambda widget: 1 if widget is student_tab else -1,
            setTabText=lambda index, text: titles.append((index, text)),
        )
        view = SimpleNamespace(tab_widget=tab_widget, student_tab=student_tab)

        ChatView._update_group_tab_title(view, 105)

        self.assertEqual(titles, [(1, "群组(105)")])

    def test_chat_view_update_group_tab_title_hides_zero_count(self):
        titles = []
        student_tab = object()
        tab_widget = SimpleNamespace(
            indexOf=lambda widget: 1 if widget is student_tab else -1,
            setTabText=lambda index, text: titles.append((index, text)),
        )
        view = SimpleNamespace(tab_widget=tab_widget, student_tab=student_tab)

        ChatView._update_group_tab_title(view, 0)

        self.assertEqual(titles, [(1, "群组")])

    def test_study_status_table_style_sets_explicit_cross_platform_colors(self):
        class _FakeHeader:
            def __init__(self):
                self.default_size = None
                self.minimum_size = None

            def setDefaultSectionSize(self, size):
                self.default_size = size

            def setMinimumSectionSize(self, size):
                self.minimum_size = size

        class _FakeTable:
            def __init__(self):
                self.alternating = None
                self.word_wrap = None
                self.show_grid = None
                self.style_sheet = ""
                self.header = _FakeHeader()

            def setAlternatingRowColors(self, value):
                self.alternating = value

            def setWordWrap(self, value):
                self.word_wrap = value

            def setShowGrid(self, value):
                self.show_grid = value

            def setStyleSheet(self, value):
                self.style_sheet = value

            def verticalHeader(self):
                return self.header

        table = _FakeTable()
        view = SimpleNamespace()

        StudyStatusView._apply_stats_table_style(view, table)

        self.assertTrue(table.alternating)
        self.assertFalse(table.word_wrap)
        self.assertTrue(table.show_grid)
        self.assertIn("alternate-background-color: #252526;", table.style_sheet)
        self.assertIn("color: #e6e6e6;", table.style_sheet)
        self.assertEqual(table.header.default_size, 36)
        self.assertEqual(table.header.minimum_size, 32)

    def test_absence_stats_table_style_sets_explicit_cross_platform_colors(self):
        class _FakeHeader:
            def __init__(self):
                self.default_size = None
                self.minimum_size = None

            def setDefaultSectionSize(self, size):
                self.default_size = size

            def setMinimumSectionSize(self, size):
                self.minimum_size = size

        class _FakeTable:
            def __init__(self):
                self.alternating = None
                self.word_wrap = None
                self.show_grid = None
                self.style_sheet = ""
                self.header = _FakeHeader()

            def setAlternatingRowColors(self, value):
                self.alternating = value

            def setWordWrap(self, value):
                self.word_wrap = value

            def setShowGrid(self, value):
                self.show_grid = value

            def setStyleSheet(self, value):
                self.style_sheet = value

            def verticalHeader(self):
                return self.header

        table = _FakeTable()
        dialog = SimpleNamespace()

        AbsenceStatsDialog._apply_table_style(dialog, table)

        self.assertTrue(table.alternating)
        self.assertFalse(table.word_wrap)
        self.assertTrue(table.show_grid)
        self.assertIn("alternate-background-color: #252526;", table.style_sheet)
        self.assertIn("selection-color: #ffffff;", table.style_sheet)
        self.assertEqual(table.header.default_size, 36)
        self.assertEqual(table.header.minimum_size, 32)

    def test_resolve_student_from_group_cache_returns_unique_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "group_members"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = build_group_members_cache_path("离散数学（2025-2026-2）", "4.03计科2班、区块链1班", cache_dir=cache_dir)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {"name": "张三", "tuid": "1001", "puid": "3001"},
                        {"name": "李四", "tuid": "1002", "puid": "3002"},
                    ],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            resolved = resolve_student_from_group_cache("离散数学（2025-2026-2）", "4.03计科2班、区块链1班", "张三", cache_dir=cache_dir)

            self.assertEqual(resolved["status"], "success")
            self.assertEqual(resolved["matches"][0]["tuid"], "1001")
            self.assertEqual(resolved["cache_path"], cache_file)

    def test_resolve_student_from_group_cache_detects_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "group_members"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = build_group_members_cache_path("离散数学（2025-2026-2）", "4.03计科2班、区块链1班", cache_dir=cache_dir)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {"name": "张三", "tuid": "1001", "puid": "3001"},
                        {"name": "张三", "tuid": "1003", "puid": "3003"},
                    ],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            resolved = resolve_student_from_group_cache("离散数学（2025-2026-2）", "4.03计科2班、区块链1班", "张三", cache_dir=cache_dir)

            self.assertEqual(resolved["status"], "duplicate")
            self.assertEqual(len(resolved["matches"]), 2)

    def test_group_members_cache_normalization_keeps_puid_separate_from_student_id(self):
        from core.group_members_cache import _normalize_members

        members = _normalize_members([{"name": "张三", "tuid": "1001", "puid": "488064870"}])

        self.assertEqual(
            members,
            [{
                "person_id": "1001",
                "name": "张三",
                "student_id": "",
                "avatar_url": "",
                "tuid": "1001",
                "puid": "488064870",
            }],
        )

    def test_study_status_homework_message_click_opens_reusable_dialog_on_unique_match(self):
        opened = []

        class _FakeDialog:
            def __init__(self, crawler, student, on_send_success=None, parent=None):
                opened.append((crawler, student, on_send_success, parent))

            def exec(self):
                opened.append("exec")

        view = SimpleNamespace(
            crawler=SimpleNamespace(),
            _resolve_student_message_target=lambda student_name: {
                "status": "success",
                "matches": [{"name": student_name, "tuid": "1001", "student_id": "3001"}],
            },
            _mark_homework_student_communicated=lambda student_id: opened.append(("marked", student_id)),
        )

        with patch("ui.views.study_status_view.StudentMessageDialog", _FakeDialog):
            StudyStatusView._on_homework_message_clicked(view, SimpleNamespace(user_name="张三", alias_name="2023001001"))

        self.assertEqual(opened[0][1]["name"], "张三")
        self.assertTrue(callable(opened[0][2]))
        self.assertEqual(opened[1], "exec")
        opened[0][2]({"name": "张三"})
        self.assertEqual(opened[2], ("marked", "2023001001"))

    def test_study_status_homework_message_click_warns_on_duplicate_names(self):
        infos = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(),
            _resolve_student_message_target=lambda student_name: {
                "status": "duplicate",
                "matches": [{"name": student_name, "tuid": "1001"}, {"name": student_name, "tuid": "1002"}],
            },
        )

        with patch("ui.views.study_status_view.QMessageBox.information", side_effect=lambda *args: infos.append(args[1:3])):
            StudyStatusView._on_homework_message_clicked(view, SimpleNamespace(user_name="张三"))

        self.assertEqual(infos, [("存在重名学生", "张三 在群成员缓存中存在重名，请到“消息”模块中手动发送。")])

    def test_study_status_mark_homework_student_communicated_updates_storage_and_row(self):
        class _FakeItem:
            def __init__(self, student_id):
                self._student_id = student_id
                self.text_value = "☐"
                self.foreground = None

            def data(self, role):
                return self._student_id if role == Qt.ItemDataRole.UserRole else None

            def setText(self, value):
                self.text_value = value

            def setForeground(self, value):
                self.foreground = value

        item = _FakeItem("2023001001")
        view = SimpleNamespace(
            current_course_id="course-1",
            current_class_id="class-1",
            communication_manager=SimpleNamespace(set_status=lambda course_id, class_id, student_id, status: setattr(view, "_saved", (course_id, class_id, student_id, status))),
            homework_table=SimpleNamespace(
                rowCount=lambda: 1,
                item=lambda row, column: item if (row, column) == (0, 9) else None,
            ),
        )

        StudyStatusView._mark_homework_student_communicated(view, "2023001001")

        self.assertEqual(view._saved, ("course-1", "class-1", "2023001001", True))
        self.assertEqual(item.text_value, "☑")

    def test_study_status_renders_homework_reminder_placeholders(self):
        stats = SimpleNamespace(
            user_name="张三",
            alias_name="2023001001",
            complete_num=10,
            work_submitted=7,
            pending_count=1,
            unsubmitted_count=3,
        )

        message = StudyStatusView._render_homework_reminder_message(
            stats,
            "{student_name} {student_id} {total_count} {submitted_count} {pending_count} {unsubmitted_count}",
        )

        self.assertEqual(message, "张三 2023001001 10 7 1 3")

    def test_study_status_calculates_homework_reminder_threshold_from_total_count(self):
        stats_list = [
            SimpleNamespace(complete_num=10),
            SimpleNamespace(complete_num=8),
        ]

        threshold = StudyStatusView._calculate_homework_reminder_threshold(stats_list)

        self.assertEqual(threshold, 6)

    def test_study_status_homework_reminders_send_only_eligible_students_and_report_duplicates(self):
        infos = []
        sent = []
        marked = []
        busy = []
        progress_updates = []
        stats_list = [
            SimpleNamespace(
                user_name="张三",
                alias_name="2023001001",
                complete_num=10,
                work_submitted=7,
                pending_count=1,
                unsubmitted_count=3,
            ),
            SimpleNamespace(
                user_name="李四",
                alias_name="2023001002",
                complete_num=10,
                work_submitted=9,
                pending_count=0,
                unsubmitted_count=1,
            ),
            SimpleNamespace(
                user_name="王五",
                alias_name="2023001003",
                complete_num=10,
                work_submitted=6,
                pending_count=1,
                unsubmitted_count=4,
            ),
        ]
        view = SimpleNamespace(
            crawler=SimpleNamespace(),
            current_homework_data=stats_list,
            current_course_name="离散数学（2025-2026-2）",
            current_class_name="4.03计科2班、区块链1班",
            _set_homework_reminder_busy=lambda value: busy.append(value),
            _resolve_student_message_target=lambda student_name: {
                "张三": {"status": "success", "matches": [{"name": "张三", "tuid": "1001", "student_id": "2023001001"}]},
                "王五": {"status": "duplicate", "matches": [{"name": "王五", "tuid": "1003"}, {"name": "王五", "tuid": "1004"}]},
            }.get(student_name, {"status": "not_found", "matches": []}),
            _mark_homework_student_communicated=lambda student_id: marked.append(student_id),
        )
        view._format_homework_student_label = lambda stats: StudyStatusView._format_homework_student_label(stats)
        view._render_homework_reminder_message = lambda stats, template: StudyStatusView._render_homework_reminder_message(stats, template)
        
        class _FakeProgressDialog:
            def __init__(self, *args, **kwargs):
                pass

            def setWindowTitle(self, title):
                progress_updates.append(("title", title))

            def setWindowModality(self, modality):
                progress_updates.append(("modality", modality))

            def setMinimumDuration(self, duration):
                progress_updates.append(("duration", duration))

            def setAutoClose(self, value):
                progress_updates.append(("auto_close", value))

            def setAutoReset(self, value):
                progress_updates.append(("auto_reset", value))

            def setValue(self, value):
                progress_updates.append(("value", value))

            def setLabelText(self, text):
                progress_updates.append(("label", text))

            def show(self):
                progress_updates.append(("show", True))

            def close(self):
                progress_updates.append(("close", True))

        with patch("ui.views.study_status_view.StudentMessageDialog.send_student_message", side_effect=lambda crawler, student, content: sent.append((student, content)) or {"status": "success"}), patch("ui.views.study_status_view.QMessageBox.information", side_effect=lambda *args: infos.append(args[1:3])), patch("ui.views.study_status_view.QApplication.instance", return_value=None), patch("ui.views.study_status_view.QProgressDialog", _FakeProgressDialog):
            StudyStatusView._send_homework_reminders(
                view,
                3,
                "作业总数为:{total_count}，未提交为:{unsubmitted_count}",
            )

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0]["name"], "张三")
        self.assertEqual(sent[0][1], "作业总数为:10，未提交为:3")
        self.assertEqual(marked, ["2023001001"])
        self.assertEqual(busy, [True, False])
        self.assertEqual(infos[0][0], "提醒发送完成")
        self.assertIn("共筛选 2 名学生，成功发送 1 名。", infos[0][1])
        self.assertIn("王五（2023001003）：因学生重名，未自动发送提醒信息，请通过消息手动发送。", infos[0][1])
        self.assertIn(("label", "正在发送第 1/2 名学生：张三（2023001001）"), progress_updates)
        self.assertIn(("label", "正在发送第 2/2 名学生：王五（2023001003）"), progress_updates)
        self.assertIn(("close", True), progress_updates)

    def test_study_status_homework_reminder_click_uses_dialog_values(self):
        sent = []

        created = []

        class _FakeDialog:
            def __init__(self, threshold=1, message_template="", parent=None):
                created.append((threshold, message_template))
                self.threshold = 2
                self.message_template = "{student_name}"

            def exec(self):
                return 1

        view = SimpleNamespace(
            current_homework_data=[SimpleNamespace(complete_num=10)],
            _homework_reminder_threshold=1,
            _homework_reminder_template=DEFAULT_HOMEWORK_REMINDER_TEMPLATE,
            _send_homework_reminders=lambda threshold, template: sent.append((threshold, template)),
        )

        with patch("ui.views.study_status_view.HomeworkReminderDialog", _FakeDialog):
            StudyStatusView._on_homework_reminder_clicked(view)

        self.assertEqual(created[0][0], 6)
        self.assertEqual(sent, [(2, "{student_name}")])
        self.assertEqual(view._homework_reminder_threshold, 2)
        self.assertEqual(view._homework_reminder_template, "{student_name}")

    def test_study_status_clear_content_removes_nested_layout_widgets(self):
        deleted = []

        class _FakeWidget:
            def __init__(self, name):
                self.name = name

            def deleteLater(self):
                deleted.append(self.name)

        class _FakeItem:
            def __init__(self, widget=None, layout=None):
                self._widget = widget
                self._layout = layout

            def widget(self):
                return self._widget

            def layout(self):
                return self._layout

        class _FakeLayout:
            def __init__(self, items):
                self._items = list(items)

            def count(self):
                return len(self._items)

            def takeAt(self, index):
                return self._items.pop(index)

        nested_layout = _FakeLayout([_FakeItem(widget=_FakeWidget("reminder-button"))])
        content_layout = _FakeLayout([
            _FakeItem(widget=_FakeWidget("table")),
            _FakeItem(layout=nested_layout),
        ])
        view = SimpleNamespace(
            content_layout=content_layout,
            btn_homework_export=object(),
            btn_homework_reminder=object(),
        )
        view._delete_layout_item = lambda item: StudyStatusView._delete_layout_item(view, item)

        StudyStatusView.clear_content(view)

        self.assertEqual(deleted, ["table", "reminder-button"])
        self.assertIsNone(view.btn_homework_export)
        self.assertIsNone(view.btn_homework_reminder)

    def test_absence_stats_message_click_opens_reusable_dialog_on_unique_match(self):
        opened = []

        class _FakeDialog:
            def __init__(self, crawler, student, on_send_success=None, parent=None):
                opened.append((crawler, student, on_send_success, parent))

            def exec(self):
                opened.append("exec")

        dialog = SimpleNamespace(
            crawler=SimpleNamespace(),
            course_name="离散数学（2025-2026-2）",
            teaching_class_name="4.03计科2班、区块链1班",
            _resolve_student_message_target=lambda student_name: {
                "status": "success",
                "matches": [{"name": student_name, "tuid": "1001", "student_id": "3001"}],
            },
            _mark_student_communicated=lambda student_id: opened.append(("marked", student_id)),
        )

        with patch("ui.dialogs.absence_stats_dialog.StudentMessageDialog", _FakeDialog):
            AbsenceStatsDialog._on_message_clicked(dialog, {"name": "张三", "username": "2023001001"})

        self.assertEqual(opened[0][1]["name"], "张三")
        self.assertTrue(callable(opened[0][2]))
        self.assertEqual(opened[1], "exec")
        opened[0][2]({"name": "张三"})
        self.assertEqual(opened[2], ("marked", "2023001001"))

    def test_absence_stats_mark_student_communicated_updates_storage_and_row(self):
        class _FakeItem:
            def __init__(self, student_id):
                self._student_id = student_id
                self.text_value = "☐"
                self.foreground = None

            def data(self, role):
                return self._student_id if role == Qt.ItemDataRole.UserRole else None

            def setText(self, value):
                self.text_value = value

            def setForeground(self, value):
                self.foreground = value

        item = _FakeItem("2023001001")
        dialog = SimpleNamespace(
            course_id="course-1",
            class_id="class-1",
            communication_manager=SimpleNamespace(set_status=lambda course_id, class_id, student_id, status: setattr(dialog, "_saved", (course_id, class_id, student_id, status))),
            table=SimpleNamespace(
                rowCount=lambda: 1,
                item=lambda row, column: item if (row, column) == (0, 5) else None,
            ),
        )

        AbsenceStatsDialog._mark_student_communicated(dialog, "2023001001")

        self.assertEqual(dialog._saved, ("course-1", "class-1", "2023001001", True))
        self.assertEqual(item.text_value, "☑")

    def test_absence_stats_renders_reminder_placeholders(self):
        message = AbsenceStatsDialog._render_reminder_message(
            {
                "name": "张三",
                "username": "2023001001",
                "class_name": "1班",
                "absent_count": 3,
                "total_count": 9,
            },
            "{student_name} {student_id} {class_name} {total_count} {absent_count}",
        )

        self.assertEqual(message, "张三 2023001001 1班 9 3")

    def test_absence_stats_calculates_reminder_threshold_from_total_activities(self):
        self.assertEqual(AbsenceStatsDialog._calculate_reminder_threshold(9), 4)

    def test_absence_stats_reminders_send_only_eligible_students_and_report_duplicates(self):
        infos = []
        sent = []
        marked = []
        busy = []
        progress_updates = []
        dialog = SimpleNamespace(
            absence_stats={
                "1001": {"name": "张三", "username": "2023001001", "class_name": "1班", "absent_count": 3, "total_count": 9},
                "1002": {"name": "李四", "username": "2023001002", "class_name": "1班", "absent_count": 1, "total_count": 9},
                "1003": {"name": "王五", "username": "2023001003", "class_name": "1班", "absent_count": 4, "total_count": 9},
            },
            crawler=SimpleNamespace(),
            course_name="离散数学（2025-2026-2）",
            teaching_class_name="4.03计科2班、区块链1班",
            _set_reminder_busy=lambda value: busy.append(value),
            _resolve_student_message_target=lambda student_name: {
                "张三": {"status": "success", "matches": [{"name": "张三", "tuid": "1001", "student_id": "2023001001"}]},
                "王五": {"status": "duplicate", "matches": [{"name": "王五", "tuid": "1003"}, {"name": "王五", "tuid": "1004"}]},
            }.get(student_name, {"status": "not_found", "matches": []}),
            _mark_student_communicated=lambda student_id: marked.append(student_id),
        )
        dialog._format_student_label = lambda stats: AbsenceStatsDialog._format_student_label(stats)
        dialog._render_reminder_message = lambda stats, template: AbsenceStatsDialog._render_reminder_message(stats, template)

        class _FakeProgressDialog:
            def __init__(self, *args, **kwargs):
                pass

            def setWindowTitle(self, title):
                progress_updates.append(("title", title))

            def setWindowModality(self, modality):
                progress_updates.append(("modality", modality))

            def setMinimumDuration(self, duration):
                progress_updates.append(("duration", duration))

            def setAutoClose(self, value):
                progress_updates.append(("auto_close", value))

            def setAutoReset(self, value):
                progress_updates.append(("auto_reset", value))

            def setValue(self, value):
                progress_updates.append(("value", value))

            def setLabelText(self, text):
                progress_updates.append(("label", text))

            def show(self):
                progress_updates.append(("show", True))

            def close(self):
                progress_updates.append(("close", True))

        with patch("ui.dialogs.absence_stats_dialog.StudentMessageDialog.send_student_message", side_effect=lambda crawler, student, content: sent.append((student, content)) or {"status": "success"}), patch("ui.dialogs.absence_stats_dialog.QMessageBox.information", side_effect=lambda *args: infos.append(args[1:3])), patch("ui.dialogs.absence_stats_dialog.QApplication.instance", return_value=None), patch("ui.dialogs.absence_stats_dialog.QProgressDialog", _FakeProgressDialog):
            AbsenceStatsDialog._send_reminders(
                dialog,
                3,
                "总签到次数为:{total_count}，缺勤为:{absent_count}",
            )

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0]["name"], "张三")
        self.assertEqual(sent[0][1], "总签到次数为:9，缺勤为:3")
        self.assertEqual(marked, ["2023001001"])
        self.assertEqual(busy, [True, False])
        self.assertEqual(infos[0][0], "提醒发送完成")
        self.assertIn("共筛选 2 名学生，成功发送 1 名。", infos[0][1])
        self.assertIn("王五（2023001003）：因学生重名，未自动发送提醒信息，请通过消息手动发送。", infos[0][1])
        self.assertIn(("label", "正在发送第 1/2 名学生：张三（2023001001）"), progress_updates)
        self.assertIn(("label", "正在发送第 2/2 名学生：王五（2023001003）"), progress_updates)
        self.assertIn(("close", True), progress_updates)

    def test_absence_stats_reminder_click_uses_dialog_values(self):
        sent = []

        created = []

        class _FakeDialog:
            def __init__(self, threshold=1, message_template="", parent=None, **kwargs):
                created.append((threshold, message_template, kwargs))
                self.threshold = 2
                self.message_template = "{student_name}"
                self.kwargs = kwargs

            def exec(self):
                return 1

        dialog = SimpleNamespace(
            absence_stats={"1001": {"name": "张三", "username": "2023001001", "absent_count": 1, "total_count": 3}},
            total_activities=9,
            _reminder_threshold=1,
            _reminder_template=DEFAULT_ABSENCE_REMINDER_TEMPLATE,
            _send_reminders=lambda threshold, template: sent.append((threshold, template)),
        )

        with patch("ui.dialogs.absence_stats_dialog.HomeworkReminderDialog", _FakeDialog):
            AbsenceStatsDialog._on_reminder_clicked(dialog)

        self.assertEqual(created[0][0], 4)
        self.assertEqual(sent, [(2, "{student_name}")])
        self.assertEqual(dialog._reminder_threshold, 2)
        self.assertEqual(dialog._reminder_template, "{student_name}")

    def test_study_status_show_absence_stats_passes_message_dependencies(self):
        created = []

        class _FakeDialog:
            def __init__(self, absence_stats, total_activities, course_id, class_id, course_name="", teaching_class_name="", crawler=None, parent=None):
                created.append((absence_stats, total_activities, course_id, class_id, course_name, teaching_class_name, crawler, parent))

            def exec(self):
                created.append("exec")

        view = SimpleNamespace(
            _absence_dialog_open=False,
            current_course_id="course-1",
            current_class_id="class-1",
            current_course_name="离散数学（2025-2026-2）",
            current_class_name="4.03计科2班、区块链1班",
            current_attendance_data=[object(), object()],
            crawler=SimpleNamespace(),
            _set_absence_stats_busy=lambda busy: created.append(("busy", busy)),
            status_update=SimpleNamespace(emit=lambda text: created.append(("status", text))),
        )

        with patch("ui.dialogs.absence_stats_dialog.AbsenceStatsDialog", _FakeDialog):
            StudyStatusView._show_absence_stats(view, {"488064870": {"name": "张三", "username": "2023001001"}})

        self.assertEqual(created[0][2:7], ("course-1", "class-1", "离散数学（2025-2026-2）", "4.03计科2班、区块链1班", view.crawler))
        self.assertEqual(created[1], "exec")

    def test_student_message_dialog_waits_for_msync_connection(self):
        class _FakeCrawler:
            def __init__(self):
                self.connect_calls = 0
                self._checks = 0

            def is_msync_connected(self):
                self._checks += 1
                return self._checks >= 3

            def connect_msync(self, listener_key=None):
                self.connect_calls += 1
                return SimpleNamespace()

        dialog = SimpleNamespace(crawler=_FakeCrawler())

        with patch("ui.dialogs.student_message_dialog.time.sleep", lambda _: None), patch("ui.dialogs.student_message_dialog.QApplication.instance", return_value=None):
            self.assertTrue(StudentMessageDialog._ensure_connected(dialog, timeout=0.3, interval=0.01))

        self.assertEqual(dialog.crawler.connect_calls, 1)

    def test_student_message_dialog_fails_when_msync_never_connects(self):
        class _FakeCrawler:
            def __init__(self):
                self.connect_calls = 0

            def is_msync_connected(self):
                return False

            def connect_msync(self, listener_key=None):
                self.connect_calls += 1
                return SimpleNamespace()

        dialog = SimpleNamespace(crawler=_FakeCrawler())

        with patch("ui.dialogs.student_message_dialog.time.sleep", lambda _: None), patch("ui.dialogs.student_message_dialog.QApplication.instance", return_value=None):
            self.assertFalse(StudentMessageDialog._ensure_connected(dialog, timeout=0.05, interval=0.01))

        self.assertEqual(dialog.crawler.connect_calls, 1)

    def test_student_message_dialog_uses_puid_label_instead_of_student_id_label(self):
        lines = StudentMessageDialog._build_info_lines(
            {"name": "张三", "student_id": "", "puid": "488064870", "tuid": "1001"}
        )

        self.assertIn("PUID：488064870", lines)
        self.assertNotIn("学号：488064870", lines)

    def test_communication_manager_stores_status_by_real_student_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CommunicationManager(data_dir=tmpdir)

            manager.set_status("course-1", "class-1", "2023001001", True)

            self.assertTrue(manager.get_status("course-1", "class-1", "2023001001"))
            with open(Path(tmpdir) / "communication_status.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data, {"course-1_class-1": {"2023001001": True}})

    def test_homework_export_rows_use_alias_name_for_communication_lookup(self):
        from core.exporters.homework_stats_exporter import _build_rows

        calls = []
        rows = list(_build_rows(
            stats_list=[SimpleNamespace(
                alias_name="2023001001",
                user_name="张三",
                complete_num=10,
                work_submitted=8,
                pending_count=1,
                unsubmitted_count=2,
                real_avg_score=88.5,
                min_score=60.0,
                max_score=99.0,
            )],
            course_id="course-1",
            class_id="class-1",
            communication_status_getter=lambda course_id, class_id, student_id: calls.append((course_id, class_id, student_id)) or False,
        ))

        self.assertEqual(calls, [("course-1", "class-1", "2023001001")])
        self.assertEqual(rows[0][0], "2023001001")

    def test_absence_export_rows_use_username_for_communication_lookup(self):
        from core.exporters.absence_stats_exporter import _build_rows

        calls = []
        rows = list(_build_rows(
            absence_stats={"488064870": {"name": "张三", "username": "2023001001", "class_name": "1班", "absent_count": 2, "total_count": 5}},
            total_activities=5,
            course_id="course-1",
            class_id="class-1",
            communication_status_getter=lambda course_id, class_id, student_id: calls.append((course_id, class_id, student_id)) or False,
        ))

        self.assertEqual(calls, [("course-1", "class-1", "2023001001")])
        self.assertEqual(rows[0][1], "2023001001")

    def test_study_status_absence_stats_ignores_rapid_repeat_clicks(self):
        started = []

        class _FakeSignal:
            def __init__(self):
                self.callbacks = []

            def connect(self, callback):
                self.callbacks.append(callback)

        class _FakeAbsenceWorker:
            def __init__(self, crawler, attendance_data, course_id, class_id):
                self.crawler = crawler
                self.attendance_data = attendance_data
                self.course_id = course_id
                self.class_id = class_id
                self.stats_ready = _FakeSignal()
                self.finished = _FakeSignal()

            def start(self):
                started.append((self.course_id, self.class_id))

        button_states = []
        status_updates = []
        button = SimpleNamespace(
            setEnabled=lambda enabled: button_states.append(("enabled", enabled)),
            setText=lambda text: button_states.append(("text", text)),
        )
        view = SimpleNamespace(
            current_attendance_data=[object()],
            _absence_stats_loading=False,
            _absence_dialog_open=False,
            crawler=SimpleNamespace(),
            current_course_id="course-1",
            current_class_id="class-1",
            btn_absence_stats=button,
            status_update=SimpleNamespace(emit=lambda text: status_updates.append(text)),
        )
        view._set_absence_stats_busy = lambda busy: StudyStatusView._set_absence_stats_busy(view, busy)
        view._show_absence_stats = lambda result: StudyStatusView._show_absence_stats(view, result)
        view._on_absence_stats_worker_finished = lambda: StudyStatusView._on_absence_stats_worker_finished(view)

        with patch("ui.views.study_status_view.AbsenceStatsWorker", _FakeAbsenceWorker):
            StudyStatusView._on_absence_stats_clicked(view)
            StudyStatusView._on_absence_stats_clicked(view)

        self.assertEqual(started, [("course-1", "class-1")])
        self.assertTrue(view._absence_stats_loading)
        self.assertIn(("enabled", False), button_states)
        self.assertIn(("text", "统计中..."), button_states)

    def test_study_status_attendance_click_stores_course_name_for_absence_messaging(self):
        class _FakeCourse:
            id = "course-1"

        class _FakeMainWindow:
            class _Box:
                def __init__(self, data, text):
                    self._data = data
                    self._text = text

                def currentData(self):
                    return self._data

                def currentText(self):
                    return self._text

            def __init__(self):
                self.course_box = self._Box(_FakeCourse(), "离散数学（2025-2026-2）")
                self.clazz_box = self._Box("class-1", "4.01计科3班、4班")

        view = SimpleNamespace(
            _highlight_button=lambda button: None,
            btn_attendance=object(),
            status_update=SimpleNamespace(emit=lambda text: None),
            _show_loading=lambda text: None,
            _display_attendance=lambda result: None,
            window=lambda: _FakeMainWindow(),
            crawler=SimpleNamespace(),
        )

        with patch("ui.main_window.MainWindow", _FakeMainWindow), patch("ui.views.study_status_view.AttendanceWorker", lambda crawler: SimpleNamespace(attendance_ready=SimpleNamespace(connect=lambda callback: None), start=lambda: None)):
            StudyStatusView.on_attendance_clicked(view)

        self.assertEqual(view.current_course_id, "course-1")
        self.assertEqual(view.current_course_name, "离散数学（2025-2026-2）")
        self.assertEqual(view.current_class_id, "class-1")
        self.assertEqual(view.current_class_name, "4.01计科3班、4班")

    def test_numeric_table_widget_item_sorts_by_number_not_text(self):
        high = NumericTableWidgetItem("100.00", 100.0)
        low = NumericTableWidgetItem("9.50", 9.5)

        self.assertFalse(high < low)
        self.assertTrue(low < high)

    def test_study_status_quiz_shows_development_placeholder(self):
        placeholders = []
        statuses = []
        highlighted = []
        button = object()
        view = SimpleNamespace(
            _highlight_button=lambda current: highlighted.append(current),
            btn_quiz=button,
            status_update=SimpleNamespace(emit=lambda text: statuses.append(text)),
            _show_placeholder=lambda text: placeholders.append(text),
        )

        StudyStatusView.on_quiz_clicked(view)

        self.assertEqual(view.last_sub, "quiz")
        self.assertEqual(highlighted, [button])
        self.assertEqual(statuses, ["测验情况功能开发中"])
        self.assertEqual(placeholders, ["🚧 测验情况功能开发中，敬请期待"])

    def test_study_status_midterm_shows_development_placeholder(self):
        placeholders = []
        statuses = []
        highlighted = []
        button = object()
        view = SimpleNamespace(
            _highlight_button=lambda current: highlighted.append(current),
            btn_midterm=button,
            status_update=SimpleNamespace(emit=lambda text: statuses.append(text)),
            _show_placeholder=lambda text: placeholders.append(text),
        )

        StudyStatusView.on_midterm_clicked(view)

        self.assertEqual(view.last_sub, "midterm")
        self.assertEqual(highlighted, [button])
        self.assertEqual(statuses, ["期中考试功能开发中"])
        self.assertEqual(placeholders, ["🚧 期中考试功能开发中，敬请期待"])

    def test_assign_clazz_to_teachers_uses_update_classassign_endpoint(self):
        class _FakeTeacherAPI(TeacherAPI):
            def __init__(self):
                self._session = _FakeSession(_FakeResponse(payload={"status": True}))
                self.session_manager = SimpleNamespace(course_params={"cpi": "888"})

            @property
            def session(self):
                return self._session

        api = _FakeTeacherAPI()

        success, message = api.assign_clazz_to_teachers("course-1", "class-1", ["1001", "1002"])

        self.assertTrue(success)
        self.assertEqual(message, "成功分配班级给 2 名教师")
        self.assertEqual(api.session.calls[0]["url"], "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/update-classassign")
        self.assertEqual(
            api.session.calls[0]["params"],
            {
                "courseid": "course-1",
                "clazzid": "class-1",
                "cpi": "888",
                "assigneds": "1001,1002,",
            },
        )

    def test_activities_view_build_publish_params_uses_face_checkbox_state(self):
        class _FakeCheckBox:
            def __init__(self, checked):
                self._checked = checked

            def isChecked(self):
                return self._checked

        class _FakeComboBox:
            def __init__(self, data):
                self._data = data

            def currentData(self):
                return self._data

        view = SimpleNamespace(
            chk_need_vcode=_FakeCheckBox(False),
            chk_need_face=_FakeCheckBox(True),
            chk_enable_location=_FakeCheckBox(False),
            combo_refresh_time=_FakeComboBox(30),
        )

        params = ActivitiesView._build_publish_params(
            view,
            {
                "name": "1-1",
                "courseId": "course-1",
                "classId": "class-1",
                "planId": "plan-1",
                "signcode": "ABCDE",
            },
        )

        self.assertEqual(params["ifNeedVCode"], 0)
        self.assertEqual(params["openCheckFaceFlag"], 1)
        self.assertEqual(params["ewmRefreshTime"], 30)
        self.assertEqual(params["ifopenAddress"], "0")

    def test_attendance_detail_from_dict_preserves_signed_and_unsigned_lists(self):
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "已签学生", "username": "2025001", "status": 1, "submittime": "2026-05-12 13:50:45"},
                ],
                "weiqianList": [
                    {"id": 2, "uid": 11, "activeId": 100, "name": "未签学生", "username": "2025002", "status": 0},
                ],
            }
        )

        stats = detail.get_statistics()

        self.assertEqual(len(detail.signed_records), 1)
        self.assertEqual(len(detail.unsigned_records), 1)
        self.assertEqual(detail.signed_records[0].name, "已签学生")
        self.assertEqual(detail.signed_records[0].status_name, "已签")
        self.assertEqual(detail.unsigned_records[0].name, "未签学生")
        self.assertEqual(stats["已签"], 1)
        self.assertEqual(stats["未签"], 1)
        self.assertEqual(stats["代签"], 0)

    def test_attendance_detail_statistics_unsign_excludes_leave_records(self):
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [],
                "weiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "未签学生", "username": "2025001", "status": 0},
                    {"id": 2, "uid": 11, "activeId": 100, "name": "事假学生", "username": "2025002", "status": 8},
                    {"id": 3, "uid": 12, "activeId": 100, "name": "病假学生", "username": "2025003", "status": 7},
                ],
            }
        )

        stats = detail.get_statistics()

        self.assertEqual(stats["未签"], 1)
        self.assertEqual(stats["事假"], 1)
        self.assertEqual(stats["病假"], 1)

    def test_attendance_detail_filter_matches_partial_name_and_username(self):
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "张三", "username": "2025001", "status": 1},
                    {"id": 2, "uid": 11, "activeId": 100, "name": "李四", "username": "1203456", "status": 1},
                ],
                "weiqianList": [],
            }
        )
        dialog = SimpleNamespace(
            detail=detail,
            search_input=SimpleNamespace(text=lambda: "张"),
            _records_for_tab_key=lambda tab_key: AttendanceDetailDialog._records_for_tab_key(dialog, tab_key),
            _search_query=lambda: AttendanceDetailDialog._search_query(dialog),
            _record_matches_query=lambda record, query: AttendanceDetailDialog._record_matches_query(dialog, record, query),
        )

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        name_matches = AttendanceDetailDialog._filtered_records_for_tab_key(dialog, "signed")
        dialog.search_input = SimpleNamespace(text=lambda: "203")
        username_matches = AttendanceDetailDialog._filtered_records_for_tab_key(dialog, "signed")

        self.assertEqual([record.name for record in name_matches], ["张三"])
        self.assertEqual([record.name for record in username_matches], ["李四"])

    def test_attendance_detail_update_record_status_moves_record_between_tabs(self):
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "已签学生", "username": "2025001", "status": 1},
                ],
                "weiqianList": [
                    {"id": 2, "uid": 11, "activeId": 100, "name": "未签学生", "username": "2025002", "status": 0},
                ],
            }
        )

        changed = detail.update_record_status(10, 5)

        self.assertTrue(changed)
        self.assertEqual(len(detail.signed_records), 0)
        self.assertEqual(len(detail.unsigned_records), 2)
        self.assertEqual(detail.unsigned_records[0].uid, 10)
        self.assertEqual(detail.unsigned_records[0].status_name, "缺勤")
        self.assertTrue(detail.unsigned_records[0].submit_time)

    def test_update_attendance_status_posts_expected_payload(self):
        class _FakeActivityAPI(ActivityAPI):
            def __init__(self):
                self._session = _FakeSession(_FakeResponse(payload={"state": "success"}))
                self.session_manager = SimpleNamespace(course_params={"courseid": "course-1", "clazzid": "class-1", "fid": "4311", "cpi": "cpi-1"})

            @property
            def session(self):
                return self._session

        api = _FakeActivityAPI()

        success, message = api.update_attendance_status("active-1", 406811774, 5)

        self.assertTrue(success)
        self.assertEqual(message, "状态修改成功")
        self.assertEqual(
            api.session.calls[0],
            {
                "url": "https://mobilelearn.chaoxing.com/pptSign/updateSignStatusByUidsV2?DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId&activeId=active-1",
                "params": {},
                "headers": {
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": "https://mobilelearn.chaoxing.com",
                    "Referer": "https://mobilelearn.chaoxing.com/page/sign/endSign?courseId=course-1&classId=class-1&activeId=active-1&fid=4311&cpi=cpi-1&showOnScreenShare=true&returnType=1",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                },
                "data": {"uids": "406811774", "status": "5", "remark": ""},
                "timeout": 10,
                "method": "POST",
            },
        )

    def test_activities_view_load_attendance_detail_starts_worker(self):
        statuses = []

        class _FakeSignal:
            def __init__(self):
                self.callbacks = []

            def connect(self, callback):
                self.callbacks.append(callback)

        class _FakeWorker:
            instances = []

            def __init__(self, crawler, active_id):
                self.crawler = crawler
                self.active_id = active_id
                self.detail_ready = _FakeSignal()
                self.started = False
                _FakeWorker.instances.append(self)

            def start(self):
                self.started = True

        view = SimpleNamespace(crawler=object(), status_callback=lambda text: statuses.append(text), workers=[])
        activity = SimpleNamespace(title="签到1", active_id="active-1")

        with patch("ui.views.activities_view.AttendanceDetailWorker", _FakeWorker):
            ActivitiesView._load_attendance_detail(view, activity)

        self.assertEqual(statuses, ["正在加载 签到1 的签到详情..."])
        self.assertEqual(len(view.workers), 1)
        self.assertEqual(_FakeWorker.instances[0].active_id, "active-1")
        self.assertTrue(_FakeWorker.instances[0].started)
        self.assertEqual(len(_FakeWorker.instances[0].detail_ready.callbacks), 2)

    def test_activities_view_source_contains_active_sign_detail_button(self):
        activities_view_source = Path("/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong/ui/views/activities_view.py").read_text(encoding="utf-8")
        self.assertIn('detail_btn = QPushButton("签到详情")', activities_view_source)
        self.assertIn("card.mousePressEvent = lambda event, a=act: self._handle_active_card_click(event, a)", activities_view_source)

    def test_activities_view_show_attendance_detail_shows_warning_on_error(self):
        warnings = []
        statuses = []
        view = SimpleNamespace(status_callback=lambda text: statuses.append(text))

        with patch("ui.views.activities_view.QMessageBox.warning", side_effect=lambda *args: warnings.append(args[1:3])):
            ActivitiesView._show_attendance_detail(view, SimpleNamespace(title="签到1"), "网络错误")

        self.assertEqual(warnings, [("加载失败", "获取签到详情失败：\n网络错误")])
        self.assertEqual(statuses, ["签到详情加载失败"])

    def test_activities_view_active_card_click_opens_qrcode_on_left_click(self):
        shown = []
        view = SimpleNamespace(_show_qrcode=lambda act: shown.append(act))
        act = SimpleNamespace(title="签到1")

        class _FakeEvent:
            def button(self):
                return Qt.MouseButton.LeftButton

        ActivitiesView._handle_active_card_click(view, _FakeEvent(), act)

        self.assertEqual(shown, [act])

    def test_attendance_detail_dialog_status_update_sets_local_current_time(self):
        refreshed = []
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "已签学生", "username": "2025001", "status": 1, "submittime": "2026-05-12 13:50:45"},
                ],
                "weiqianList": [],
            }
        )
        dialog = SimpleNamespace(
            detail=detail,
            setEnabled=lambda enabled: refreshed.append(("enabled", enabled)),
            _refresh_tables=lambda preferred_uid="": refreshed.append(("refresh", preferred_uid)),
            _status_worker=None,
            _pending_selection_uid="",
        )

        with patch("ui.dialogs.attendance_detail_dialog.QApplication.restoreOverrideCursor", lambda: refreshed.append(("cursor", None))), \
             patch("ui.dialogs.attendance_detail_dialog.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-05-12 14:00:00"
            from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

            AttendanceDetailDialog._on_status_update_finished(dialog, True, "ok", 10, 5)

        self.assertEqual(dialog.detail.unsigned_records[0].submit_time, "2026-05-12 14:00:00")
        self.assertEqual(dialog.detail.unsigned_records[0].status_name, "缺勤")
        self.assertIn(("refresh", ""), refreshed)
        self.assertIn(("enabled", True), refreshed)

    def test_attendance_detail_dialog_apply_selection_defaults_to_first_record(self):
        actions = []

        class _FakeTable:
            def setFocus(self):
                actions.append(("focus",))

            def setCurrentCell(self, row, col):
                actions.append(("current", row, col))

            def selectRow(self, row):
                actions.append(("select", row))

        dialog = SimpleNamespace(
            tabs=SimpleNamespace(setCurrentIndex=lambda index: actions.append(("tab", index))),
            _tables={"signed": _FakeTable(), "unsigned": _FakeTable()},
            detail=AttendanceDetail.from_dict(
                {
                    "yiqianList": [{"id": 1, "uid": 10, "activeId": 100, "name": "A", "username": "1", "status": 1}],
                    "weiqianList": [{"id": 2, "uid": 11, "activeId": 100, "name": "B", "username": "2", "status": 0}],
                }
            ),
            _pending_selection_uid="",
        )
        dialog._records_for_tab_key = lambda tab_key: AttendanceDetailDialog._records_for_tab_key(dialog, tab_key)
        dialog._filtered_records_for_tab_key = lambda tab_key: AttendanceDetailDialog._filtered_records_for_tab_key(dialog, tab_key)
        dialog._select_record_by_uid = lambda uid: AttendanceDetailDialog._select_record_by_uid(dialog, uid)
        dialog._search_query = lambda: ""
        dialog._select_first_record = lambda preferred_tab_key="": AttendanceDetailDialog._select_first_record(dialog, preferred_tab_key)
        dialog._focus_record = lambda tab_key, row: AttendanceDetailDialog._focus_record(dialog, tab_key, row)

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        AttendanceDetailDialog._apply_selection(dialog)

        self.assertEqual(actions, [("tab", 0), ("focus",), ("current", 0, 0), ("select", 0)])

    def test_attendance_detail_search_button_refresh_prefers_current_tab_first_result(self):
        refreshed = []
        dialog = SimpleNamespace(
            search_input=SimpleNamespace(text=lambda: "203"),
            tabs=SimpleNamespace(count=lambda: 2, currentIndex=lambda: 1),
            _refresh_tables=lambda preferred_uid="", preferred_tab_key="": refreshed.append((preferred_uid, preferred_tab_key)),
            _tab_key_for_index=lambda index: "signed" if index == 0 else "unsigned",
        )

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        AttendanceDetailDialog._execute_search(dialog)

        self.assertEqual(dialog._active_search_query, "203")
        self.assertEqual(refreshed, [("", "unsigned")])

    def test_attendance_detail_search_clear_restores_all_records(self):
        refreshed = []
        dialog = SimpleNamespace(
            _active_search_query="203",
            tabs=SimpleNamespace(count=lambda: 2, currentIndex=lambda: 0),
            _refresh_tables=lambda preferred_uid="", preferred_tab_key="": refreshed.append((preferred_uid, preferred_tab_key)),
            _tab_key_for_index=lambda index: "signed" if index == 0 else "unsigned",
        )

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        AttendanceDetailDialog._on_search_text_changed(dialog, "")

        self.assertEqual(dialog._active_search_query, "")
        self.assertEqual(refreshed, [("", "signed")])

    def test_attendance_detail_dialog_source_contains_tab_row_search_button(self):
        dialog_source = Path("/Volumes/Hao/Users/hao/Documents/hao/sias/xuexitong/ui/dialogs/attendance_detail_dialog.py").read_text(encoding="utf-8")

        self.assertIn('self.search_btn = QPushButton("搜索")', dialog_source)
        self.assertIn("self.tabs.setCornerWidget(search_container, Qt.Corner.TopRightCorner)", dialog_source)
        self.assertIn("font-size: 12px;", dialog_source)
        self.assertIn("self.search_input.textChanged.connect(self._on_search_text_changed)", dialog_source)

    def test_attendance_detail_dialog_status_update_selects_next_record(self):
        refreshed = []
        detail = AttendanceDetail.from_dict(
            {
                "yiqianList": [
                    {"id": 1, "uid": 10, "activeId": 100, "name": "A", "username": "1", "status": 1, "submittime": "2026-05-12 13:50:45"},
                    {"id": 2, "uid": 11, "activeId": 100, "name": "B", "username": "2", "status": 1, "submittime": "2026-05-12 13:51:00"},
                ],
                "weiqianList": [],
            }
        )
        dialog = SimpleNamespace(
            detail=detail,
            setEnabled=lambda enabled: refreshed.append(("enabled", enabled)),
            _refresh_tables=lambda preferred_uid="": refreshed.append(("refresh", preferred_uid)),
            _apply_selection=lambda: refreshed.append(("fallback", None)),
            _status_worker=None,
            _pending_selection_uid="11",
        )

        with patch("ui.dialogs.attendance_detail_dialog.QApplication.restoreOverrideCursor", lambda: refreshed.append(("cursor", None))), \
             patch("ui.dialogs.attendance_detail_dialog.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2026-05-12 14:00:00"
            from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

            AttendanceDetailDialog._on_status_update_finished(dialog, True, "ok", 10, 5)

        self.assertEqual(dialog.detail.unsigned_records[0].submit_time, "2026-05-12 14:00:00")
        self.assertIn(("refresh", "11"), refreshed)

    def test_attendance_detail_dialog_activate_record_ignores_out_of_range_rows(self):
        table = SimpleNamespace(property=lambda _name: "signed")
        dialog = SimpleNamespace(
            _filtered_records_for_tab_key=lambda _tab_key: [SimpleNamespace(uid=1)],
        )

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        AttendanceDetailDialog._activate_record(dialog, table, -1)
        AttendanceDetailDialog._activate_record(dialog, table, 5)

    def test_attendance_detail_dialog_enter_activates_focused_row(self):
        activated = []
        table = SimpleNamespace(currentRow=lambda: 2)
        dialog = SimpleNamespace(
            _tables={"signed": table},
            focusWidget=lambda: table,
            _activate_record=lambda current_table, row: activated.append((current_table, row)),
        )

        class _FakeEvent:
            def __init__(self):
                self.accepted = False

            def key(self):
                return Qt.Key.Key_Return

            def accept(self):
                self.accepted = True

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        event = _FakeEvent()
        with patch("PyQt6.QtWidgets.QDialog.keyPressEvent", lambda *args, **kwargs: None):
            AttendanceDetailDialog.keyPressEvent(dialog, event)

        self.assertEqual(activated, [(table, 2)])
        self.assertTrue(event.accepted)

    def test_attendance_detail_dialog_tab_change_selects_first_record_in_tab(self):
        selected = []
        dialog = SimpleNamespace(
            _select_first_record_in_tab=lambda tab_key: selected.append(tab_key),
        )

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        AttendanceDetailDialog._on_tab_changed(dialog, 0)
        AttendanceDetailDialog._on_tab_changed(dialog, 1)
        AttendanceDetailDialog._on_tab_changed(dialog, 2)

        self.assertEqual(selected, ["signed", "unsigned"])

    def test_attendance_status_edit_dialog_signed_option_maps_to_status_one(self):
        from PyQt6.QtWidgets import QApplication
        from ui.dialogs.attendance_detail_dialog import AttendanceStatusEditDialog

        app = QApplication.instance() or QApplication([])
        dialog = AttendanceStatusEditDialog(
            SimpleNamespace(name="张三", username="2025001", status=0, status_name="未签")
        )

        dialog.shortcut_buttons["1"].setChecked(True)

        self.assertEqual(dialog.selected_status, 1)
        dialog.deleteLater()

    def test_attendance_detail_dialog_unsigned_signed_submits_status_two(self):
        dialog = SimpleNamespace()

        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        self.assertEqual(AttendanceDetailDialog._resolve_submitted_status(dialog, "unsigned", 1), 2)
        self.assertEqual(AttendanceDetailDialog._resolve_submitted_status(dialog, "signed", 1), 1)
        self.assertEqual(AttendanceDetailDialog._resolve_submitted_status(dialog, "unsigned", 5), 5)

    def test_attendance_detail_close_button_has_no_focus(self):
        from PyQt6.QtWidgets import QApplication
        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog

        app = QApplication.instance() or QApplication([])
        dialog = AttendanceDetailDialog(
            crawler=object(),
            activity=SimpleNamespace(title="签到1", time_range="t", create_time="c", active_id="a"),
            detail=AttendanceDetail.from_dict({"yiqianList": [], "weiqianList": []}),
        )

        self.assertEqual(dialog.close_btn.focusPolicy(), Qt.FocusPolicy.NoFocus)
        dialog.deleteLater()

    def test_refresh_qrcode_parses_enc_and_sign_code(self):
        class _FakeActivityAPI(ActivityAPI):
            def __init__(self):
                self._session = _FakeSession(_FakeResponse(payload={"result": 1, "data": {"enc": "ENC123", "signCode": "ABCDE"}}))

            @property
            def session(self):
                return self._session

        api = _FakeActivityAPI()

        success, message, enc, sign_code = api.refresh_qrcode("active-1")

        self.assertTrue(success)
        self.assertEqual(message, "获取成功")
        self.assertEqual(enc, "ENC123")
        self.assertEqual(sign_code, "ABCDE")
        self.assertEqual(api.session.calls[0]["params"]["activeId"], "active-1")

    def test_qrcode_dialog_builds_chaoxing_sign_url(self):
        self.assertEqual(
            QRCodeDialog._build_qr_url("12345", "ENC123", "ABCDE"),
            "https://mobilelearn.chaoxing.com/widget/sign/e?id=12345&c=ABCDE&enc=ENC123&DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=id",
        )
        self.assertEqual(
            QRCodeDialog._build_qr_url("12345", "ENC123", ""),
            "https://mobilelearn.chaoxing.com/widget/sign/e?id=12345&c=12345&enc=ENC123&DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=id",
        )

    def test_msync_batch_message_keeps_device_resources(self):
        frame = base64.b64decode(
            "CABAAErCAwoCCAAingMI3JiA0sr3u8AVElEKDmN4LWRldiNjeHN0dWR5EggyNTI3ODk3NBoLZWFzZW1vYi5jb20iKGlvc19lN2UyMzdjZS0wOTBkLTBhNDAtMGExZC0wYjVjNjg2NmUzOWMaPAoOY3gtZGV2I2N4c3R1ZHkSCDI1Mjc4OTc0GgtlYXNlbW9iLmNvbSITd2ViaW1fMTc3ODMzNjExOTUyOSCJ+uro4DMoATKhAQgBEgoSCDI1Mjc4OTc0GgoSCDI1Mjc4OTc0IgoIABIG5L2g5aW9Kl0KC2VtX2FwbnNfZXh0EAgyTHsiZW1faHVhd2VpX3B1c2hfYmFkZ2VfY2xhc3MiOiJjb20uY2hhb3hpbmcubW9iaWxlLmFjdGl2aXR5LlNwbGFzaEFjdGl2aXR5In0qFgoIZnJvbVB1aWQQBzIIMzAwNDczODNKAnt9QisKEWNoYXRfcm91dGVfdGFyZ2V0EAcyFHNlbGZfc3BlY2lmaWNfZGV2aWNlQhYKCWNsaWVudF9pZBAEGNvXuaP+u8sfSg97ImlzX29ubGluZSI6MX0o3JiA0sr3u8AVMgoSCDI1Mjc4OTc0QMn/6ujgMw=="
        )
        client = MSyncClient(app_key="cx-dev#cxstudy", domain="easemob.com")
        client._username = "25278974"

        messages = client._extract_batch_messages(decode_message(frame))

        self.assertEqual(messages[0]["content"], "你好")
        self.assertTrue(messages[0]["from_resource"].startswith("ios_"))
        self.assertTrue(messages[0]["to_resource"].startswith("webim_"))

    def test_chat_view_treats_same_account_other_device_message_as_incoming(self):
        view = SimpleNamespace(
            crawler=SimpleNamespace(get_msync_resource=lambda: "webim_1778336119529"),
        )

        self.assertTrue(
            ChatView._is_remote_self_device_message(
                view,
                {
                    "from": "25278974",
                    "to": "25278974",
                    "from_resource": "ios_e7e237ce-090d-0a40-0a1d-0b5c6866e39c",
                    "to_resource": "webim_1778336119529",
                },
                "25278974",
            )
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

    def test_refresh_msync_info_calls_ws_info_endpoint(self):
        response = _FakeResponse(payload={"websocket": True, "cookie_needed": False})
        session = _FakeSession(response)
        api = _FakeChatAPI(session)

        with patch("core.apis.chat_api.time.time", return_value=1778483983.012):
            result = api.refresh_msync_info()

        self.assertEqual(result, {"websocket": True, "cookie_needed": False})
        self.assertEqual(session.calls[0]["url"], "https://im-api-vip6-v2.easecdn.com/ws/info")
        self.assertEqual(session.calls[0]["params"], {"t": "1778483983012"})

    def test_chat_view_refresh_message_tab_calls_ws_info_and_reload(self):
        calls = []
        view = SimpleNamespace(
            _message_refreshing=False,
            crawler=SimpleNamespace(refresh_msync_info=lambda: calls.append("ws_info")),
            message_refresh_btn=SimpleNamespace(
                setEnabled=lambda enabled: calls.append(("enabled", enabled)),
                setText=lambda text: calls.append(("text", text)),
            ),
            loading_hint=SimpleNamespace(
                setText=lambda text: calls.append(("hint", text)),
                show=lambda: calls.append("show_hint"),
            ),
            _load_message_list=lambda show_loading=True: calls.append(("load_list", show_loading)),
            _ensure_msync_connected=lambda: calls.append("ensure_msync"),
        )

        ChatView._refresh_message_tab(view)

        self.assertEqual(
            calls,
            [
                ("enabled", False),
                ("text", "刷新中"),
                ("hint", "正在刷新消息连接..."),
                "show_hint",
                "ws_info",
                ("enabled", True),
                ("text", "刷新"),
                ("load_list", True),
                "ensure_msync",
            ],
        )

    def test_chat_view_auto_refresh_message_tab_skips_loading_hint(self):
        calls = []
        view = SimpleNamespace(
            _message_refreshing=False,
            crawler=SimpleNamespace(refresh_msync_info=lambda: calls.append("ws_info")),
            message_refresh_btn=SimpleNamespace(
                setEnabled=lambda enabled: calls.append(("enabled", enabled)),
                setText=lambda text: calls.append(("text", text)),
            ),
            loading_hint=SimpleNamespace(
                setText=lambda text: calls.append(("hint", text)),
                show=lambda: calls.append("show_hint"),
            ),
            _load_message_list=lambda show_loading=True: calls.append(("load_list", show_loading)),
            _ensure_msync_connected=lambda: calls.append("ensure_msync"),
        )

        ChatView._refresh_message_tab(view, auto_triggered=True)

        self.assertEqual(calls, ["ws_info", "ensure_msync"])

    def test_chat_view_realtime_message_list_reload_skips_loading_hint(self):
        loaded = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={},
            _raw_sessions=[],
            _message_cache={},
            _pending_read_acks={},
            _unread_count_by_peer={},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._store_class_info_metadata = lambda peer_id, class_info, allow_avatar_update=True: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: True
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: 0
        view._set_unread_count = lambda peer_id, unread_count, history_id="": None
        view._load_message_list = lambda show_loading=True: loaded.append(show_loading)

        with patch.object(ChatView, "_schedule_realtime_message_refresh", lambda current: None):
            ChatView._on_msync_message(
                view,
                {
                    "from": "358566558",
                    "to": "25278974",
                    "peer_id": "358566558",
                    "content": "新的实时消息",
                    "timestamp": 1778312000000,
                    "message_id": "1549399999999999999",
                },
            )

        self.assertEqual(loaded, [False])

    def test_chat_view_refresh_message_tab_after_realtime_retries_when_busy(self):
        calls = []
        view = SimpleNamespace(
            _message_refreshing=True,
            _message_worker=SimpleNamespace(isRunning=lambda: False),
            _message_auto_refresh_timer=SimpleNamespace(start=lambda delay: calls.append(("timer", delay))),
        )

        ChatView._refresh_message_tab_after_realtime(view)

        self.assertEqual(calls, [("timer", 400)])

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

    def test_get_im_user_info_by_tuid_uses_cache_after_first_lookup(self):
        session = _FakeSession(_FakeResponse(payload={"data": {"name": "张三", "icon": "http://photo.example/a.png"}}))
        api = _FakeChatAPI(
            session,
            course_params={"im_tuid": "100", "im_puid": "200", "im_token": "token-1"},
        )

        first = api.get_im_user_info_by_tuid("358572378")
        second = api.get_im_user_info_by_tuid("358572378")

        self.assertEqual(first["name"], "张三")
        self.assertEqual(second["name"], "张三")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(api.session_manager.course_params["im_user_info_cache"]["358572378"]["name"], "张三")

    def test_connect_msync_reuses_running_client(self):
        session = _FakeSession(_FakeResponse(payload={}))
        api = _FakeChatAPI(session, course_params={"im_tuid": "100", "im_token": "token-1"})
        _FakeChatAPI._msync_message_listeners = {}
        _FakeChatAPI._msync_error_listeners = {}
        _FakeChatAPI._msync_close_listeners = {}
        running_client = SimpleNamespace(
            is_running=lambda: True,
            on_message=None,
            on_error=None,
            on_close=None,
        )
        _FakeChatAPI._msync = running_client

        result = api.connect_msync(on_message="msg", on_error="err", on_close="close")

        self.assertIs(result, running_client)
        self.assertIs(running_client.on_message.__func__, _FakeChatAPI._dispatch_msync_message.__func__)
        self.assertIs(running_client.on_error.__func__, _FakeChatAPI._dispatch_msync_error.__func__)
        self.assertIs(running_client.on_close.__func__, _FakeChatAPI._dispatch_msync_close.__func__)
        self.assertEqual(list(_FakeChatAPI._msync_message_listeners.values()), ["msg"])
        self.assertEqual(list(_FakeChatAPI._msync_error_listeners.values()), ["err"])
        self.assertEqual(list(_FakeChatAPI._msync_close_listeners.values()), ["close"])

    def test_connect_msync_dispatches_to_multiple_registered_message_listeners(self):
        session = _FakeSession(_FakeResponse(payload={}))
        api = _FakeChatAPI(session, course_params={"im_tuid": "100", "im_token": "token-1"})
        _FakeChatAPI._msync_message_listeners = {}
        _FakeChatAPI._msync_error_listeners = {}
        _FakeChatAPI._msync_close_listeners = {}
        _FakeChatAPI._msync = SimpleNamespace(
            is_running=lambda: True,
            on_message=None,
            on_error=None,
            on_close=None,
        )
        received = []

        cb1 = lambda payload: received.append(("cb1", payload))
        cb2 = lambda payload: received.append(("cb2", payload))

        api.connect_msync(on_message=cb1, listener_key="listener-1")
        api.connect_msync(on_message=cb2, listener_key="listener-2")
        _FakeChatAPI._dispatch_msync_message({"type": "message"})

        self.assertEqual(
            received,
            [("cb1", {"type": "message"}), ("cb2", {"type": "message"})],
        )

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

    def test_chat_view_ensure_msync_connected_requests_unread_summary_after_connect(self):
        requested = []

        class _Crawler:
            def is_msync_connected(self):
                return False

            def connect_msync(self, on_message=None, on_error=None, on_close=None, listener_key=None):
                return SimpleNamespace()

            def request_history_summary_msync(self, peer_ids):
                requested.append(peer_ids)
                return True

        thread_targets = []

        def _make_thread(target=None, name=None, daemon=None):
            thread_targets.append(target)
            return SimpleNamespace(start=lambda: target())

        with patch("ui.views.chat_view.threading.Thread", side_effect=_make_thread):
            view = SimpleNamespace(
                crawler=_Crawler(),
                _msync_connecting=False,
                _msync_connect_lock=threading.Lock(),
                _current_target_id="",
                _raw_sessions=[{"chatId": "358566558"}, {"chatId": "358574049"}],
            )
            view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
            view._request_unread_summary = lambda sessions: ChatView._request_unread_summary(view, sessions)
            view.msync_message_received = SimpleNamespace(emit=lambda msg: None)

            ChatView._ensure_msync_connected(view)

        self.assertEqual(requested, [["358566558", "358574049"]])

    def test_chat_view_startup_badge_gate_waits_for_messages_and_msync(self):
        enabled = []
        refreshed = []
        stopped = []
        view = SimpleNamespace(
            _startup_badge_gate_active=True,
            _startup_badge_gate_completed=False,
            _startup_messages_loaded=True,
            _startup_msync_ready=False,
            _raw_sessions=[{"chatId": "358566558"}],
            chat_list=SimpleNamespace(setEnabled=lambda value: enabled.append(value)),
            _startup_badge_gate_timer=SimpleNamespace(stop=lambda: stopped.append(True)),
        )
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)

        first = ChatView._finish_startup_badge_gate(view)
        view._startup_msync_ready = True
        second = ChatView._finish_startup_badge_gate(view)

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertFalse(view._startup_badge_gate_active)
        self.assertTrue(view._startup_badge_gate_completed)
        self.assertEqual(enabled, [True])
        self.assertEqual(refreshed, [None])
        self.assertEqual(stopped, [True])

    def test_chat_view_display_unread_count_hides_badge_until_startup_gate_finishes(self):
        view = SimpleNamespace(_startup_badge_gate_active=True)

        hidden = ChatView._display_unread_count(view, 3)
        view._startup_badge_gate_active = False
        shown = ChatView._display_unread_count(view, 3)

        self.assertEqual(hidden, 0)
        self.assertEqual(shown, 3)

    def test_chat_view_sync_conversation_read_state_uses_latest_cached_message(self):
        requested = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(request_conversation_read_msync=lambda peer_id, message_id: requested.append((peer_id, message_id)) or True),
            _current_target_id="247836588",
            _current_history_id="306927744647171",
            _message_cache={
                "306927744647171": [
                    {"message_id": "1549317683114151050", "timestamp": 1},
                    {"message_id": "1549317683114151060", "timestamp": 2},
                ]
            },
            _last_read_sync_by_conversation={},
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._message_sort_key = lambda msg: ChatView._message_sort_key(view, msg)
        view._latest_message_id_for_conversation = lambda conversation_key=None: ChatView._latest_message_id_for_conversation(view, conversation_key)

        synced = ChatView._sync_conversation_read_state(view)

        self.assertTrue(synced)
        self.assertEqual(requested, [("247836588", "1549317683114151060")])
        self.assertEqual(view._last_read_sync_by_conversation["306927744647171"], "1549317683114151060")

    def test_chat_view_sync_conversation_read_state_resolves_group_peer_from_history_id(self):
        requested = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(request_conversation_read_msync=lambda peer_id, message_id: requested.append((peer_id, message_id)) or True),
            _current_target_id="306927744647171",
            _current_history_id="306927744647171",
            _history_id_by_peer={"358566558": "306927744647171"},
            _message_cache={"306927744647171": [{"message_id": "1549317683114151060", "timestamp": 2}]},
            _last_read_sync_by_conversation={},
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._message_sort_key = lambda msg: ChatView._message_sort_key(view, msg)
        view._latest_message_id_for_conversation = lambda conversation_key=None: ChatView._latest_message_id_for_conversation(view, conversation_key)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)

        synced = ChatView._sync_conversation_read_state(view)

        self.assertTrue(synced)
        self.assertEqual(requested, [("358566558", "1549317683114151060")])

    def test_chat_view_load_current_chat_history_starts_new_worker_for_new_chat(self):
        created = []

        class _Signal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)

        class _Worker:
            def __init__(self, crawler, chat_id, limit=200):
                self.crawler = crawler
                self.chat_id = chat_id
                self.limit = limit
                self.history_ready = _Signal()
                self.finished = _Signal()
                self.started = False
                created.append(self)
            def isRunning(self):
                return False
            def start(self):
                self.started = True

        view = SimpleNamespace(
            crawler=SimpleNamespace(),
            _current_history_id="new-chat",
            _history_worker=SimpleNamespace(chat_id="old-chat", isRunning=lambda: True),
            _history_workers=[],
            _on_history_loaded=lambda chat_id, messages: None,
        )

        with patch("ui.views.chat_view.ChatHistoryWorker", _Worker):
            ChatView._load_current_chat_history(view)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].chat_id, "new-chat")
        self.assertTrue(created[0].started)
        self.assertIs(view._history_worker, created[0])

    def test_chat_view_history_load_waits_for_msync_before_showing_empty(self):
        ensured = []
        cleared = []
        placeholders = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(is_msync_connected=lambda: False),
            _current_target_id="358566558",
            _current_target_name="张三",
            _current_history_id="bad-chat",
            _current_history_candidates=["bad-chat"],
            _history_attempted_keys={"bad-chat"},
            _message_cache={},
            _last_send_error="",
            _msync_connecting=True,
            _current_history_empty_retry_done=False,
            _current_history_post_connect_retry_done=False,
            _pending_history_retry_after_connect=False,
            chat_messages=SimpleNamespace(
                clear=lambda: cleared.append(True),
                setPlaceholderText=lambda text: placeholders.append(text),
            ),
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._normalize_history_messages = lambda messages: []
        view._try_fallback_history_key = lambda failed_history_id, limit=200: False
        view._delay_empty_history_resolution = lambda history_id, limit=200: ChatView._delay_empty_history_resolution(view, history_id, limit)
        view._ensure_msync_connected = lambda: ensured.append(True)
        view.append_message = lambda sender, text, is_self=False, status_text="": None

        ChatView._on_history_loaded(view, "bad-chat", [])

        self.assertEqual(cleared, [])
        self.assertEqual(placeholders, [])
        self.assertEqual(ensured, [True])
        self.assertTrue(view._pending_history_retry_after_connect)

    def test_chat_view_ignores_stale_history_response_from_previous_open_generation(self):
        cleared = []
        placeholders = []
        rendered = []
        view = SimpleNamespace(
            _current_target_id="358566558",
            _current_target_name="张三",
            _current_history_id="same-chat",
            _current_history_candidates=["same-chat"],
            _history_attempted_keys={"same-chat"},
            _history_load_generation=3,
            _message_cache={},
            _last_send_error="",
            chat_messages=SimpleNamespace(
                clear=lambda: cleared.append(True),
                setPlaceholderText=lambda text: placeholders.append(text),
            ),
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._normalize_history_messages = lambda messages: []
        view._try_fallback_history_key = lambda failed_history_id, limit=200: False
        view._delay_empty_history_resolution = lambda history_id, limit=200: False
        view._render_cached_messages = lambda conversation_key=None: rendered.append(conversation_key)
        view._sync_conversation_read_state = lambda peer_id=None, history_id=None, message_id="": None
        view.append_message = lambda sender, text, is_self=False, status_text="": None

        ChatView._on_history_loaded(view, "same-chat", [], load_generation=2)

        self.assertEqual(cleared, [])
        self.assertEqual(placeholders, [])
        self.assertEqual(rendered, [])

    def test_chat_view_history_load_falls_back_to_next_candidate_when_primary_is_empty(self):
        loads = []
        cleared = []
        placeholders = []
        view = SimpleNamespace(
            _current_target_id="358566558",
            _current_target_name="张三",
            _current_history_id="bad-chat",
            _current_history_candidates=["bad-chat", "good-chat"],
            _history_attempted_keys={"bad-chat"},
            _message_cache={},
            _last_send_error="",
            chat_messages=SimpleNamespace(
                clear=lambda: cleared.append(True),
                setPlaceholderText=lambda text: placeholders.append(text),
            ),
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._normalize_history_messages = lambda messages: []
        view._try_fallback_history_key = lambda failed_history_id, limit=200: ChatView._try_fallback_history_key(view, failed_history_id, limit)
        view._load_current_chat_history = lambda limit=200, history_id=None: loads.append((limit, history_id or view._current_history_id))
        view.append_message = lambda sender, text, is_self=False, status_text="": None

        ChatView._on_history_loaded(view, "bad-chat", [])

        self.assertEqual(view._current_history_id, "good-chat")
        self.assertEqual(loads, [(200, "good-chat")])
        self.assertEqual(cleared, [])
        self.assertEqual(placeholders, [])

    def test_chat_view_ensure_msync_connected_retries_current_history_after_connect(self):
        requested = []
        retried = []

        class _Crawler:
            def __init__(self):
                self.connected = False

            def is_msync_connected(self):
                return self.connected

            def connect_msync(self, on_message=None, on_error=None, on_close=None, listener_key=None):
                self.connected = True
                return SimpleNamespace()

            def request_history_summary_msync(self, peer_ids):
                return True

            def request_history_msync(self, peer_id):
                requested.append(peer_id)
                return True

        def _make_thread(target=None, name=None, daemon=None):
            return SimpleNamespace(start=lambda: target())

        with patch("ui.views.chat_view.threading.Thread", side_effect=_make_thread), \
             patch.object(ChatView, "_retry_current_chat_history", side_effect=lambda view, limit=200, force=False, request_realtime=True: retried.append((limit, force, request_realtime)) or True):
            view = SimpleNamespace(
                crawler=_Crawler(),
                _msync_connecting=False,
                _msync_connect_lock=threading.Lock(),
                _current_target_id="358566558",
                _current_history_id="bad-chat",
                _current_history_post_connect_retry_done=False,
                _pending_history_retry_after_connect=True,
                _raw_sessions=[],
            )
            view.msync_message_received = SimpleNamespace(emit=lambda msg: None)
            view._request_unread_summary = lambda sessions: None
            view._sync_conversation_read_state = lambda: None

            ChatView._ensure_msync_connected(view)

        self.assertEqual(requested, ["358566558"])
        self.assertEqual(retried, [(200, True, False)])
        self.assertTrue(view._current_history_post_connect_retry_done)
        self.assertFalse(view._pending_history_retry_after_connect)

    def test_chat_view_request_history_sync_throttles_same_target_briefly(self):
        requested = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(request_history_msync=lambda peer_id: requested.append(peer_id) or True),
            _history_id_by_peer={},
            _last_history_request_at={},
        )
        view._resolve_active_peer_id = lambda peer_id="", history_id="": ChatView._resolve_active_peer_id(view, peer_id, history_id)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._resolve_peer_id_by_history_id = lambda history_id: ChatView._resolve_peer_id_by_history_id(view, history_id)

        with patch("ui.views.chat_view.time.monotonic", side_effect=[100.0, 100.2, 101.3]):
            first = ChatView._request_history_sync(view, "358566558")
            second = ChatView._request_history_sync(view, "358566558")
            third = ChatView._request_history_sync(view, "358566558")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(third)
        self.assertEqual(requested, ["358566558", "358566558"])

    def test_chat_view_ensure_msync_connected_skips_duplicate_recent_history_request(self):
        requested = []

        class _Crawler:
            def __init__(self):
                self.connected = False

            def is_msync_connected(self):
                return self.connected

            def connect_msync(self, on_message=None, on_error=None, on_close=None, listener_key=None):
                self.connected = True
                return SimpleNamespace()

            def request_history_msync(self, peer_id):
                requested.append(peer_id)
                return True

        def _make_thread(target=None, name=None, daemon=None):
            return SimpleNamespace(start=lambda: target())

        with patch("ui.views.chat_view.threading.Thread", side_effect=_make_thread), \
             patch("ui.views.chat_view.time.monotonic", return_value=100.0), \
             patch.object(ChatView, "_retry_current_chat_history", return_value=True):
            view = SimpleNamespace(
                crawler=_Crawler(),
                _msync_connecting=False,
                _msync_connect_lock=threading.Lock(),
                _current_target_id="358566558",
                _current_history_id="bad-chat",
                _current_history_post_connect_retry_done=False,
                _pending_history_retry_after_connect=True,
                _raw_sessions=[],
                _history_id_by_peer={},
                _last_history_request_at={},
            )
            view.msync_message_received = SimpleNamespace(emit=lambda msg: None)
            view._sync_conversation_read_state = lambda: None
            view._resolve_active_peer_id = lambda peer_id="", history_id="": ChatView._resolve_active_peer_id(view, peer_id, history_id)
            view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
            view._resolve_peer_id_by_history_id = lambda history_id: ChatView._resolve_peer_id_by_history_id(view, history_id)

            ChatView._request_history_sync(view, "358566558", history_id="bad-chat")
            ChatView._ensure_msync_connected(view)

        self.assertEqual(requested, ["358566558"])

    def test_chat_view_normalize_history_messages_does_not_leak_self_name_to_peer_messages(self):
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={
                "im_tuid": "25278974",
                "im_my_info": {"name": "郝玉锋"},
            })),
            _current_target_id="340857874",
            _current_history_id="history-1",
            _current_target_name="郝玉锋",
            _all_students=[],
            _group_members_cache={},
            _group_members_cache_dir=Path(tempfile.mkdtemp()),
        )
        view._current_user_display_name = lambda: ChatView._current_user_display_name(view)
        view._store_known_contact_name = lambda index, member: ChatView._store_known_contact_name(view, index, member)
        view._build_known_contact_name_index = lambda: ChatView._build_known_contact_name_index(view)
        view._resolve_known_contact_name = lambda sender_id: ChatView._resolve_known_contact_name(view, sender_id)
        view._resolve_history_sender_name = lambda raw, sender_id, is_self: ChatView._resolve_history_sender_name(view, raw, sender_id, is_self)
        view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)

        normalized = ChatView._normalize_history_messages(
            view,
            [
                {"from": "340857874", "fromName": "张三", "content": "老师好", "timestamp": 1, "msgId": "m1"},
                {"from": "25278974", "fromName": "郝玉锋", "content": "你好", "timestamp": 2, "msgId": "m2"},
            ],
        )

        self.assertEqual(normalized[0]["sender_name"], "张三")
        self.assertFalse(normalized[0]["is_self"])
        self.assertEqual(normalized[1]["sender_name"], "我")
        self.assertTrue(normalized[1]["is_self"])

    def test_chat_view_normalize_history_messages_uses_group_member_cache_when_history_lacks_name(self):
        cache_dir = Path(tempfile.mkdtemp())
        try:
            view = SimpleNamespace(
                crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={
                    "im_tuid": "25278974",
                    "im_my_info": {"name": "郝玉锋"},
                })),
                _current_target_id="358572378",
                _current_history_id="history-1",
                _current_target_name="358572378",
                _all_students=[],
                _group_members_cache={"room-1": [{"person_id": "358572378", "name": "张三"}]},
                _group_members_cache_dir=cache_dir,
            )
            view._current_user_display_name = lambda: ChatView._current_user_display_name(view)
            view._store_known_contact_name = lambda index, member: ChatView._store_known_contact_name(view, index, member)
            view._build_known_contact_name_index = lambda: ChatView._build_known_contact_name_index(view)
            view._resolve_known_contact_name = lambda sender_id: ChatView._resolve_known_contact_name(view, sender_id)
            view._resolve_history_sender_name = lambda raw, sender_id, is_self: ChatView._resolve_history_sender_name(view, raw, sender_id, is_self)
            view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)

            normalized = ChatView._normalize_history_messages(
                view,
                [{"from": "358572378", "content": "老师好", "timestamp": 1, "msgId": "m1"}],
            )

            self.assertEqual(normalized[0]["sender_name"], "张三")
        finally:
            for path in cache_dir.glob("*"):
                path.unlink()
            cache_dir.rmdir()

    def test_chat_view_history_load_corrects_current_target_name_from_peer_message(self):
        render_calls = []
        synced = []
        merged = []
        cache_dir = Path(tempfile.mkdtemp())
        try:
            view = SimpleNamespace(
                crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={
                    "im_tuid": "25278974",
                    "im_my_info": {"name": "郝玉锋"},
                })),
                _current_target_id="340857874",
                _current_history_id="history-1",
                _current_target_name="郝玉锋",
                _message_cache={},
                _history_id_by_peer={},
                _all_students=[],
                _group_members_cache={},
                _group_members_cache_dir=cache_dir,
                chat_title_label=SimpleNamespace(setText=lambda text: render_calls.append(("title", text))),
                chat_messages=SimpleNamespace(clear=lambda: None, setPlaceholderText=lambda text: None),
                _last_send_error="",
            )
            view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
            view._current_user_display_name = lambda: ChatView._current_user_display_name(view)
            view._store_known_contact_name = lambda index, member: ChatView._store_known_contact_name(view, index, member)
            view._build_known_contact_name_index = lambda: ChatView._build_known_contact_name_index(view)
            view._resolve_known_contact_name = lambda sender_id: ChatView._resolve_known_contact_name(view, sender_id)
            view._resolve_history_sender_name = lambda raw, sender_id, is_self: ChatView._resolve_history_sender_name(view, raw, sender_id, is_self)
            view._correct_current_target_name_from_history = lambda normalized: ChatView._correct_current_target_name_from_history(view, normalized)
            view._normalize_history_messages = lambda messages: ChatView._normalize_history_messages(view, messages)
            view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)
            view._merge_cached_messages = lambda conversation_key, normalized: merged.append((conversation_key, normalized))
            view._render_cached_messages = lambda conversation_key: render_calls.append(("render", conversation_key))
            view._sync_conversation_read_state = lambda peer_id="", history_id="": synced.append((peer_id, history_id))
            view._try_fallback_history_key = lambda chat_id: False

            ChatView._on_history_loaded(
                view,
                "history-1",
                [{"from": "340857874", "fromName": "张三", "content": "老师好", "timestamp": 1, "msgId": "m1"}],
            )

            self.assertEqual(view._current_target_name, "张三")
            self.assertIn(("title", "张三"), render_calls)
            self.assertEqual(merged[0][1][0]["sender_name"], "张三")
            self.assertEqual(synced, [("340857874", "history-1")])
        finally:
            for path in cache_dir.glob("*"):
                path.unlink()
            cache_dir.rmdir()

    def test_chat_view_history_load_corrects_numeric_target_name_from_cached_member(self):
        render_calls = []
        cache_dir = Path(tempfile.mkdtemp())
        try:
            view = SimpleNamespace(
                crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={
                    "im_tuid": "25278974",
                    "im_my_info": {"name": "郝玉锋"},
                })),
                _current_target_id="358572378",
                _current_history_id="history-1",
                _current_target_name="358572378",
                _message_cache={},
                _history_id_by_peer={},
                _all_students=[],
                _group_members_cache={"room-1": [{"person_id": "358572378", "name": "李四"}]},
                _group_members_cache_dir=cache_dir,
                chat_title_label=SimpleNamespace(setText=lambda text: render_calls.append(text)),
                chat_messages=SimpleNamespace(clear=lambda: None, setPlaceholderText=lambda text: None),
                _last_send_error="",
            )
            view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
            view._current_user_display_name = lambda: ChatView._current_user_display_name(view)
            view._store_known_contact_name = lambda index, member: ChatView._store_known_contact_name(view, index, member)
            view._build_known_contact_name_index = lambda: ChatView._build_known_contact_name_index(view)
            view._resolve_known_contact_name = lambda sender_id: ChatView._resolve_known_contact_name(view, sender_id)
            view._resolve_history_sender_name = lambda raw, sender_id, is_self: ChatView._resolve_history_sender_name(view, raw, sender_id, is_self)
            view._correct_current_target_name_from_history = lambda normalized: ChatView._correct_current_target_name_from_history(view, normalized)
            view._normalize_history_messages = lambda messages: ChatView._normalize_history_messages(view, messages)
            view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)
            view._merge_cached_messages = lambda conversation_key, normalized: None
            view._render_cached_messages = lambda conversation_key: None
            view._sync_conversation_read_state = lambda peer_id="", history_id="": None
            view._try_fallback_history_key = lambda chat_id: False

            ChatView._on_history_loaded(
                view,
                "history-1",
                [{"from": "358572378", "content": "收到", "timestamp": 1, "msgId": "m1"}],
            )

            self.assertEqual(view._current_target_name, "李四")
            self.assertIn("李四", render_calls)
        finally:
            for path in cache_dir.glob("*"):
                path.unlink()
            cache_dir.rmdir()

    def test_chat_view_resolve_known_contact_name_falls_back_to_im_user_lookup(self):
        cache_dir = Path(tempfile.mkdtemp())
        view = SimpleNamespace(
            _all_students=[],
            _group_members_cache={},
            _group_members_cache_dir=cache_dir,
            crawler=SimpleNamespace(get_im_user_info_by_tuid=lambda tuid: {"name": "王五"} if tuid == "358572378" else {}),
        )
        view._store_known_contact_name = lambda index, member: ChatView._store_known_contact_name(view, index, member)
        view._build_known_contact_name_index = lambda: ChatView._build_known_contact_name_index(view)

        try:
            resolved = ChatView._resolve_known_contact_name(view, "358572378")
            self.assertEqual(resolved, "王五")
            self.assertEqual(view._known_contact_name_index["358572378"], "王五")
        finally:
            cache_dir.rmdir()

    def test_chat_view_render_cached_messages_prefers_session_list_display_name(self):
        rendered = []
        placeholder_texts = []
        view = SimpleNamespace(
            _current_target_id="358572378",
            _current_history_id="history-1",
            _current_target_name="358572378",
            _current_session_display_name="张三",
            _message_cache={
                "history-1": [
                    {"is_self": False, "sender_name": "358572378", "content": "老师好", "timestamp": 1},
                    {"is_self": True, "sender_name": "我", "content": "收到", "timestamp": 2},
                ]
            },
            _last_send_error="",
            chat_messages=SimpleNamespace(
                clear=lambda: None,
                setPlaceholderText=lambda text: placeholder_texts.append(text),
            ),
        )
        view._conversation_key = lambda peer_id=None, history_id=None: ChatView._conversation_key(view, peer_id, history_id)
        view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)
        view._message_status_text = lambda msg: ChatView._message_status_text(view, msg)
        view.append_message = lambda sender, text, is_self=False, status_text="": rendered.append((sender, text, is_self))

        ChatView._render_cached_messages(view, "history-1")

        self.assertEqual(placeholder_texts, ["与 张三 的对话"])
        self.assertEqual(rendered[0], ("张三", "老师好", False))
        self.assertEqual(rendered[1], ("我", "收到", True))

    def test_chat_view_history_sync_message_refreshes_without_reloading_list(self):
        refreshed = []
        loaded = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={},
            _raw_sessions=[{"chatId": "358566558", "chatName": "离散数学"}],
            _message_cache={},
            _pending_read_acks={},
            _unread_count_by_peer={},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: None
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: loaded.append(True)

        ChatView._on_msync_message(
            view,
            {
                "from": "358566558",
                "to": "25278974",
                "peer_id": "358566558",
                "content": "好的谢谢老师",
                "timestamp": 1778311611198,
                "message_id": "1549395756211768472",
                "history_sync": True,
            },
        )

        self.assertEqual(len(refreshed), 1)
        self.assertEqual(loaded, [])

    def test_chat_view_history_sync_message_does_not_increment_unread_count(self):
        refreshed = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={},
            _raw_sessions=[{"chatId": "358566558", "chatName": "离散数学"}],
            _message_cache={},
            _unread_count_by_peer={"358566558": 2},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: None
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: None

        ChatView._on_msync_message(
            view,
            {
                "from": "358566558",
                "to": "25278974",
                "peer_id": "358566558",
                "content": "历史同步消息",
                "timestamp": 1778311611198,
                "message_id": "1549395756211768472",
                "history_sync": True,
            },
        )

        self.assertEqual(view._unread_count_by_peer["358566558"], 2)
        self.assertEqual(len(refreshed), 1)

    def test_chat_view_duplicate_live_message_only_increments_unread_once(self):
        refreshed = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={},
            _raw_sessions=[{"chatId": "358566558", "chatName": "离散数学"}],
            _message_cache={},
            _pending_read_acks={},
            _unread_count_by_peer={},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: ChatView._append_cached_message(view, **kwargs)
        view._message_sort_key = lambda item: ChatView._message_sort_key(view, item)
        view._find_cached_message = lambda cache, message: ChatView._find_cached_message(view, cache, message)
        view._message_identity = lambda message: ChatView._message_identity(view, message)
        view._merge_read_state = lambda old_state="", new_state="": ChatView._merge_read_state(view, old_state, new_state)
        view._merge_cached_entry = lambda current, incoming: ChatView._merge_cached_entry(view, current, incoming)
        view._apply_pending_read_ack = lambda message: ChatView._apply_pending_read_ack(view, message)
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: None

        payload = {
            "from": "358566558",
            "to": "25278974",
            "peer_id": "358566558",
            "content": "重复实时消息",
            "timestamp": 1778312000000,
            "message_id": "1549399999999999999",
        }

        ChatView._on_msync_message(view, dict(payload))
        ChatView._on_msync_message(view, dict(payload))

        self.assertEqual(view._unread_count_by_peer["358566558"], 1)
        self.assertEqual(len(view._message_cache["358566558"]), 1)
        self.assertEqual(len(refreshed), 1)

    def test_chat_view_live_message_upserts_session_without_reloading_list(self):
        row_updates = []
        refreshed = []
        loaded = []
        auto_refresh = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={},
            _raw_sessions=[{"chatId": "358566558", "chatName": "离散数学", "updateTime": 1}],
            _message_cache={},
            _unread_count_by_peer={},
            _message_auto_refresh_timer=SimpleNamespace(start=lambda delay: auto_refresh.append(delay)),
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: None
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._update_session_row = lambda peer_id="", history_id="", session=None: row_updates.append((peer_id, history_id, session))
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: loaded.append(True)

        ChatView._on_msync_message(
            view,
            {
                "from": "358566558",
                "to": "25278974",
                "peer_id": "358566558",
                "content": "新的实时消息",
                "timestamp": 1778312000000,
                "message_id": "1549399999999999999",
            },
        )

        self.assertEqual(len(row_updates), 1)
        self.assertEqual(refreshed, [])
        self.assertEqual(loaded, [])
        self.assertEqual(auto_refresh, [400])

    def test_chat_view_self_message_does_not_leak_current_chat_name_into_group_session(self):
        refreshed = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="peer-1",
            _current_history_id="peer-1",
            _current_target_name="郝玉锋",
            _history_id_by_peer={"358566558": "306927744647171"},
            _session_meta_by_peer={"358566558": {"courseName": "离散数学（2025-2026-2）"}},
            _raw_sessions=[{"chatId": "306927744647171", "chatName": "358566558", "updateTime": 1, "isGroup": 0, "isPrivate": False}],
            _message_cache={},
            _unread_count_by_peer={},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: None
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: None

        ChatView._on_msync_message(
            view,
            {
                "from": "25278974",
                "to": "358566558",
                "peer_id": "358566558",
                "content": "我发到群里的消息",
                "timestamp": 1778312000001,
                "message_id": "1549400000000000000",
            },
        )

        self.assertEqual(len(refreshed), 1)
        updated = refreshed[0][0]
        self.assertEqual(updated["chatName"], "离散数学（2025-2026-2）")
        self.assertEqual(updated["isGroup"], 0)
        self.assertFalse(updated["isPrivate"])

    def test_chat_view_private_session_with_different_history_id_stays_out_of_group_section(self):
        refreshed = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _current_target_id="",
            _current_history_id="",
            _current_target_name="",
            _history_id_by_peer={"25278974": "self-history-id"},
            _session_meta_by_peer={},
            _raw_sessions=[{"chatId": "self-history-id", "chatName": "郝玉锋", "updateTime": 1, "isGroup": 1, "isPrivate": True}],
            _message_cache={},
            _unread_count_by_peer={},
        )
        view._resolve_message_peer_id = lambda msg: ChatView._resolve_message_peer_id(view, msg)
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._normalize_unread_peer_id = lambda peer_id: ChatView._normalize_unread_peer_id(view, peer_id)
        view._extract_session_unread_count = lambda session: ChatView._extract_session_unread_count(view, session)
        view._store_class_info_metadata = lambda peer_id, class_info: False
        view._conversation_key = lambda peer_id=None, history_id=None: str(history_id or peer_id or "")
        view._append_cached_message = lambda **kwargs: None
        view._is_ai_assistant_conversation = lambda peer_id, msg=None: False
        view._is_current_conversation_message = lambda peer_id, msg: False
        view._get_unread_count = lambda peer_id="", history_id="", session=None: ChatView._get_unread_count(view, peer_id, history_id, session)
        view._set_unread_count = lambda peer_id, unread_count, history_id="": ChatView._set_unread_count(view, peer_id, unread_count, history_id)
        view._refresh_session_list = lambda sessions=None: refreshed.append(sessions)
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)
        view._load_message_list = lambda: None
        view._is_group_session = lambda session: ChatView._is_group_session(view, session)

        ChatView._on_msync_message(
            view,
            {
                "from": "25278974",
                "to": "25278974",
                "peer_id": "25278974",
                "content": "自己发给自己的消息",
                "timestamp": 1778312000002,
                "message_id": "1549400000000000001",
            },
        )

        updated = refreshed[0][0]
        self.assertEqual(updated["isGroup"], 1)
        self.assertTrue(updated["isPrivate"])

    def test_chat_view_existing_private_session_keeps_private_type_even_if_message_has_class_info(self):
        row_updates = []
        view = SimpleNamespace(
            crawler=SimpleNamespace(session_manager=SimpleNamespace(course_params={"im_tuid": "25278974"})),
            _history_id_by_peer={"3001": "student-history-id"},
            _session_meta_by_peer={},
            _raw_sessions=[{"chatId": "student-history-id", "chatName": "张三", "updateTime": 1, "isGroup": 1, "isPrivate": True}],
        )
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._update_session_row = lambda peer_id="", history_id="", session=None: row_updates.append((peer_id, history_id, session))
        view._refresh_session_list = lambda sessions=None: None
        view._upsert_session_from_message = lambda peer_id, msg, display_name="": ChatView._upsert_session_from_message(view, peer_id, msg, display_name)

        changed = ChatView._upsert_session_from_message(
            view,
            "3001",
            {
                "peer_id": "3001",
                "content": "老师好",
                "timestamp": 1778312000003,
                "class_info": {"chat_id": "306927744647171", "course_name": "离散数学（2025-2026-2）"},
            },
            display_name="张三",
        )

        self.assertTrue(changed)
        updated = row_updates[0][2]
        self.assertEqual(updated["isGroup"], 1)
        self.assertTrue(updated["isPrivate"])
        self.assertEqual(updated["content"], "老师好")

    def test_chat_view_realtime_upsert_suppresses_avatar_refresh(self):
        row_updates = []
        view = SimpleNamespace(
            _history_id_by_peer={},
            _session_meta_by_peer={},
            _raw_sessions=[{"chatId": "3001", "chatName": "张三", "chatIco": "https://photo.example/avatar.png", "updateTime": 1, "isGroup": 1, "isPrivate": True}],
        )
        view._resolve_session_peer_id = lambda session: ChatView._resolve_session_peer_id(view, session)
        view._resolve_session_display_name = lambda peer_id, msg, fallback_name="": ChatView._resolve_session_display_name(view, peer_id, msg, fallback_name)
        view._update_session_row = lambda peer_id="", history_id="", session=None: row_updates.append((peer_id, history_id, getattr(view, "_suppress_avatar_refresh", False)))
        view._refresh_session_list = lambda sessions=None: None

        changed = ChatView._upsert_session_from_message(
            view,
            "3001",
            {"peer_id": "3001", "content": "新消息", "timestamp": 1778312000004},
            display_name="张三",
        )

        self.assertTrue(changed)
        self.assertEqual(row_updates, [("3001", "3001", True)])


if __name__ == "__main__":
    unittest.main()

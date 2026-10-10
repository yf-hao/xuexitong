import unittest

from core.apis.exam_api import (
    ExamReviewContext,
    fetch_all_submitted_exam_records,
    fetch_exam_review_page,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payloads = list(payload) if isinstance(payload, list) else [payload]
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payloads.pop(0))


class ExamReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.context = ExamReviewContext(
            course_id="course-1",
            class_id="class-1",
            cpi="cpi-1",
            exam_id="exam-1",
            exam_title="期中考试",
            class_name="计算机1班",
            marklist_url="https://example.test/marklist",
        )

    def test_fetches_requested_state_and_accepts_code_zero_payload(self):
        session = FakeSession({
            "code": 0,
            "status": False,
            "total": 4,
            "classSize": 60,
            "size": 50,
            "pageNum": 2,
            "totalPage": 3,
            "data": [{"mark": "未查看"}],
        })

        page = fetch_exam_review_page(
            session, self.context, state=0, page_num=2, page_size=50
        )

        url, options = session.calls[0]
        self.assertTrue(url.endswith("/exam/test/markresult-new"))
        self.assertEqual(options["data"]["courseid"], "course-1")
        self.assertEqual(options["data"]["clazzid"], "class-1")
        self.assertEqual(options["data"]["id"], "exam-1")
        self.assertEqual(options["data"]["state"], "0")
        self.assertEqual(options["data"]["pages"], "2")
        self.assertEqual(options["data"]["size"], "50")
        self.assertEqual(options["data"]["groupId"], "-1")
        self.assertEqual(options["data"]["mark"], "-1")
        self.assertEqual(options["headers"]["Referer"], self.context.marklist_url)
        self.assertEqual(options["headers"]["X-Requested-With"], "XMLHttpRequest")
        self.assertIn("Chrome/154", options["headers"]["User-Agent"])
        self.assertEqual(page.total, 4)
        self.assertEqual(page.class_size, 60)
        self.assertEqual(page.page_num, 2)
        self.assertEqual(page.records[0]["mark"], "未查看")

    def test_first_page_matches_captured_form_defaults(self):
        session = FakeSession({
            "code": 0,
            "total": 0,
            "classSize": 0,
            "size": 20,
            "pageNum": 1,
            "totalPage": 0,
            "data": [],
        })

        fetch_exam_review_page(session, self.context, state=1)

        form_data = session.calls[0][1]["data"]
        self.assertEqual(form_data["state"], "1")
        self.assertNotIn("pageNum", form_data)
        self.assertNotIn("size", form_data)
        self.assertEqual(form_data["courseid"], "course-1")
        self.assertEqual(form_data["clazzid"], "class-1")

    def test_custom_page_size_is_sent_on_first_page(self):
        session = FakeSession({
            "code": 0,
            "total": 0,
            "classSize": 0,
            "size": 50,
            "pageNum": 1,
            "totalPage": 0,
            "data": [],
        })

        fetch_exam_review_page(
            session, self.context, state=1, page_size=50
        )

        self.assertEqual(session.calls[0][1]["data"]["size"], "50")

    def test_fetches_and_joins_receive_ips_by_record_id(self):
        session = FakeSession([
            {
                "code": 0,
                "total": 2,
                "classSize": 2,
                "size": 20,
                "pageNum": 1,
                "totalPage": 1,
                "data": [{"id": 101}, {"id": 102}],
            },
            {
                "status": True,
                "receiveIps": [
                    {"id": 102, "receiveIp": "192.0.2.2/河南"},
                    {"id": 101, "receiveIp": "192.0.2.1/河南"},
                ],
            },
        ])

        page = fetch_exam_review_page(session, self.context, state=1)

        ip_url, ip_options = session.calls[1]
        self.assertTrue(ip_url.endswith("/exam/test/answers-receiveip"))
        self.assertEqual(
            ip_options["data"],
            {
                "courseId": "course-1",
                "classId": "class-1",
                "cpi": "cpi-1",
                "ids": "101,102",
            },
        )
        self.assertEqual(page.records[0]["receiveIp"], "192.0.2.1/河南")
        self.assertEqual(page.records[1]["receiveIp"], "192.0.2.2/河南")

    def test_fetches_all_submitted_pages_for_ip_analysis(self):
        session = FakeSession([
            {
                "code": 0,
                "total": 2,
                "classSize": 2,
                "size": 100,
                "pageNum": 1,
                "totalPage": 2,
                "data": [{"id": 101, "loginName": "s101"}],
            },
            {"status": True, "receiveIps": [{"id": 101, "receiveIp": "192.0.2.1/河南"}]},
            {
                "code": 0,
                "total": 2,
                "classSize": 2,
                "size": 100,
                "pageNum": 2,
                "totalPage": 2,
                "data": [{"id": 102, "loginName": "s102"}],
            },
            {"status": True, "receiveIps": [{"id": 102, "receiveIp": "192.0.2.1/河南"}]},
        ])
        progress = []

        records = fetch_all_submitted_exam_records(
            session,
            self.context,
            page_size=100,
            progress_callback=lambda current, total: progress.append((current, total)),
        )

        self.assertEqual([record["id"] for record in records], [101, 102])
        self.assertEqual([record["receiveIp"] for record in records], [
            "192.0.2.1/河南", "192.0.2.1/河南",
        ])
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertEqual(len(session.calls), 4)

    def test_rejects_unknown_state_without_sending_request(self):
        session = FakeSession({})

        with self.assertRaises(ValueError):
            fetch_exam_review_page(session, self.context, state=2)

        self.assertEqual(session.calls, [])

    def test_reports_forbidden_response(self):
        class ForbiddenSession(FakeSession):
            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                response = FakeResponse({})
                response.status_code = 403
                return response

        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            fetch_exam_review_page(
                ForbiddenSession({}), self.context, state=1
            )


if __name__ == "__main__":
    unittest.main()
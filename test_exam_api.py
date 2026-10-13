import struct
import unittest
import zlib

from core.apis.exam_api import (
    ExamReviewContext,
    fetch_all_submitted_exam_records,
    fetch_exam_mark_paper,
    fetch_exam_review_page,
    submit_exam_mark,
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

    def test_fetches_markpaper_html_for_the_selected_record(self):
        class HtmlResponse:
            status_code = 200
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markpaper"
            text = "<html>grading page</html>"

            def raise_for_status(self):
                pass

        class GetSession:
            def get(self, url, **kwargs):
                self.url = url
                self.options = kwargs
                return HtmlResponse()

        session = GetSession()
        html = fetch_exam_mark_paper(session, self.context, "answer-1")

        self.assertEqual(html, "<html>grading page</html>")
        self.assertTrue(session.url.endswith("/exam/test/markpaper"))
        self.assertEqual(
            session.options["params"],
            {
                "courseid": "course-1",
                "id": "answer-1",
                "classid": "class-1",
                "groupid": "-1",
                "ut": "t",
                "cpi": "cpi-1",
                "hideRetest": "false",
                "groupIds": "",
                "sw": "",
                "sorttype": "",
                "updateScore": "1",
                "allowAnnotationRedoDownload": "1",
                "sort": "",
                "from": "list",
            },
        )
        self.assertEqual(
            session.options["headers"]["Referer"], self.context.marklist_url
        )

    def test_submits_mark_form_with_action_and_updated_query_parameters(self):
        session = FakeSession({"status": "success", "msg": "批阅成功"})

        result = submit_exam_mark(
            session,
            "/mooc2-ans/exam/test/submitmark?testUserRelationId=answer-1&classId=class-1",
            [("sumScore", "93"), ("testUserRelationId", "answer-2")],
            [("scoreq1", "8"), ("teacherContentq1", "<p>AI理由</p>")],
        )

        self.assertEqual(result["status"], "success")
        url, options = session.calls[0]
        self.assertTrue(url.endswith("/exam/test/submitmark"))
        self.assertEqual(options["params"], [
            ("testUserRelationId", "answer-2"),
            ("classId", "class-1"),
            ("sumScore", "93"),
        ])
        self.assertEqual(options["data"], [
            ("scoreq1", "8"), ("teacherContentq1", "<p>AI理由</p>"),
        ])
        self.assertEqual(
            options["headers"]["X-Requested-With"], "XMLHttpRequest"
        )

    def test_submit_mark_rejects_external_actions_and_unsuccessful_status(self):
        session = FakeSession({"status": "failed", "msg": "提交失败"})
        with self.assertRaisesRegex(ValueError, "受信任"):
            submit_exam_mark(
                session, "https://outside.invalid/submitmark", [], []
            )
        self.assertEqual(session.calls, [])

        with self.assertRaisesRegex(RuntimeError, "提交失败"):
            submit_exam_mark(
                session,
                "/mooc2-ans/exam/test/submitmark",
                [],
                [],
            )

    def test_fetches_and_embeds_trusted_answer_images_only(self):
        def png_chunk(chunk_type, data):
            return (
                struct.pack(">I", len(data))
                + chunk_type
                + data
                + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
            )

        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
            + png_chunk(b"IEND", b"")
        )
        page_html = """
        <html><body>
          <img class="ans-ued-img" src="https://p.ananas.chaoxing.com/image.jpg">
          <img class="ans-ued-img" src="https://outside.invalid/image.jpg">
        </body></html>
        """

        class HtmlResponse:
            status_code = 200
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markpaper"
            text = page_html

            def raise_for_status(self):
                pass

        class ImageResponse:
            status_code = 200
            url = "https://p.ananas.chaoxing.com/image.jpg"
            content = png_bytes

        class ImageSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/image.jpg"):
                    return ImageResponse()
                return HtmlResponse()

        session = ImageSession()
        page = fetch_exam_mark_paper(session, self.context, "answer-1")

        self.assertEqual(len(session.calls), 2)
        image_headers = session.calls[1][1]["headers"]
        self.assertEqual(
            image_headers["Referer"],
            "https://mooc2-gray.chaoxing.com/",
        )
        self.assertEqual(image_headers["Accept-Language"].split(",", 1)[0], "zh-CN")
        self.assertEqual(image_headers["Sec-Fetch-Dest"], "image")
        self.assertEqual(image_headers["Sec-Fetch-Mode"], "no-cors")
        self.assertEqual(image_headers["Sec-Fetch-Site"], "same-site")
        self.assertIn("data:image/png;base64,", page)
        self.assertFalse(
            any("outside.invalid" in call[0] for call in session.calls)
        )

    def test_follows_only_trusted_image_redirects(self):
        page_html = (
            '<img class="ans-ued-img" '
            'src="https://p.ananas.chaoxing.com/source.jpg">'
        )

        class PageResponse:
            status_code = 200
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markpaper"
            text = page_html

            def raise_for_status(self):
                pass

        class RedirectResponse:
            status_code = 302
            headers = {"Location": "/cdn/final.jpg"}
            url = "https://p.ananas.chaoxing.com/source.jpg"

        class ImageResponse:
            status_code = 200
            url = "https://p.ananas.chaoxing.com/cdn/final.jpg"
            content = b"\xff\xd8\xffjpeg-data"

        class RedirectSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                if url.endswith("/markpaper"):
                    return PageResponse()
                if url.endswith("/source.jpg"):
                    return RedirectResponse()
                return ImageResponse()

        session = RedirectSession()
        page = fetch_exam_mark_paper(session, self.context, "answer-1")

        self.assertEqual(len(session.calls), 3)
        self.assertIn("data:image/jpeg;base64,", page)

        class ExternalRedirectResponse:
            status_code = 302
            headers = {"Location": "https://outside.invalid/final.jpg"}
            url = "https://p.ananas.chaoxing.com/source.jpg"

        class ExternalRedirectSession(RedirectSession):
            def get(self, url, **kwargs):
                self.calls.append(url)
                if url.endswith("/markpaper"):
                    return PageResponse()
                return ExternalRedirectResponse()

        external_session = ExternalRedirectSession()
        page = fetch_exam_mark_paper(
            external_session, self.context, "answer-1"
        )
        self.assertEqual(len(external_session.calls), 2)
        self.assertNotIn("data:image/", page)


if __name__ == "__main__":
    unittest.main()
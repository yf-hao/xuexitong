import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.apis.exam_api import (
    download_exam_attachment,
    exam_attachment_cache_path,
)


class ExamAttachmentDownloadTests(unittest.TestCase):
    def test_cache_path_is_stable_scoped_and_preserves_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with unittest.mock.patch("core.apis.exam_api.DATA_DIR", temp_dir):
                first = exam_attachment_cache_path(
                    "object-a", "../StudentManager.JAVA"
                )
                repeated = exam_attachment_cache_path(
                    "object-a", "StudentManager.java"
                )
                other = exam_attachment_cache_path(
                    "object-b", "StudentManager.java"
                )

            self.assertEqual(first, repeated)
            self.assertNotEqual(first, other)
            self.assertEqual(Path(first).suffix, ".java")
            self.assertTrue(Path(first).parent.is_dir())

    def test_downloads_using_status_url_and_authenticated_session(self):
        status_response = Mock()
        status_response.status_code = 200
        status_response.url = "https://mooc2-gray.chaoxing.com/ananas/status/id-1"
        status_response.json.return_value = {
            "download": "http://files.example.test/submission.java?token=abc"
        }
        file_response = Mock()
        file_response.status_code = 200
        file_response.url = "https://files.example.test/submission.java?token=abc"
        file_response.iter_content.return_value = [b"class Main {}", b""]
        session = Mock()
        session.get.side_effect = [status_response, file_response]

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "submission.java"
            result = download_exam_attachment(
                session, "id-1", str(destination)
            )

            self.assertEqual(result, str(destination))
            self.assertEqual(destination.read_bytes(), b"class Main {}")

        self.assertIn("/ananas/status/id-1", session.get.call_args_list[0].args[0])
        self.assertIn(
            "Chrome/154.0.0.0",
            session.get.call_args_list[0].kwargs["headers"]["User-Agent"],
        )
        self.assertEqual(
            session.get.call_args_list[1].args[0],
            "https://files.example.test/submission.java?token=abc",
        )
        self.assertTrue(session.get.call_args_list[1].kwargs["stream"])
        status_response.close.assert_called_once()
        file_response.close.assert_called_once()

    def test_missing_download_url_fails_without_fetching_a_file(self):
        status_response = Mock()
        status_response.status_code = 200
        status_response.json.return_value = {"status": 0}
        session = Mock()
        session.get.return_value = status_response

        with self.assertRaisesRegex(RuntimeError, "没有返回下载地址"):
            download_exam_attachment(session, "id-1", "/tmp/unused")

        session.get.assert_called_once()
        status_response.close.assert_called_once()

    def test_forbidden_status_reports_permission_and_redacts_tokens(self):
        status_response = Mock()
        status_response.status_code = 403
        status_response.url = "https://mooc2-gray.chaoxing.com/ananas/status/id-1"
        status_response.json.side_effect = ValueError("not JSON")
        status_response.text = (
            "<html><body>权限不足，请联系管理员。"
            "?token=private-value</body></html>"
        )
        session = Mock()
        session.get.return_value = status_response

        with self.assertRaises(RuntimeError) as context:
            download_exam_attachment(session, "id-1", "/tmp/unused")

        self.assertIn("下载权限", str(context.exception))
        self.assertIn("权限不足", str(context.exception))
        self.assertNotIn("private-value", str(context.exception))
        status_response.close.assert_called_once()

    def test_forbidden_status_detects_redirect_to_login(self):
        status_response = Mock()
        status_response.status_code = 403
        status_response.url = "https://passport2.chaoxing.com/login"
        status_response.json.side_effect = ValueError("not JSON")
        status_response.text = "请登录"
        session = Mock()
        session.get.return_value = status_response

        with self.assertRaisesRegex(RuntimeError, "跳转到了登录服务"):
            download_exam_attachment(session, "id-1", "/tmp/unused")

        status_response.close.assert_called_once()

    def test_failed_stream_removes_partial_file(self):
        status_response = Mock()
        status_response.status_code = 200
        status_response.url = "https://mooc2-gray.chaoxing.com/ananas/status/id-1"
        status_response.json.return_value = {
            "download": "https://files.example.test/submission.java"
        }
        file_response = Mock()
        file_response.status_code = 200
        file_response.url = "https://files.example.test/submission.java"

        def failing_stream():
            yield b"partial"
            raise OSError("connection dropped")

        file_response.iter_content.return_value = failing_stream()
        session = Mock()
        session.get.side_effect = [status_response, file_response]

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "submission.java"
            with self.assertRaisesRegex(OSError, "connection dropped"):
                download_exam_attachment(session, "id-1", str(destination))

            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

        file_response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
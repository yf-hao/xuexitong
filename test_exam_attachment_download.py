import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.apis.exam_api import download_exam_attachment


class ExamAttachmentDownloadTests(unittest.TestCase):
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
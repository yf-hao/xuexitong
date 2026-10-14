import unittest
from unittest.mock import patch

from core.apis.ai_service import DiscreteMathAIService
from ui.views.chat_view import ChatView


PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


class AIChatImageRequestTests(unittest.TestCase):
    @staticmethod
    def create_service(endpoint_type):
        service = DiscreteMathAIService.__new__(DiscreteMathAIService)
        service.api_key = "test-key"
        service.base_url = "https://example.test/v1"
        service.model = "vision-model"
        service.endpoint_type = endpoint_type
        service.system_prompt = "请帮助教师解答学生问题。"
        return service

    def test_chat_completions_request_contains_text_and_image_url(self):
        service = self.create_service("chat_completions")
        with (
            patch.object(service, "_send_streaming_chat_request", return_value=None),
            patch.object(service, "_send_generation_request", return_value="答复") as send,
        ):
            result = service.generate_reply_suggestion(
                "请解答图中题目",
                image_data_uris=[PNG_DATA_URI],
            )

        self.assertEqual(result, "答复")
        payload = send.call_args.args[1]
        user_content = payload["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertIn("请解答图中题目", user_content[0]["text"])
        self.assertEqual(
            user_content[2],
            {"type": "image_url", "image_url": {"url": PNG_DATA_URI}},
        )

    def test_responses_request_contains_input_image(self):
        service = self.create_service("responses")
        with (
            patch.object(service, "_send_streaming_chat_request", return_value=None),
            patch.object(service, "_send_generation_request", return_value="答复") as send,
        ):
            result = service.generate_reply_suggestion(
                "请解答图中题目",
                image_data_uris=[PNG_DATA_URI],
            )

        self.assertEqual(result, "答复")
        payload = send.call_args.args[1]
        user_content = payload["input"][1]["content"]
        self.assertIn(
            {"type": "input_image", "image_url": PNG_DATA_URI},
            user_content,
        )

    def test_rejects_invalid_or_oversized_image_data(self):
        service = self.create_service("chat_completions")

        result = service.generate_reply_suggestion(
            "请解答",
            image_data_uris=["data:image/png;base64,not-an-image"],
        )

        self.assertIn("格式不受支持或超过 8 MB", result)

    def test_dify_reply_uses_chat_messages_and_does_not_require_model_name(self):
        service = self.create_service("dify")
        service.model = ""
        with patch.object(service, "_dify_chat", return_value="Dify 答复") as chat:
            result = service.generate_reply_suggestion(
                "请解答图中题目",
                image_data_uris=[PNG_DATA_URI],
            )

        self.assertEqual(result, "Dify 答复")
        query = chat.call_args.args[0]
        self.assertIn("请解答图中题目", query)
        self.assertEqual(
            chat.call_args.kwargs["inputs"]["system"],
            "请帮助教师解答学生问题。",
        )
        self.assertNotIn("model", chat.call_args.kwargs["inputs"])
        self.assertEqual(
            chat.call_args.kwargs["image_data_uris"],
            [PNG_DATA_URI],
        )

    def test_dify_uploads_image_and_passes_upload_id_to_chat(self):
        service = self.create_service("dify")
        upload_response = type(
            "Response",
            (),
            {
                "status_code": 200,
                "json": lambda self: {"id": "upload-1"},
                "close": lambda self: None,
            },
        )()
        chat_response = type(
            "Response",
            (),
            {
                "status_code": 200,
                "json": lambda self: {"answer": "图中内容"},
                "close": lambda self: None,
            },
        )()

        with patch(
            "core.apis.ai_service.requests.post",
            side_effect=[upload_response, chat_response],
        ) as post:
            answer = service._dify_chat("识别图片", [PNG_DATA_URI])

        self.assertEqual(answer, "图中内容")
        upload_call, chat_call = post.call_args_list
        self.assertEqual(
            upload_call.args[0],
            "https://example.test/v1/files/upload",
        )
        self.assertEqual(
            upload_call.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertIn("file", upload_call.kwargs["files"])
        self.assertEqual(
            chat_call.args[0],
            "https://example.test/v1/chat-messages",
        )
        self.assertEqual(
            chat_call.kwargs["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(
            chat_call.kwargs["json"]["files"],
            [{
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": "upload-1",
            }],
        )
        self.assertEqual(
            chat_call.kwargs["json"]["inputs"],
            {"system": "请帮助教师解答学生问题。", "model": "vision-model"},
        )

    def test_dify_connection_test_uses_native_chat_endpoint(self):
        service = self.create_service("dify")
        with patch.object(service, "_dify_chat", return_value="pong") as chat:
            success, message = service.test_connection()

        self.assertTrue(success)
        self.assertIn("Dify", message)
        self.assertEqual(chat.call_args.args, ("ping",))
        self.assertEqual(chat.call_args.kwargs["timeout"], (10, 30))

    def test_dify_auth_header_does_not_duplicate_existing_bearer_prefix(self):
        service = self.create_service("dify")
        service.api_key = "Bearer app-test-key"

        self.assertEqual(
            service._dify_authorization_header(),
            "Bearer app-test-key",
        )

    def test_dify_scoring_sends_scoring_prompt_and_attached_images(self):
        service = self.create_service("dify")
        service.model = ""
        uploaded = [{
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": "answer-1",
        }]
        answer = (
            '{"score": 10, "earned_points": [{"item":"正确",'
            '"points":10,"evidence":"图片中的作答完整"}],'
            '"lost_points":[],"summary":"作答完整。"}'
        )
        with (
            patch.object(service, "_dify_upload_images", return_value=uploaded) as upload,
            patch.object(service, "_dify_chat", return_value=answer) as chat,
        ):
            result = service.generate_exam_score({
                "question": "识别图片并评分",
                "maximum_score": 10,
                "student_answer": "[图片 1]",
                "student_answer_images": [{
                    "data_uri": PNG_DATA_URI,
                    "context": "答卷图片 1",
                }],
            })

        self.assertEqual(result["score"], 10)
        upload.assert_called_once_with([PNG_DATA_URI])
        self.assertIn("评分输入", chat.call_args.args[0])
        self.assertIn("图片 1：答卷图片 1", chat.call_args.args[0])
        self.assertEqual(chat.call_args.kwargs["uploaded_files"], uploaded)
        self.assertIn("只返回 JSON 对象", chat.call_args.kwargs["inputs"]["system"])

    def test_chat_view_extracts_valid_cached_student_image(self):
        message = {
            "image_html": f'<img src="{PNG_DATA_URI}" width="360" />',
        }

        self.assertEqual(ChatView._image_message_data_uri(message), PNG_DATA_URI)

    def test_chat_view_rejects_non_data_image_markup(self):
        message = {"image_html": '<img src="https://example.test/image.png" />'}

        self.assertIsNone(ChatView._image_message_data_uri(message))


if __name__ == "__main__":
    unittest.main()

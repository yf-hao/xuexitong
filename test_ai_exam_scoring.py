import unittest
from unittest.mock import Mock, patch

from core.apis.ai_service import (
    DiscreteMathAIService,
    parse_exam_score_response,
)


class AIExamScoreResponseTests(unittest.TestCase):
    def test_parses_score_earned_points_lost_points_and_summary(self):
        result = parse_exam_score_response(
            '{"score": 8, '
            '"earned_points": [{"item":"步骤正确","points":8,'
            '"evidence":"完成了主要推导"}], '
            '"lost_points": [{"item":"缺少结论","points":2,'
            '"evidence":"未明确写出最终结论"}], '
            '"summary":"主要推理正确。"}',
            10,
        )

        self.assertEqual(result["score"], 8)
        self.assertEqual(result["earned_points"][0]["points"], 8)
        self.assertEqual(result["lost_points"][0]["points"], 2)
        self.assertEqual(result["summary"], "主要推理正确。")

    def test_accepts_json_code_fence(self):
        result = parse_exam_score_response(
            '```json\n{"score": 10, "earned_points": [{"item":"完整",'
            '"points":10,"evidence":"答案完整"}], "lost_points": [],'
            '"summary":"完整作答。"}\n```',
            10,
        )

        self.assertEqual(result["score"], 10)
        self.assertEqual(result["lost_points"], [])

    def test_accepts_half_point_score(self):
        result = parse_exam_score_response(
            '{"score": 10.5, "earned_points": [{"item":"正确内容",'
            '"points":10.5,"evidence":"答案满足对应要求"}], '
            '"lost_points": [{"item":"部分缺漏","points":1.5,'
            '"evidence":"有一项未满足"}], "summary":"基本正确。"}',
            12,
        )

        self.assertEqual(result["score"], 10.5)

    def test_rounds_scores_to_half_point_increments(self):
        for score in (10.3, 10.6):
            response = (
                f'{{"score": {score}, "earned_points": '
                f'[{{"item":"得分项","points":{score},'
                '"evidence":"有答案依据"}], '
                f'"lost_points": [{{"item":"失分项",'
                f'"points":{20 - score},"evidence":"有扣分依据"}}], '
                '"summary":"完成评分。"}'
            )
            with self.subTest(score=score):
                result = parse_exam_score_response(response, 20)

                self.assertEqual(result["score"], 10.5)
                self.assertAlmostEqual(
                    sum(item["points"] for item in result["earned_points"]),
                    10.5,
                )
                self.assertAlmostEqual(
                    sum(item["points"] for item in result["lost_points"]),
                    9.5,
                )

    def test_rejects_invalid_json_and_scores_outside_maximum(self):
        with self.assertRaisesRegex(ValueError, "有效 JSON"):
            parse_exam_score_response("not json", 10)
        with self.assertRaisesRegex(ValueError, "0 到 10"):
            parse_exam_score_response(
                '{"score": 11, "earned_points": [], "lost_points": [],'
                '"summary":"超分"}',
                10,
            )

    def test_rejects_inconsistent_point_totals(self):
        response = (
            '{"score": 8, "earned_points": [{"item":"步骤正确",'
            '"points":7,"evidence":"完成了主要推导"}], '
            '"lost_points": [{"item":"缺少结论","points":2,'
            '"evidence":"未明确写出最终结论"}], "summary":"推理正确。"}'
        )

        with self.assertRaisesRegex(ValueError, "得分点分值之和"):
            parse_exam_score_response(response, 10)

        inconsistent_deduction = response.replace(
            '"points":7,"evidence":"完成了主要推导"',
            '"points":8,"evidence":"完成了主要推导"',
        ).replace(
            '"points":2,"evidence":"未明确写出最终结论"',
            '"points":1,"evidence":"未明确写出最终结论"',
        )
        with self.assertRaisesRegex(ValueError, "失分点分值之和"):
            parse_exam_score_response(inconsistent_deduction, 10)

    def test_scoring_request_does_not_log_prompt_or_response(self):
        service = DiscreteMathAIService.__new__(DiscreteMathAIService)
        service.api_key = "test-key"
        service.base_url = "https://example.test/v1"
        service.model = "test-model"
        service.endpoint_type = "chat_completions"
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"score": 9, "earned_points": '
                    '[{"item":"关键步骤","points":9,"evidence":"步骤完整"}], '
                    '"lost_points": [{"item":"结论不够清楚","points":1,'
                    '"evidence":"结论表述较简略"}], "summary":"整体正确。"}'
                }
            }]
        }
        scoring_data = {
            "question": "private exam question",
            "maximum_score": 10,
            "additional_scoring_requirements": "步骤分占一半。",
        }

        with (
            patch("core.apis.ai_service.requests.post", return_value=response) as post,
            patch("core.apis.ai_service.logger.info") as log_info,
            patch("core.apis.ai_service.logger.warning") as log_warning,
        ):
            result = service.generate_exam_score(scoring_data)

        self.assertEqual(result["score"], 9)
        self.assertIn("private exam question", post.call_args.kwargs["json"]["messages"][1]["content"])
        system_prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("earned_points", system_prompt)
        self.assertIn("lost_points", system_prompt)
        self.assertIn("无法验证的评分点不得给分", system_prompt)
        self.assertIn("不得断言学生确定没有完成", system_prompt)
        self.assertIn(
            "步骤分占一半。",
            post.call_args.kwargs["json"]["messages"][1]["content"],
        )
        log_info.assert_not_called()
        log_warning.assert_not_called()
        response.close.assert_called_once()

    def test_retries_once_when_lost_points_total_is_inconsistent(self):
        service = DiscreteMathAIService.__new__(DiscreteMathAIService)
        service.api_key = "test-key"
        service.base_url = "https://example.test/v1"
        service.model = "test-model"
        service.endpoint_type = "chat_completions"
        invalid_response = Mock()
        invalid_response.status_code = 200
        invalid_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"score": 8, "earned_points": '
                    '[{"item":"步骤正确","points":8,"evidence":"推导正确"}], '
                    '"lost_points": [{"item":"结论缺失","points":1,'
                    '"evidence":"没有结论"}], "summary":"基本正确。"}'
                }
            }]
        }
        corrected_response = Mock()
        corrected_response.status_code = 200
        corrected_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"score": 8, "earned_points": '
                    '[{"item":"步骤正确","points":8,"evidence":"推导正确"}], '
                    '"lost_points": [{"item":"结论缺失","points":2,'
                    '"evidence":"没有结论"}], "summary":"基本正确。"}'
                }
            }]
        }

        with patch(
            "core.apis.ai_service.requests.post",
            side_effect=[invalid_response, corrected_response],
        ) as post:
            result = service.generate_exam_score({
                "question": "示例题目",
                "maximum_score": 10,
            })

        self.assertEqual(result["score"], 8)
        self.assertEqual(result["lost_points"][0]["points"], 2)
        self.assertEqual(post.call_count, 2)
        retry_prompt = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("previous_response", retry_prompt)
        self.assertIn("重新核对并调整", retry_prompt)
        invalid_response.close.assert_called_once()
        corrected_response.close.assert_called_once()

    def test_scoring_request_sends_all_images_for_both_supported_endpoints(self):
        image_data_uris = [
            "data:image/png;base64,aW1hZ2UtMQ==",
            "data:image/jpeg;base64,aW1hZ2UtMg==",
        ]
        scoring_data = {
            "question": "识别图中答案并评分",
            "maximum_score": 10,
            "student_answer": "答案文字",
            "student_answer_images": [
                image_data_uris[0],
                {
                    "data_uri": image_data_uris[1],
                    "context": "DOCX 图片 1，对应正文标记 [图片 1]",
                },
            ],
        }
        reply = (
            '{"score": 10, "earned_points": [{"item":"正确",'
            '"points":10,"evidence":"文字和图片作答完整"}],'
            '"lost_points":[],"summary":"作答完整。"}'
        )

        for endpoint_type in ("chat_completions", "responses"):
            with self.subTest(endpoint_type=endpoint_type):
                service = DiscreteMathAIService.__new__(DiscreteMathAIService)
                service.api_key = "test-key"
                service.base_url = "https://example.test/v1"
                service.model = "vision-model"
                service.endpoint_type = endpoint_type
                response = Mock()
                response.status_code = 200
                if endpoint_type == "responses":
                    response.json.return_value = {"output_text": reply}
                else:
                    response.json.return_value = {
                        "choices": [{"message": {"content": reply}}],
                    }

                with patch(
                    "core.apis.ai_service.requests.post", return_value=response
                ) as post:
                    result = service.generate_exam_score(scoring_data)

                self.assertEqual(result["score"], 10)
                payload = post.call_args.kwargs["json"]
                if endpoint_type == "responses":
                    user_content = payload["input"][1]["content"]
                    images = [
                        item["image_url"]
                        for item in user_content
                        if item["type"] == "input_image"
                    ]
                    prompt_text = "\n".join(
                        item["text"] for item in user_content
                        if item["type"] == "input_text"
                    )
                else:
                    user_content = payload["messages"][1]["content"]
                    images = [
                        item["image_url"]["url"]
                        for item in user_content
                        if item["type"] == "image_url"
                    ]
                    prompt_text = "\n".join(
                        item["text"] for item in user_content
                        if item["type"] == "text"
                    )

                self.assertEqual(images, image_data_uris)
                self.assertIn("答案文字", prompt_text)
                self.assertIn("对应正文标记 [图片 1]", prompt_text)
                self.assertNotIn(image_data_uris[0], prompt_text)
                response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
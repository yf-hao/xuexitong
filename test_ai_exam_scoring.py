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
        self.assertIn(
            "步骤分占一半。",
            post.call_args.kwargs["json"]["messages"][1]["content"],
        )
        log_info.assert_not_called()
        log_warning.assert_not_called()
        response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
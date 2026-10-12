import tempfile
import unittest
from pathlib import Path

from core.utils.exam_score_drafts import (
    ExamScoreDraftStore,
    distribute_group_score,
)


class ExamScoreDistributionTests(unittest.TestCase):
    def test_distributes_integer_total_evenly(self):
        for _ in range(8):
            scores = distribute_group_score(10, [33, 33, 33])

            self.assertEqual(sorted(scores), [3, 3, 4])
            self.assertEqual(sum(scores), 10)

    def test_respects_question_caps_and_decimal_maximums(self):
        capped_scores = distribute_group_score(10, [2, 33, 33])
        decimal_scores = distribute_group_score(5, [2.5, 2.5])

        self.assertEqual(sorted(capped_scores), [2, 4, 4])
        self.assertEqual(sorted(decimal_scores), [2.5, 2.5])

    def test_rejects_total_above_available_maximum(self):
        with self.assertRaisesRegex(ValueError, "超过本题型满分"):
            distribute_group_score(11, [3, 3, 4])


class ExamScoreDraftStoreTests(unittest.TestCase):
    def test_saves_multiple_question_scores_as_one_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExamScoreDraftStore(Path(directory) / "drafts.json")
            store.save_scores([
                ("question-1", 3, {"question_number": "1"}),
                ("question-2", 3, {"question_number": "2"}),
                ("question-3", 4, {"question_number": "3"}),
            ])

            reloaded = ExamScoreDraftStore(Path(directory) / "drafts.json")

            self.assertEqual(reloaded.get_score("question-1"), 3.0)
            self.assertEqual(reloaded.get_score("question-2"), 3.0)
            self.assertEqual(reloaded.get_score("question-3"), 4.0)

    def test_preserves_ai_score_breakdown_as_draft_metadata(self):
        breakdown = {
            "score": 8,
            "earned_points": [{
                "item": "主要推导正确",
                "points": 8,
                "evidence": "推导步骤完整",
            }],
            "lost_points": [{
                "item": "缺少边界分析",
                "points": 2,
                "evidence": "未讨论边界情况",
            }],
            "summary": "整体完成较好。",
        }
        with tempfile.TemporaryDirectory() as directory:
            store = ExamScoreDraftStore(Path(directory) / "drafts.json")
            store.save_score(
                "question-1",
                8,
                exam_id="exam-1",
                ai_score_breakdown=breakdown,
            )

            reloaded = ExamScoreDraftStore(Path(directory) / "drafts.json")

            self.assertEqual(reloaded.get_score("question-1"), 8.0)
            self.assertEqual(
                reloaded.get_entry("question-1")["ai_score_breakdown"],
                breakdown,
            )

    def test_saves_and_reloads_scores_by_exam_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExamScoreDraftStore(Path(directory) / "drafts.json")
            key = store.make_key("exam-1", "answer-1", "student-1", "q-1", "1", "简答题")
            store.save_score(
                key,
                7.5,
                exam_id="exam-1",
                answer_id="answer-1",
                student_id="student-1",
                question_id="q-1",
                question_number="1",
                question_type="简答题",
            )

            reloaded = ExamScoreDraftStore(Path(directory) / "drafts.json")

            self.assertEqual(reloaded.get_score(key), 7.5)
            self.assertEqual(
                reloaded.get_for_attempt("exam-1", "answer-1")[0]["question_id"],
                "q-1",
            )
            self.assertEqual(reloaded.get_for_attempt("exam-1", "answer-2"), [])

    def test_question_keys_are_scoped_to_student_and_attempt(self):
        first = ExamScoreDraftStore.make_key(
            "exam-1", "answer-1", "student-1", "q-1", "1", "简答题"
        )
        other_student = ExamScoreDraftStore.make_key(
            "exam-1", "answer-1", "student-2", "q-1", "1", "简答题"
        )

        self.assertNotEqual(first, other_student)


if __name__ == "__main__":
    unittest.main()
import tempfile
import unittest
from pathlib import Path

from core.utils.exam_score_drafts import ExamScoreDraftStore


class ExamScoreDraftStoreTests(unittest.TestCase):
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
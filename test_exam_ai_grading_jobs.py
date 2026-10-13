import tempfile
import unittest
from pathlib import Path

from core.utils.exam_ai_grading_jobs import ExamAIGradingJobStore


class ExamAIGradingJobStoreTests(unittest.TestCase):
    def test_persists_status_and_reuses_submitted_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            filepath = Path(directory) / "jobs.json"
            store = ExamAIGradingJobStore(filepath)
            store.update_record(
                "exam-1",
                "answer-1",
                "ready_to_submit",
                student_name="学生甲",
                student_id="1001",
                score_results={"q-1": {"score": 3}},
            )
            store.update_record("exam-1", "answer-1", "submitted")

            reopened_store = ExamAIGradingJobStore(filepath)
            record = reopened_store.get_record("exam-1", "answer-1")

        self.assertEqual(record["status"], "submitted")
        self.assertEqual(record["student_name"], "学生甲")
        self.assertEqual(record["score_results"], {"q-1": {"score": 3}})

    def test_issue_can_be_resolved_without_becoming_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExamAIGradingJobStore(Path(directory) / "jobs.json")
            store.update_record(
                "exam-1", "answer-2", "submission_failed", error="网络错误"
            )

            self.assertEqual(len(store.get_exam_issues("exam-1")), 1)
            self.assertTrue(store.resolve_issue("exam-1", "answer-2"))

            self.assertEqual(store.get_exam_issues("exam-1"), [])
            self.assertEqual(
                store.get_record("exam-1", "answer-2")["status"], "resolved"
            )


if __name__ == "__main__":
    unittest.main()
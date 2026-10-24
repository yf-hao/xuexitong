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

    def test_each_rerun_appends_an_attempt_without_losing_current_job_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExamAIGradingJobStore(Path(directory) / "jobs.json")
            for stage, status in (
                ("提交成绩", "submitted"),
                ("评分第 1 题", "stopped"),
            ):
                store.start_attempt(
                    "exam-1", "answer-1",
                    student_name="学生甲", student_id="1001",
                )
                store.update_record(
                    "exam-1",
                    "answer-1",
                    status,
                    student_name="学生甲",
                    student_id="1001",
                    stage=stage,
                    score_results={"q-1": {"score": 3}},
                )
                store.finish_attempt(
                    "exam-1",
                    "answer-1",
                    {"status": status},
                )

            job = store.get_record("exam-1", "answer-1")
            attempts = store.get_exam_visible_records("exam-1")

        self.assertEqual(job["status"], "stopped")
        self.assertEqual(job["score_results"], {"q-1": {"score": 3}})
        self.assertEqual([item["attempt_number"] for item in attempts], [2])
        self.assertEqual([item["status"] for item in attempts], ["stopped"])
        self.assertEqual(
            len(job["history"]), 2,
            "成功轮次保存在任务历史中，但不显示在批改记录列表",
        )
        self.assertEqual(attempts[0]["student_name"], "学生甲")


if __name__ == "__main__":
    unittest.main()
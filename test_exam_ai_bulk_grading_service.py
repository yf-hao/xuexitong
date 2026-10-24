import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.apis.exam_api import ExamReviewContext
from core.services.exam_ai_bulk_grading_service import ExamAIBulkGradingService
from core.services.exam_ai_scoring_service import ExamAIScoringService
from core.utils.exam_ai_grading_jobs import ExamAIGradingJobStore
from core.utils.exam_mark_paper_parser import parse_exam_mark_paper
from core.utils.exam_score_drafts import ExamScoreDraftStore


PAPER_HTML = """
<form id="submitMarking" method="post"
 action="/mooc2-ans/exam/test/submitmark?testUserRelationId=answer-1">
 <input name="testUserRelationId" value="answer-1">
 <input name="testPaperId" value="paper-1">
 <input name="courseId" value="course-1">
 <input name="classId" value="class-1">
 <input name="questionId" value="q1,q2,">
 <input name="sumScore" value="3">
 <input name="perq1" value="10"><input name="scoreq1" value="">
 <textarea name="teacherContentq1"></textarea>
 <input name="perq2" value="5"><input name="scoreq2" value="3" readonly>
</form>
<div class="questionWrap" index="1" name="简答题">
 <input id="fullScoreq1" value="10"><input name="scoreq1" value="">
 <h3 class="mark_name" id="questionStem_q1">解释方法</h3>
 <div class="stuAnswerWords"><div class="SubjectStuAnswer">答案内容</div></div>
</div>
<div class="questionWrap" index="2" name="单选题">
 <input id="fullScoreq2" value="5"><input name="scoreq2" value="3" readonly>
 <h3 class="mark_name" id="questionStem_q2">选择结果</h3>
</div>
"""


class FakeScoringService:
    def __init__(self, result=None, error=None):
        self.result = result or {
            "score": 8,
            "earned_points": [{
                "item": "核心说明", "points": 8, "evidence": "答案内容",
            }],
            "lost_points": [{
                "item": "缺少举例", "points": 2, "evidence": "未提供例子",
            }],
            "summary": "基本正确",
        }
        self.error = error
        self.scored_questions = []

    @staticmethod
    def is_subjective_question(question):
        return question.question_type not in {"单选题", "多选题", "判断题"}

    @staticmethod
    def build_scoring_data(question, rubric):
        return {"question_id": question.question_id, "rubric": rubric}

    def score(self, scoring_data, attachments, session):
        self.scored_questions.append(scoring_data["question_id"])
        if self.error:
            raise self.error
        return self.result


class ExamAIBulkGradingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temp_directory.name)
        self.job_store = ExamAIGradingJobStore(directory / "jobs.json")
        self.score_store = ExamScoreDraftStore(directory / "scores.json")
        self.context = ExamReviewContext(
            course_id="course-1",
            class_id="class-1",
            cpi="cpi-1",
            exam_id="exam-1",
            exam_title="考试",
            class_name="班级",
            marklist_url="https://example.test/marklist",
        )
        self.records = [{
            "id": "answer-1",
            "createUserName": "学生甲",
            "loginName": "1001",
        }]
        self.submissions = []

    def tearDown(self):
        self.temp_directory.cleanup()

    def make_service(self, scoring_service, records=None):
        return ExamAIBulkGradingService(
            object(),
            self.context,
            job_store=self.job_store,
            score_draft_store=self.score_store,
            scoring_service=scoring_service,
            record_fetcher=lambda _session, _context: (
                self.records if records is None else records
            ),
            mark_paper_fetcher=lambda *_args: PAPER_HTML,
            paper_parser=parse_exam_mark_paper,
            submitter=lambda *args, **kwargs: self.submissions.append(
                (args, kwargs)
            ),
            rubric_provider=lambda _question: "",
        )

    def test_scores_only_subjective_questions_and_preserves_objective_score(self):
        scorer = FakeScoringService()
        service = self.make_service(scorer)
        progress = []

        result = service.run(
            progress_callback=lambda current, total, outcome: progress.append(
                (current, total, outcome)
            )
        )

        self.assertEqual(result["outcomes"][0]["status"], "submitted")
        self.assertEqual(
            [item[2]["status"] for item in progress],
            ["processing", "submitted"],
        )
        self.assertEqual(progress[0][2]["student_name"], "学生甲")
        self.assertEqual(scorer.scored_questions, ["q1"])
        self.assertEqual(len(self.submissions), 1)
        form_fields = dict(self.submissions[0][0][3])
        self.assertEqual(form_fields["scoreq1"], "8")
        self.assertEqual(form_fields["scoreq2"], "3")
        self.assertEqual(form_fields["sumScore"], "11")
        self.assertIn("基本正确", form_fields["teacherContentq1"])

    def test_scoring_failure_is_persisted_and_does_not_submit(self):
        service = self.make_service(
            FakeScoringService(error=ValueError("AI 返回的评分无效"))
        )

        result = service.run()

        self.assertEqual(result["outcomes"][0]["status"], "grading_failed")
        self.assertEqual(self.submissions, [])
        saved = self.job_store.get_record("exam-1", "answer-1")
        self.assertEqual(saved["error"], "AI 返回的评分无效")
        self.assertEqual(saved["student_id"], "1001")

    def test_inconsistent_ai_breakdown_is_persisted_without_submission(self):
        scorer = FakeScoringService(result={
            "score": 8,
            "earned_points": [{
                "item": "得分项", "points": 8, "evidence": "依据",
            }],
            "lost_points": [{
                "item": "失分项", "points": 1, "evidence": "依据",
            }],
            "summary": "结果不一致",
        })
        service = self.make_service(scorer)

        result = service.run()

        self.assertEqual(result["outcomes"][0]["status"], "grading_failed")
        self.assertIn("失分点分值之和", result["outcomes"][0]["error"])
        self.assertEqual(self.submissions, [])

    def test_stop_after_scoring_resumes_submission_without_scoring_again(self):
        first_scorer = FakeScoringService()
        first_service = self.make_service(first_scorer)

        stopped = first_service.run(
            stop_requested=lambda: bool(first_scorer.scored_questions)
        )

        self.assertEqual(
            stopped["outcomes"][0]["status"], "ready_to_submit"
        )
        self.assertEqual(self.submissions, [])
        retry_scorer = FakeScoringService(
            error=AssertionError("已保存评分不应重新调用 AI")
        )
        resumed_service = self.make_service(retry_scorer)

        resumed = resumed_service.run()

        self.assertEqual(resumed["outcomes"][0]["status"], "submitted")
        self.assertEqual(retry_scorer.scored_questions, [])
        self.assertEqual(len(self.submissions), 1)

    def test_submission_failure_retry_reuses_saved_ai_result(self):
        first_scorer = FakeScoringService()
        failing_service = self.make_service(first_scorer)
        failing_service.submitter = lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(RuntimeError("提交失败"))
        )

        failed = failing_service.run()

        self.assertEqual(
            failed["outcomes"][0]["status"], "submission_failed"
        )
        retry_scorer = FakeScoringService(
            error=AssertionError("提交重试不应重新调用 AI")
        )
        resumed_service = self.make_service(retry_scorer)

        resumed = resumed_service.run()

        self.assertEqual(resumed["outcomes"][0]["status"], "submitted")
        self.assertEqual(retry_scorer.scored_questions, [])
        self.assertEqual(len(self.submissions), 1)

    def test_already_submitted_answer_is_not_scored_or_submitted_again(self):
        result = FakeScoringService().result
        rubric_fingerprint = ExamAIScoringService.rubric_fingerprint("")
        self.job_store.update_record(
            "exam-1",
            "answer-1",
            "submitted",
            student_name="学生甲",
            score_results={"q1": result},
            rubric_fingerprints={"q1": rubric_fingerprint},
        )
        scorer = FakeScoringService()
        service = self.make_service(scorer)

        result = service.run()

        self.assertEqual(result["outcomes"][0]["status"], "submitted")
        self.assertEqual(scorer.scored_questions, [])
        self.assertEqual(self.submissions, [])

    def test_changed_rubric_regrades_submitted_answer_after_confirmation(self):
        old_result = FakeScoringService().result
        old_fingerprint = ExamAIScoringService.rubric_fingerprint("旧要求")
        new_fingerprint = ExamAIScoringService.rubric_fingerprint("新要求")
        self.job_store.update_record(
            "exam-1",
            "answer-1",
            "submitted",
            student_name="学生甲",
            student_id="1001",
            score_results={"q1": old_result},
            rubric_fingerprints={"q1": old_fingerprint},
        )
        scorer = FakeScoringService()
        service = self.make_service(scorer)
        service.rubric_provider = lambda _question: "新要求"
        confirmations = []

        result = service.run(
            regrade_confirmation_callback=lambda submissions: (
                confirmations.append(submissions) or True
            )
        )

        self.assertEqual(confirmations[0][0]["student_name"], "学生甲")
        self.assertEqual(
            confirmations[0][0]["changed_questions"], ["1"]
        )
        self.assertEqual(scorer.scored_questions, ["q1"])
        self.assertEqual(result["outcomes"][0]["status"], "submitted")
        self.assertEqual(len(self.submissions), 1)
        saved_job = self.job_store.get_record("exam-1", "answer-1")
        self.assertEqual(
            saved_job["rubric_fingerprints"]["q1"], new_fingerprint
        )

    def test_declining_changed_rubric_confirmation_leaves_submission_untouched(self):
        self.job_store.update_record(
            "exam-1",
            "answer-1",
            "submitted",
            student_name="学生甲",
            student_id="1001",
            score_results={"q1": FakeScoringService().result},
            rubric_fingerprints={
                "q1": ExamAIScoringService.rubric_fingerprint("旧要求")
            },
        )
        scorer = FakeScoringService()
        service = self.make_service(scorer)
        service.rubric_provider = lambda _question: "新要求"
        self.score_store.save_score(
            self.score_store.make_key(
                "exam-1", "answer-1", "1001", "q1", "1", "简答题"
            ),
            8,
            ai_score_breakdown=FakeScoringService().result,
            rubric_fingerprint=ExamAIScoringService.rubric_fingerprint(
                "新要求"
            ),
        )

        result = service.run(
            regrade_confirmation_callback=lambda _submissions: False
        )

        self.assertTrue(result["regrade_cancelled"])
        self.assertEqual(scorer.scored_questions, [])
        self.assertEqual(self.submissions, [])
        self.assertEqual(
            self.job_store.get_record("exam-1", "answer-1")["status"],
            "submitted",
        )

    def test_reuses_single_question_ai_score_draft(self):
        question = parse_exam_mark_paper(PAPER_HTML).questions[0]
        draft_key = self.score_store.make_key(
            "exam-1", "answer-1", "1001", "q1", "1", "简答题"
        )
        saved_breakdown = {
            "score": 8,
            "earned_points": [{
                "item": "核心说明", "points": 8, "evidence": "答案内容",
            }],
            "lost_points": [{
                "item": "缺少举例", "points": 2, "evidence": "未提供例子",
            }],
            "summary": "基本正确",
        }
        self.score_store.save_score(
            draft_key,
            8,
            ai_score_breakdown=saved_breakdown,
            rubric_fingerprint=ExamAIScoringService.rubric_fingerprint(""),
        )
        scorer = FakeScoringService(
            error=AssertionError("应复用答卷中的 AI 评分草稿")
        )
        service = self.make_service(scorer)

        result = service.run()

        self.assertEqual(result["outcomes"][0]["status"], "submitted")
        self.assertEqual(scorer.scored_questions, [])
        self.assertEqual(len(self.submissions), 1)


if __name__ == "__main__":
    unittest.main()
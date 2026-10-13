import json

from core.apis.exam_api import (
    exam_mark_paper_referer, fetch_all_submitted_exam_records,
    fetch_exam_mark_paper, submit_exam_mark,
)
from core.services.exam_ai_scoring_service import ExamAIScoringService
from core.utils.exam_ai_grading_jobs import ExamAIGradingJobStore
from core.utils.exam_mark_paper_parser import parse_exam_mark_paper
from core.utils.exam_mark_submission import build_exam_mark_submission_payload
from core.utils.exam_score_drafts import ExamScoreDraftStore
from core.apis.ai_service import parse_exam_score_response


class ExamAIBulkGradingService:
    def __init__(
        self,
        session,
        context,
        *,
        job_store=None,
        score_draft_store=None,
        scoring_service=None,
        record_fetcher=None,
        mark_paper_fetcher=None,
        paper_parser=None,
        submitter=None,
        rubric_provider=None,
    ):
        self.session = session
        self.context = context
        self.job_store = job_store or ExamAIGradingJobStore()
        self.score_draft_store = score_draft_store or ExamScoreDraftStore()
        self.scoring_service = scoring_service or ExamAIScoringService()
        self.record_fetcher = record_fetcher or self._fetch_records_for_grading
        self.mark_paper_fetcher = mark_paper_fetcher or fetch_exam_mark_paper
        self.paper_parser = paper_parser or parse_exam_mark_paper
        self.submitter = submitter or submit_exam_mark
        self.rubric_provider = rubric_provider or (lambda _question: "")

    @staticmethod
    def _fetch_records_for_grading(session, context):
        return fetch_all_submitted_exam_records(
            session, context, include_ips=False
        )

    def run(
        self, progress_callback=None, stop_requested=None, answer_ids=None
    ):
        stop_requested = stop_requested or (lambda: False)
        records = self.record_fetcher(self.session, self.context)
        if answer_ids is not None:
            answer_ids = {str(answer_id) for answer_id in answer_ids}
            records = [
                record for record in records
                if str(record.get("id") or "") in answer_ids
            ]
        outcomes = []
        total = len(records)
        for index, record in enumerate(records, 1):
            if stop_requested():
                break
            outcome = self._process_record(record, stop_requested)
            outcomes.append(outcome)
            if progress_callback is not None:
                progress_callback(index, total, outcome)
        return {
            "total": total,
            "processed": len(outcomes),
            "stopped": stop_requested(),
            "outcomes": outcomes,
        }

    def _process_record(self, record, stop_requested):
        answer_id = str(record.get("id") or "")
        student_name = str(record.get("createUserName") or "")
        student_id = str(record.get("loginName") or "")
        if not answer_id:
            return {
                "answer_id": "",
                "student_name": student_name,
                "status": "grading_failed",
                "error": "已交答卷记录缺少 ID，无法持久化或批改",
            }

        job = self.job_store.get_record(self.context.exam_id, answer_id) or {}
        if job.get("status") in self.job_store.TERMINAL_STATUSES:
            return self._outcome(answer_id, student_name, job)

        score_results = dict(job.get("score_results") or {})
        try:
            self.job_store.update_record(
                self.context.exam_id,
                answer_id,
                "grading",
                student_name=student_name,
                student_id=student_id,
                stage="读取答卷",
                score_results=score_results,
            )
            html = self.mark_paper_fetcher(
                self.session, self.context, answer_id
            )
            content = self.paper_parser(
                html,
                referer=exam_mark_paper_referer(self.context, answer_id),
            )
        except Exception as exc:
            return self._fail(
                answer_id, student_name, student_id, "grading_failed",
                "读取答卷", str(exc), score_results,
            )

        subjective_questions = [
            question
            for question in content.questions
            if self.scoring_service.is_subjective_question(question)
        ]
        if not subjective_questions:
            job = self.job_store.update_record(
                self.context.exam_id,
                answer_id,
                "no_subjective",
                student_name=student_name,
                student_id=student_id,
                stage="没有可评分主观题",
            )
            return self._outcome(answer_id, student_name, job)

        for question in subjective_questions:
            question_id = str(question.question_id or "")
            if not question_id:
                return self._fail(
                    answer_id, student_name, student_id, "grading_failed",
                    f"读取第 {question.number} 题", "主观题缺少题目 ID",
                    score_results,
                )
            result = self._saved_result(
                answer_id, student_id, question, score_results
            )
            if result is None:
                if stop_requested():
                    self.job_store.update_record(
                        self.context.exam_id,
                        answer_id,
                        "stopped",
                        student_name=student_name,
                        student_id=student_id,
                        stage=f"等待第 {question.number} 题评分",
                        score_results=score_results,
                    )
                    return {
                        "answer_id": answer_id,
                        "student_name": student_name,
                        "status": "stopped",
                    }
                try:
                    rubric = str(self.rubric_provider(question) or "").strip()
                    if len(rubric) > 5000:
                        raise ValueError("追加评分要求不能超过 5000 字符")
                    if question.score is None or question.score <= 0:
                        raise ValueError("该题缺少有效满分，无法校验 AI 返回的分数")
                    scoring_data = self.scoring_service.build_scoring_data(
                        question, rubric
                    )
                    result = self.scoring_service.score(
                        scoring_data, question.attachments, self.session
                    )
                    result = parse_exam_score_response(
                        json.dumps(result, ensure_ascii=False), question.score
                    )
                    draft_key = self.score_draft_store.make_key(
                        self.context.exam_id,
                        answer_id,
                        student_id,
                        question.question_id,
                        question.number,
                        question.question_type,
                    )
                    self.score_draft_store.save_score(
                        draft_key,
                        result["score"],
                        exam_id=self.context.exam_id,
                        answer_id=answer_id,
                        student_id=student_id,
                        question_id=question.question_id,
                        question_number=question.number,
                        question_type=question.question_type,
                        ai_score_breakdown=result,
                    )
                except Exception as exc:
                    return self._fail(
                        answer_id,
                        student_name,
                        student_id,
                        "grading_failed",
                        f"AI 评分第 {question.number} 题",
                        str(exc),
                        score_results,
                    )
                score_results[question_id] = result
                self.job_store.update_record(
                    self.context.exam_id,
                    answer_id,
                    "grading",
                    student_name=student_name,
                    student_id=student_id,
                    stage=f"已完成第 {question.number} 题评分",
                    score_results=score_results,
                )
            else:
                score_results[question_id] = result

        if stop_requested():
            self.job_store.update_record(
                self.context.exam_id,
                answer_id,
                "ready_to_submit",
                student_name=student_name,
                student_id=student_id,
                stage="评分已完成，等待提交",
                score_results=score_results,
            )
            return {
                "answer_id": answer_id,
                "student_name": student_name,
                "status": "ready_to_submit",
            }

        self.job_store.update_record(
            self.context.exam_id,
            answer_id,
            "ready_to_submit",
            student_name=student_name,
            student_id=student_id,
            stage="评分完成，正在提交",
            score_results=score_results,
        )
        score_overrides = {
            question_id: result["score"]
            for question_id, result in score_results.items()
        }
        try:
            action, query_params, form_fields, referer = (
                build_exam_mark_submission_payload(
                    content,
                    score_overrides=score_overrides,
                    ai_breakdowns=score_results,
                )
            )
            self.submitter(
                self.session,
                action,
                query_params,
                form_fields,
                referer=referer,
            )
        except Exception as exc:
            return self._fail(
                answer_id,
                student_name,
                student_id,
                "submission_failed",
                "提交批阅结果",
                str(exc),
                score_results,
            )

        job = self.job_store.update_record(
            self.context.exam_id,
            answer_id,
            "submitted",
            student_name=student_name,
            student_id=student_id,
            stage="已提交",
            score_results=score_results,
        )
        return self._outcome(answer_id, student_name, job)

    def _saved_result(self, answer_id, student_id, question, score_results):
        question_id = str(question.question_id or "")
        result = score_results.get(question_id)
        if result is None:
            draft_key = self.score_draft_store.make_key(
                self.context.exam_id,
                answer_id,
                student_id,
                question.question_id,
                question.number,
                question.question_type,
            )
            try:
                entry = self.score_draft_store.get_entry(draft_key)
            except (OSError, ValueError):
                entry = None
            result = entry.get("ai_score_breakdown") if entry else None
        if not isinstance(result, dict):
            return None
        if question.score is None or question.score <= 0:
            return None
        try:
            return parse_exam_score_response(
                json.dumps(result, ensure_ascii=False), question.score
            )
        except (TypeError, ValueError):
            return None

    def _fail(
        self, answer_id, student_name, student_id, status, stage, error,
        score_results,
    ):
        self.job_store.update_record(
            self.context.exam_id,
            answer_id,
            status,
            student_name=student_name,
            student_id=student_id,
            stage=stage,
            error=error,
            score_results=score_results,
        )
        return {
            "answer_id": answer_id,
            "student_name": student_name,
            "status": status,
            "stage": stage,
            "error": error,
        }

    @staticmethod
    def _outcome(answer_id, student_name, job):
        return {
            "answer_id": answer_id,
            "student_name": student_name,
            "status": job.get("status", "unknown"),
            "error": job.get("error", ""),
        }
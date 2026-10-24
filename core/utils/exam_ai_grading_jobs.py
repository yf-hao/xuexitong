import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.config import DATA_DIR


class ExamAIGradingJobStore:
    TERMINAL_STATUSES = {"submitted", "no_subjective", "resolved"}
    ISSUE_STATUSES = {"grading_failed", "submission_failed"}
    ALLOWED_STATUSES = TERMINAL_STATUSES | ISSUE_STATUSES | {
        "pending", "grading", "ready_to_submit", "stopped",
    }

    def __init__(self, filepath=None):
        self.filepath = Path(
            filepath or Path(DATA_DIR) / "exam_ai_grading_jobs.json"
        )
        self._active_attempts = {}

    @staticmethod
    def make_key(exam_id, answer_id):
        return json.dumps(
            [str(exam_id), str(answer_id)],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _load(self):
        if not self.filepath.exists():
            return {"version": 1, "jobs": {}}
        with self.filepath.open("r", encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            raise ValueError("AI 批改任务文件格式无效")
        return data

    def get_record(self, exam_id, answer_id):
        key = self.make_key(exam_id, answer_id)
        record = self._load()["jobs"].get(key)
        return dict(record) if isinstance(record, dict) else None

    def get_exam_records(self, exam_id):
        exam_id = str(exam_id)
        return [
            dict(record)
            for record in self._load()["jobs"].values()
            if isinstance(record, dict)
            and str(record.get("exam_id")) == exam_id
        ]

    def get_exam_issues(self, exam_id):
        return [
            record for record in self.get_exam_records(exam_id)
            if record.get("status") in self.ISSUE_STATUSES
        ]

    def get_exam_visible_records(self, exam_id):
        records = []
        for job in self.get_exam_records(exam_id):
            history = job.get("history")
            if isinstance(history, list):
                records.extend(
                    dict(attempt) for attempt in history
                    if isinstance(attempt, dict)
                    and attempt.get("status") in self.visible_statuses()
                )
            elif job.get("status") in self.visible_statuses():
                records.append(job)
        return sorted(
            records,
            key=lambda record: record.get("updated_at", ""),
            reverse=True,
        )

    @classmethod
    def visible_statuses(cls):
        return cls.ISSUE_STATUSES | {
            "pending", "grading", "ready_to_submit", "stopped",
        }

    def start_attempt(self, exam_id, answer_id, *, student_name="", student_id=""):
        key = self.make_key(exam_id, answer_id)
        data = self._load()
        job = data["jobs"].get(key, {})
        if not isinstance(job, dict):
            job = {}
        history = job.get("history")
        if not isinstance(history, list):
            history = []
        attempt_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        attempt = {
            "attempt_id": attempt_id,
            "attempt_number": len(history) + 1,
            "exam_id": str(exam_id),
            "answer_id": str(answer_id),
            "student_name": str(student_name or job.get("student_name", "")),
            "student_id": str(student_id or job.get("student_id", "")),
            "status": "pending",
            "stage": "本轮开始",
            "error": "",
            "started_at": now,
            "updated_at": now,
        }
        history.append(attempt)
        job["history"] = history
        data["jobs"][key] = job
        self._save(data)
        self._active_attempts[(str(exam_id), str(answer_id))] = attempt_id
        return attempt_id

    def _update_attempt(self, exam_id, answer_id, attempt_id, details):
        key = self.make_key(exam_id, answer_id)
        data = self._load()
        job = data["jobs"].get(key, {})
        if not isinstance(job, dict):
            return
        history = job.get("history")
        if not isinstance(history, list):
            return
        now = datetime.now(timezone.utc).isoformat()
        for attempt in history:
            if attempt.get("attempt_id") == attempt_id:
                attempt.update(details)
                attempt["updated_at"] = now
                self._save(data)
                return

    def finish_attempt(self, exam_id, answer_id, outcome, *, stage=""):
        attempt_id = self._active_attempts.pop(
            (str(exam_id), str(answer_id)), None
        )
        if attempt_id is None:
            return
        details = {
            "status": str(outcome.get("status", "unknown")),
            "error": str(outcome.get("error", "")),
        }
        final_stage = stage or outcome.get("stage", "")
        if final_stage:
            details["stage"] = str(final_stage)
        self._update_attempt(exam_id, answer_id, attempt_id, details)
        if outcome.get("status") in {"submitted", "no_subjective"}:
            self._resolve_previous_attempts(exam_id, answer_id, attempt_id)

    def _resolve_previous_attempts(self, exam_id, answer_id, current_attempt_id):
        key = self.make_key(exam_id, answer_id)
        data = self._load()
        job = data["jobs"].get(key, {})
        if not isinstance(job, dict) or not isinstance(job.get("history"), list):
            return
        changed = False
        for attempt in job["history"]:
            if (
                attempt.get("attempt_id") != current_attempt_id
                and attempt.get("status") in self.visible_statuses()
            ):
                attempt["status"] = "resolved"
                attempt["stage"] = "后续重试成功，异常已解除"
                attempt["updated_at"] = datetime.now(timezone.utc).isoformat()
                changed = True
        if changed:
            self._save(data)

    def resolve_attempt(self, exam_id, attempt_id):
        for job in self.get_exam_records(exam_id):
            for attempt in job.get("history", []):
                if attempt.get("attempt_id") != attempt_id:
                    continue
                if (
                    job.get("status") in self.ISSUE_STATUSES
                    and job.get("history")
                    and job["history"][-1].get("attempt_id") == attempt_id
                ):
                    self.update_record(
                        exam_id,
                        attempt["answer_id"],
                        "resolved",
                        student_name=job.get("student_name", ""),
                        student_id=job.get("student_id", ""),
                        stage="已由教师标记处理",
                    )
                self._update_attempt(
                    exam_id,
                    attempt["answer_id"],
                    attempt_id,
                    {"status": "resolved", "stage": "已由教师标记处理"},
                )
                return True
        return False

    def update_record(
        self, exam_id, answer_id, status, *, student_name="", student_id="",
        error="", stage="", **details,
    ):
        if status not in self.ALLOWED_STATUSES:
            raise ValueError(f"未知 AI 批改任务状态：{status}")
        key = self.make_key(exam_id, answer_id)
        data = self._load()
        previous = data["jobs"].get(key, {})
        if not isinstance(previous, dict):
            previous = {}
        record = {
            **previous,
            "exam_id": str(exam_id),
            "answer_id": str(answer_id),
            "student_name": str(student_name or previous.get("student_name", "")),
            "student_id": str(student_id or previous.get("student_id", "")),
            "status": status,
            "stage": str(stage),
            "error": str(error),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        record.update(details)
        data["jobs"][key] = record
        attempt_id = self._active_attempts.get(
            (str(exam_id), str(answer_id))
        )
        if attempt_id:
            history = record.get("history")
            if isinstance(history, list):
                now = record["updated_at"]
                for attempt in history:
                    if attempt.get("attempt_id") == attempt_id:
                        attempt.update({
                            "student_name": record["student_name"],
                            "student_id": record["student_id"],
                            "status": status,
                            "stage": str(stage),
                            "error": str(error),
                            "updated_at": now,
                        })
                        break
        self._save(data)
        return dict(record)

    def resolve_issue(self, exam_id, answer_id):
        record = self.get_record(exam_id, answer_id)
        if record is None or record.get("status") not in self.ISSUE_STATUSES:
            return False
        self.update_record(
            exam_id,
            answer_id,
            "resolved",
            student_name=record.get("student_name", ""),
            student_id=record.get("student_id", ""),
            stage="已由教师标记处理",
            score_results=record.get("score_results", {}),
        )
        return True

    def _save(self, data):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.filepath.parent,
                delete=False,
            ) as target:
                temporary_path = Path(target.name)
                json.dump(data, target, ensure_ascii=False, indent=2)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, self.filepath)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
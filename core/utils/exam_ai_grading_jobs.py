import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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
        visible_statuses = self.ISSUE_STATUSES | {
            "pending", "grading", "ready_to_submit", "stopped",
        }
        records = [
            record for record in self.get_exam_records(exam_id)
            if record.get("status") in visible_statuses
        ]
        return sorted(
            records,
            key=lambda record: record.get("updated_at", ""),
            reverse=True,
        )

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
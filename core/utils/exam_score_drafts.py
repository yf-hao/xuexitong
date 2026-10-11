import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from core.config import DATA_DIR


class ExamScoreDraftStore:
    def __init__(self, filepath=None):
        self.filepath = Path(filepath or Path(DATA_DIR) / "exam_score_drafts.json")

    @staticmethod
    def make_key(exam_id, answer_id, student_id, question_id, number, question_type):
        identity = json.dumps(
            [exam_id, answer_id, student_id, question_id, number, question_type],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _load(self):
        if not self.filepath.exists():
            return {"version": 1, "drafts": {}}
        with self.filepath.open("r", encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict) or not isinstance(data.get("drafts"), dict):
            raise ValueError("主观题分数草稿文件格式无效")
        return data

    def get_score(self, key):
        entry = self._load()["drafts"].get(key)
        return entry.get("score") if isinstance(entry, dict) else None

    def save_score(self, key, score, **metadata):
        data = self._load()
        entry = dict(metadata)
        entry["score"] = float(score)
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        data["version"] = 1
        data["drafts"][key] = entry

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

    def get_for_attempt(self, exam_id, answer_id):
        drafts = self._load()["drafts"]
        return [
            dict(entry, key=key)
            for key, entry in drafts.items()
            if entry.get("exam_id") == str(exam_id)
            and entry.get("answer_id") == str(answer_id)
        ]
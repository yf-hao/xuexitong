import hashlib
import json
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from core.config import DATA_DIR


def distribute_group_score(total_score, maximum_scores):
    try:
        total_value = float(total_score)
        score_limits = [float(score) for score in maximum_scores]
    except (TypeError, ValueError) as exc:
        raise ValueError("总分或单题满分无效") from exc

    if not score_limits:
        raise ValueError("当前题型没有可评分试题")
    if (
        not math.isfinite(total_value)
        or total_value < 0
        or any(not math.isfinite(score) or score < 0 for score in score_limits)
    ):
        raise ValueError("总分或单题满分无效")

    total_cents = round(total_value * 100)
    limit_cents = [round(score * 100) for score in score_limits]
    if not math.isclose(total_value * 100, total_cents, abs_tol=1e-6):
        raise ValueError("总分最多支持两位小数")
    if total_cents > sum(limit_cents):
        raise ValueError("输入总分超过本题型满分")

    use_whole_points = (
        total_cents % 100 == 0
        and sum(limit // 100 for limit in limit_cents) >= total_cents // 100
    )
    if use_whole_points:
        target = total_cents // 100
        limits = [limit // 100 for limit in limit_cents]
    else:
        target = total_cents
        limits = limit_cents

    allocations = [0] * len(limits)
    active = list(range(len(limits)))
    remaining = target
    chooser = random.SystemRandom()
    while active:
        base, remainder = divmod(remaining, len(active))
        capped = [index for index in active if limits[index] < base]
        if capped:
            capped_set = set(capped)
            for index in capped:
                allocations[index] = limits[index]
                remaining -= limits[index]
            active = [index for index in active if index not in capped_set]
            continue

        bonus_candidates = [
            index for index in active if limits[index] > base
        ]
        if len(bonus_candidates) < remainder:
            raise ValueError("无法在单题满分范围内分配总分")
        bonus_indices = set(chooser.sample(bonus_candidates, remainder))
        for index in active:
            allocations[index] = base + (index in bonus_indices)
        break

    if use_whole_points:
        return tuple(allocations)
    return tuple(score / 100 for score in allocations)


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
        entry = self.get_entry(key)
        return entry.get("score") if isinstance(entry, dict) else None

    def get_entry(self, key):
        entry = self._load()["drafts"].get(key)
        return dict(entry) if isinstance(entry, dict) else None

    def save_score(self, key, score, **metadata):
        self.save_scores([(key, score, metadata)])

    def save_scores(self, scores):
        prepared_scores = [
            (key, float(score), dict(metadata))
            for key, score, metadata in scores
        ]
        if not prepared_scores:
            return

        data = self._load()
        updated_at = datetime.now(timezone.utc).isoformat()
        for key, score, metadata in prepared_scores:
            entry = dict(metadata)
            entry["score"] = score
            entry["updated_at"] = updated_at
            data["drafts"][key] = entry
        data["version"] = 1

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
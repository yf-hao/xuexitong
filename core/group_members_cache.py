"""群成员缓存读写与查找。"""
import json
import re
from pathlib import Path

from core.config import DATA_DIR


GROUP_MEMBERS_CACHE_DIR = Path(DATA_DIR) / "data" / "group_members"


def sanitize_group_cache_filename(name: str, fallback: str = "") -> str:
    normalized = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "").strip())
    normalized = normalized.strip().strip(".")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or str(fallback or "").strip()


def build_group_cache_name(group_name: str, class_name: str = "") -> str:
    group_name = str(group_name or "").strip()
    class_name = str(class_name or "").strip()
    if group_name and class_name and class_name != group_name:
        return f"{group_name}-{class_name}"
    return group_name or class_name


def build_group_members_cache_path(group_name: str, class_name: str = "", fallback: str = "", cache_dir: Path | None = None) -> Path:
    cache_dir = Path(cache_dir or GROUP_MEMBERS_CACHE_DIR)
    cache_name = build_group_cache_name(group_name, class_name)
    file_stem = sanitize_group_cache_filename(cache_name, fallback=fallback)
    return cache_dir / f"{file_stem}.json"


def candidate_group_members_cache_paths(group_name: str, class_name: str = "", fallback: str = "", cache_dir: Path | None = None) -> list[Path]:
    cache_dir = Path(cache_dir or GROUP_MEMBERS_CACHE_DIR)
    candidates: list[Path] = []
    for path in (
        build_group_members_cache_path(group_name, class_name, fallback=fallback, cache_dir=cache_dir),
        build_group_members_cache_path(group_name, "", fallback=fallback, cache_dir=cache_dir),
        cache_dir / f"{str(fallback or '').strip()}.json",
    ):
        if path not in candidates:
            candidates.append(path)
    return candidates


def _normalize_members(payload) -> list[dict]:
    if not isinstance(payload, list):
        return []
    members = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        member = dict(item)
        member["person_id"] = str(member.get("person_id") or member.get("tuid") or "")
        member["name"] = str(member.get("name") or "未知")
        student_id = str(member.get("student_id") or member.get("studentId") or "")
        puid = str(member.get("puid") or "")
        if student_id and puid and student_id == puid:
            student_id = ""
        member["student_id"] = student_id
        member["avatar_url"] = str(member.get("avatar_url") or "")
        if member.get("tuid") not in (None, "") or member["person_id"]:
            member["tuid"] = str(member.get("tuid") or member["person_id"])
        if puid:
            member["puid"] = puid
        members.append(member)
    return members


def load_group_members_cache(group_name: str, class_name: str = "", fallback: str = "", cache_dir: Path | None = None) -> tuple[list[dict], Path | None]:
    for path in candidate_group_members_cache_paths(group_name, class_name, fallback=fallback, cache_dir=cache_dir):
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return _normalize_members(json.load(f)), path
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return [], path
    return [], None


def resolve_student_from_group_cache(group_name: str, class_name: str, student_name: str, fallback: str = "", cache_dir: Path | None = None) -> dict:
    normalized_student_name = str(student_name or "").strip()
    members, cache_path = load_group_members_cache(group_name, class_name, fallback=fallback, cache_dir=cache_dir)
    if cache_path is None:
        return {"status": "cache_missing", "matches": [], "cache_path": None}
    if not normalized_student_name:
        return {"status": "not_found", "matches": [], "cache_path": cache_path}

    matches = [member for member in members if str(member.get("name") or "").strip() == normalized_student_name]
    if len(matches) == 1:
        return {"status": "success", "matches": matches, "cache_path": cache_path}
    if len(matches) > 1:
        return {"status": "duplicate", "matches": matches, "cache_path": cache_path}
    return {"status": "not_found", "matches": [], "cache_path": cache_path}

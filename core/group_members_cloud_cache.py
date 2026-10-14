"""Cloud backup support for locally cached group members."""
import json
import tempfile
from pathlib import Path

from core.logger import get_logger

from core.group_members_cache import (
    GROUP_MEMBERS_CACHE_DIR,
    _normalize_members,
    build_group_members_cache_path,
    load_group_members_cache,
    save_group_members_cache,
)


BACKUP_FOLDER_NAME = "backup"


def _is_file(item: dict) -> bool:
    return str(item.get("isfile", "0")).strip().lower() in {"1", "true"}


def _cloud_context(crawler) -> tuple[dict, str]:
    result = crawler.get_cloud_drive_base_info()
    if not isinstance(result, dict) or not result.get("success"):
        error = result.get("error", "无法获取云盘信息") if isinstance(result, dict) else "无法获取云盘信息"
        raise RuntimeError(error)

    cloud_info = result.get("cloud_info")
    if not isinstance(cloud_info, dict):
        raise RuntimeError("云盘信息缺少目录凭据")
    token = str(result.get("token") or cloud_info.get("token") or "").strip()
    required = ("rootdir", "currentPuid", "encstr")
    missing = [key for key in required if not str(cloud_info.get(key) or "").strip()]
    if not token or missing:
        raise RuntimeError("云盘凭据不完整，无法访问 backup 目录")
    return cloud_info, token


def _list_items(crawler, cloud_info: dict, token: str, folder_id) -> list[dict]:
    result = crawler.get_file_list(
        puid=cloud_info["currentPuid"],
        enc=cloud_info["encstr"],
        parent_id=folder_id,
        token=token,
    )
    if not isinstance(result, dict) or not result.get("success"):
        error = result.get("error", "获取云盘目录失败") if isinstance(result, dict) else "获取云盘目录失败"
        raise RuntimeError(error)
    items = result.get("list", [])
    if not isinstance(items, list):
        raise RuntimeError("云盘目录返回格式无效")
    return [item for item in items if isinstance(item, dict)]


def _named_item(items: list[dict], name: str, want_file: bool):
    matches = [
        item for item in items
        if str(item.get("name") or "") == name and _is_file(item) == want_file
    ]
    if len(matches) > 1:
        raise RuntimeError(f"云盘中存在多个同名项目：{name}")
    return matches[0] if matches else None


def _ensure_backup_folder(crawler, cloud_info: dict, token: str):
    root_id = cloud_info["rootdir"]
    root_items = _list_items(crawler, cloud_info, token, root_id)
    backup = _named_item(root_items, BACKUP_FOLDER_NAME, want_file=False)
    if backup and backup.get("id") is not None:
        return backup["id"]

    create_result = crawler.create_cloud_drive_folder(
        parent_id=root_id,
        folder_name=BACKUP_FOLDER_NAME,
        token=token,
    )
    # Re-list even after a failed create: another request may have created it
    # concurrently, and the server may omit the folder ID on successful create.
    root_items = _list_items(crawler, cloud_info, token, root_id)
    backup = _named_item(root_items, BACKUP_FOLDER_NAME, want_file=False)
    if backup and backup.get("id") is not None:
        return backup["id"]
    if not isinstance(create_result, dict) or not create_result.get("success"):
        error = create_result.get("error", "创建 backup 文件夹失败") if isinstance(create_result, dict) else "创建 backup 文件夹失败"
        raise RuntimeError(error)
    raise RuntimeError("backup 文件夹创建成功，但无法读取其目录 ID")


def _upload_cache_file(crawler, cloud_info: dict, token: str, backup_id, cache_path: Path) -> bool:
    backup_items = _list_items(crawler, cloud_info, token, backup_id)
    if _named_item(backup_items, cache_path.name, want_file=True):
        return True
    upload_token = str(cloud_info.get("_token") or "").strip()
    if not upload_token:
        raise RuntimeError("云盘信息缺少上传凭据，无法上传群成员缓存")

    upload_url_result = crawler.generate_upload_url(
        puid=cloud_info["currentPuid"],
        folder_id=backup_id,
        _token=upload_token,
        p_auth_token=token,
    )
    if not isinstance(upload_url_result, dict) or not upload_url_result.get("success"):
        error = upload_url_result.get("error", "生成缓存上传地址失败") if isinstance(upload_url_result, dict) else "生成缓存上传地址失败"
        raise RuntimeError(error)

    upload_result = crawler.upload_file_to_cloud(
        upload_url=upload_url_result.get("upload_url"),
        file_path=str(cache_path),
        token=token,
    )
    if not isinstance(upload_result, dict) or not upload_result.get("success"):
        error = upload_result.get("error", "上传群成员缓存失败") if isinstance(upload_result, dict) else "上传群成员缓存失败"
        raise RuntimeError(error)
    return False


def sync_group_members_cache_to_backup(crawler, cache_path: str | Path) -> dict:
    """Upload a local group cache to backup, creating backup when necessary."""
    cache_path = Path(cache_path)
    if not cache_path.is_file():
        return {"success": False, "error": f"本地群成员缓存不存在：{cache_path.name}"}
    try:
        cloud_info, token = _cloud_context(crawler)
        backup_id = _ensure_backup_folder(crawler, cloud_info, token)
        existed = _upload_cache_file(crawler, cloud_info, token, backup_id, cache_path)
        return {"success": True, "already_exists": existed}
    except Exception as exc:
        return {"success": False, "error": str(exc) or "同步群成员缓存失败"}


def _download_cache_file(crawler, cloud_info: dict, token: str, backup_id, file_item: dict, cache_path: Path) -> list[dict]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_path.parent) as temp_dir:
        result = crawler.download_file(
            file_id=file_item.get("id"),
            encrypted_id=file_item.get("encryptedId") or file_item.get("encryptedid"),
            puid=cloud_info["currentPuid"],
            current_folder_id=backup_id,
            token=token,
            save_path=temp_dir,
        )
        if not isinstance(result, dict) or not result.get("success"):
            error = result.get("error", "下载群成员缓存失败") if isinstance(result, dict) else "下载群成员缓存失败"
            raise RuntimeError(error)

        downloaded_path = Path(str(result.get("file_path") or ""))
        if not downloaded_path.is_file():
            raise RuntimeError("云盘下载成功，但未找到缓存文件")
        try:
            with downloaded_path.open("r", encoding="utf-8") as cache_file:
                payload = json.load(cache_file)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeError("云端群成员缓存格式无效") from exc

        members = _normalize_members(payload)
        if not members:
            raise RuntimeError("云端群成员缓存为空或格式无效")
        saved_path = save_group_members_cache(
            members,
            cache_path.stem,
            cache_dir=cache_path.parent,
        )
        if saved_path is None:
            raise RuntimeError("无法将云端群成员缓存写入本地")
        return members

logger = get_logger()


def _log_group_match_failure(sessions, course_name, class_name, course_id, class_id, reason):
    rows = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        if not (session.get("isGroup") == 1 or session.get("isPrivate") is False):
            continue
        info = session.get("class_info") if isinstance(session.get("class_info"), dict) else {}
        rows.append({
            "courseName": session.get("courseName"),
            "subtitle": session.get("subtitle"),
            "courseId": session.get("courseId") or info.get("courseid"),
            "classId": session.get("classId") or info.get("classid"),
            "roomId": session.get("roomId") or session.get("chatId"),
        })
    logger.error(
        "群成员缓存: %s target course=%r class=%r courseId=%r classId=%r; 群会话(%d)=%s",
        reason, course_name, class_name, course_id, class_id, len(rows), rows,
    )


def _find_group_room_id(crawler, course_name: str, class_name: str, course_id="", class_id="") -> str:
    sessions = crawler.get_message_list()
    if not isinstance(sessions, list):
        raise RuntimeError("无法读取消息会话列表，请先登录并重试")

    course_name = str(course_name or "").strip()
    class_name = str(class_name or "").strip()
    course_id = str(course_id or "").strip()
    class_id = str(class_id or "").strip()
    id_matches = []
    matches = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        is_group = session.get("isGroup") == 1 or session.get("isPrivate") is False
        if not is_group:
            continue
        if course_id and class_id:
            info = session.get("class_info") if isinstance(session.get("class_info"), dict) else {}
            s_course = str(session.get("courseId") or info.get("courseid") or "").strip()
            s_class = str(session.get("classId") or info.get("classid") or "").strip()
            if s_course == course_id and s_class == class_id:
                rid = str(session.get("roomId") or session.get("chatId") or "").strip()
                if rid:
                    id_matches.append(rid)
                continue
        session_course = str(session.get("courseName") or "").strip()
        session_class = str(
            session.get("subtitle")
            or session.get("className")
            or session.get("classname")
            or session.get("class_name")
            or ""
        ).strip()
        if session_course != course_name or session_class != class_name:
            continue
        room_id = str(
            session.get("roomId")
            or session.get("chatId")
            or session.get("groupId")
            or session.get("id")
            or ""
        ).strip()
        if room_id:
            matches.append(room_id)

    id_matches = list(dict.fromkeys(id_matches))
    if len(id_matches) == 1:
        return id_matches[0]
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        _log_group_match_failure(
            sessions, course_name, class_name, course_id, class_id,
            "匹配到多个课程群" if matches else "未找到课程群",
        )
        if matches:
            raise RuntimeError("匹配到多个课程群，请先在“消息”模块确认对应群")
        raise RuntimeError("未找到对应课程群，请先在“消息”模块打开该课程群")
    return matches[0]


def prepare_group_members_cache(crawler, course_name: str, class_name: str, progress_callback=None, course_id="", class_id="") -> dict:
    """Resolve local cache, restore cloud backup, or fetch and back up members."""
    def report(text: str):
        if progress_callback:
            progress_callback(text)

    cache_path = build_group_members_cache_path(
        course_name,
        class_name,
        cache_dir=GROUP_MEMBERS_CACHE_DIR,
    )
    report("正在检查本机缓存...")
    members, local_path = load_group_members_cache(
        course_name,
        class_name,
        cache_dir=GROUP_MEMBERS_CACHE_DIR,
    )
    if local_path is not None and members:
        return {"success": True, "members": members, "source": "local"}

    try:
        report("正在检查云盘 backup 目录...")
        cloud_info, token = _cloud_context(crawler)
        backup_id = _ensure_backup_folder(crawler, cloud_info, token)
        backup_items = _list_items(crawler, cloud_info, token, backup_id)
        cloud_file = _named_item(backup_items, cache_path.name, want_file=True)
        if cloud_file:
            report("正在下载云端群成员缓存...")
            members = _download_cache_file(
                crawler, cloud_info, token, backup_id, cloud_file, cache_path
            )
            return {"success": True, "members": members, "source": "cloud"}

        report("云端无缓存，正在查找课程群...")
        room_id = _find_group_room_id(
            crawler, course_name, class_name, course_id, class_id
        )
        report("正在获取群成员（首次较慢，请稍候）...")
        members = crawler.get_group_members(room_id)
        members = _normalize_members(members)
        if not members:
            raise RuntimeError("获取课程群成员失败或成员列表为空")

        saved_path = save_group_members_cache(
            members,
            cache_path.stem,
            fallback=room_id,
            cache_dir=cache_path.parent,
        )
        if saved_path is None:
            raise RuntimeError("群成员已获取，但无法保存本地缓存")

        report("正在上传缓存到云盘 backup...")
        try:
            already_exists = _upload_cache_file(
                crawler, cloud_info, token, backup_id, saved_path
            )
        except Exception as exc:
            return {
                "success": True,
                "members": members,
                "source": "fetched",
                "warning": f"群成员已缓存到本地，但上传到云盘 backup 失败：{exc}",
            }
        return {
            "success": True,
            "members": members,
            "source": "fetched",
            "warning": "云盘中已有同名缓存，已保留云端文件" if already_exists else "",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc) or "准备群成员缓存失败"}

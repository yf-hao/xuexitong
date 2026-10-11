from dataclasses import dataclass
import hashlib
from html import unescape
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from core.config import DATA_DIR


EXAM_REVIEW_LIST_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markresult-new"
)
EXAM_RECEIVE_IP_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/answers-receiveip"
)
EXAM_MARK_PAPER_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markpaper"
)
EXAM_ATTACHMENT_STATUS_URL = (
    "https://mooc2-gray.chaoxing.com/ananas/status"
)
EXAM_ATTACHMENT_IFRAME_URL = (
    "https://mooc2-gray.chaoxing.com/ananas/common-modules/attachment/insertCloud.html"
)


def _attachment_response_message(response):
    try:
        payload = response.json()
    except (AttributeError, ValueError):
        payload = None

    message = ""
    if isinstance(payload, dict):
        for key in ("msg", "message", "error", "errorMsg"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                message = value
                break

    if not message:
        body = getattr(response, "text", "")
        if isinstance(body, str):
            body = re.sub(
                r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", body
            )
            message = unescape(re.sub(r"<[^>]+>", " ", body))

    message = re.sub(r"\s+", " ", message).strip()
    message = re.sub(
        r"(?i)([?&](?:token|enc|sign|secret|auth|ticket|access_token|key)=)"
        r"[^&#\s\"'<>]+",
        r"\1[已隐藏]",
        message,
    )
    return message[:240]


def _attachment_status_forbidden_error(response):
    response_url = str(getattr(response, "url", "") or "")
    response_host = (urlsplit(response_url).hostname or "").lower()
    message = _attachment_response_message(response)
    if "passport2.chaoxing.com" in response_host:
        return RuntimeError("附件状态请求跳转到了登录服务，请重新登录后重试")
    if message and re.search(r"未登录|请先登录|登录已失效|login required", message, re.I):
        return RuntimeError(f"学习通登录状态可能已失效：{message}")
    if message and re.search(r"无权|权限不足|不允许下载|禁止下载", message):
        return RuntimeError(f"当前账号可能没有该附件的下载权限：{message}")
    if message:
        return RuntimeError(f"附件状态接口返回 HTTP 403，服务器提示：{message}")
    return RuntimeError(
        "附件状态接口返回 HTTP 403。登录会话可能已失效，也可能是当前账号无权下载该附件；"
        "请重新登录后重试。"
    )


def exam_attachment_cache_path(object_id: str, filename: str) -> str:
    if not object_id or not filename:
        raise ValueError("附件 ID 或文件名缺失")
    safe_filename = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(safe_filename).suffix.lower()
    if len(suffix) > 16:
        suffix = ""
    cache_dir = Path(DATA_DIR) / "exam_attachment_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(str(object_id).encode("utf-8")).hexdigest()
    return str(cache_dir / f"{cache_key}{suffix}")


@dataclass(frozen=True)
class ExamReviewContext:
    course_id: str
    class_id: str
    cpi: str
    exam_id: str
    exam_title: str
    class_name: str
    marklist_url: str = ""


@dataclass(frozen=True)
class ExamReviewPage:
    records: list
    total: int
    class_size: int
    page_num: int
    page_size: int
    total_pages: int


def fetch_exam_review_page(
    session,
    context: ExamReviewContext,
    state: int,
    page_num: int = 1,
    page_size: int = 20,
) -> ExamReviewPage:
    if state not in (0, 1):
        raise ValueError("state must be 0 (unsubmitted) or 1 (submitted)")
    if not context.course_id or not context.class_id or not context.cpi or not context.exam_id:
        raise ValueError("课程、班级或考试参数缺失")
    if page_num < 1 or page_size < 1:
        raise ValueError("页码和每页数量必须为正数")

    form_data = {
        "courseid": context.course_id,
        "clazzid": context.class_id,
        "cpi": context.cpi,
        "ut": "",
        "id": context.exam_id,
        "sw": "",
        "schoolId": "-1",
        "schoolName": "",
        "sort": "",
        "sorttype": "",
        "state": str(state),
        "status": "-1",
        "groupIds": "",
        "groupid": "-1",
        "collegeId": "-1",
        "majorId": "-1",
        "clazzId": "-1",
        "reviewMarkLabel": "0",
        "markType": "0",
        "hideInvigilation": "0",
        "hideRetest": "false",
        "updateScore": "1",
        "allowAnnotationRedoDownload": "1",
    }
    if page_num > 1:
        form_data.update({
            "pages": str(page_num),
            "size": str(page_size),
            "groupId": "-1",
            "mark": "-1",
        })
    elif page_size != 20:
        form_data["size"] = str(page_size)

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": (
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5"
        ),
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://mooc2-gray.chaoxing.com",
        "Pragma": "no-cache",
        "Referer": context.marklist_url,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": (
            '"Chromium";v="154", "Google Chrome";v="154", '
            '"Not A(Brand";v="99"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }
    response = session.post(
        EXAM_REVIEW_LIST_URL,
        data=form_data,
        headers=headers,
        timeout=20,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "批阅接口返回 HTTP 403：服务器拒绝请求，请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        message = payload.get("msg") if isinstance(payload, dict) else "响应格式错误"
        raise RuntimeError(message or "考试批阅列表加载失败")

    records = payload.get("data")
    if not isinstance(records, list):
        raise RuntimeError("考试批阅列表响应缺少 data 数组")

    if state == 1:
        record_ids = [
            str(record["id"])
            for record in records
            if isinstance(record, dict) and record.get("id") is not None
        ]
        if record_ids:
            ip_response = session.post(
                EXAM_RECEIVE_IP_URL,
                data={
                    "courseId": context.course_id,
                    "classId": context.class_id,
                    "cpi": context.cpi,
                    "ids": ",".join(record_ids),
                },
                headers=headers,
                timeout=20,
            )
            if ip_response.status_code == 403:
                raise RuntimeError(
                    "提交 IP 接口返回 HTTP 403：请确认登录状态和考试批阅权限"
                )
            ip_response.raise_for_status()
            ip_payload = ip_response.json()
            if (
                not isinstance(ip_payload, dict)
                or str(ip_payload.get("status")).lower() not in ("true", "1")
                or not isinstance(ip_payload.get("receiveIps"), list)
            ):
                raise RuntimeError("提交 IP 信息加载失败")

            receive_ips = {
                str(item["id"]): item.get("receiveIp", "")
                for item in ip_payload["receiveIps"]
                if isinstance(item, dict) and item.get("id") is not None
            }
            for record in records:
                if isinstance(record, dict):
                    record["receiveIp"] = receive_ips.get(
                        str(record.get("id")), record.get("receiveIp", "")
                    )

    return ExamReviewPage(
        records=records,
        total=int(payload.get("total") or 0),
        class_size=int(payload.get("classSize") or 0),
        page_num=int(payload.get("pageNum") or page_num),
        page_size=int(payload.get("size") or page_size),
        total_pages=int(payload.get("totalPage") or 0),
    )


def fetch_all_submitted_exam_records(
    session,
    context: ExamReviewContext,
    page_size: int = 100,
    progress_callback=None,
) -> list:
    first_page = fetch_exam_review_page(
        session, context, state=1, page_num=1, page_size=page_size
    )
    records = list(first_page.records)
    total_pages = max(1, first_page.total_pages)
    if progress_callback is not None:
        progress_callback(1, total_pages)

    for page_num in range(2, total_pages + 1):
        page = fetch_exam_review_page(
            session,
            context,
            state=1,
            page_num=page_num,
            page_size=page_size,
        )
        records.extend(page.records)
        if progress_callback is not None:
            progress_callback(page_num, total_pages)
    return records


def fetch_exam_mark_paper(session, context: ExamReviewContext, record_id: str):
    if not context.course_id or not context.class_id or not context.cpi:
        raise ValueError("课程、班级或考试参数缺失")
    if record_id in (None, ""):
        raise ValueError("答卷记录 ID 缺失")

    params = {
        "courseid": context.course_id,
        "id": str(record_id),
        "classid": context.class_id,
        "groupid": "-1",
        "ut": "t",
        "cpi": context.cpi,
        "hideRetest": "false",
        "groupIds": "",
        "sw": "",
        "sorttype": "",
        "updateScore": "1",
        "allowAnnotationRedoDownload": "1",
        "sort": "",
        "from": "list",
    }
    response = session.get(
        EXAM_MARK_PAPER_URL,
        params=params,
        headers={
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": context.marklist_url,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            "Upgrade-Insecure-Requests": "1",
        },
        timeout=20,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "批阅页面请求返回 HTTP 403：请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()
    response_url = str(getattr(response, "url", "") or "").lower()
    if "passport2.chaoxing.com" in response_url:
        raise RuntimeError("登录状态已失效，请重新登录")
    return response.text


def download_exam_attachment(session, object_id: str, save_path: str) -> str:
    if not object_id:
        raise ValueError("附件 ID 缺失")
    if not save_path:
        raise ValueError("附件保存路径缺失")

    status_response = session.get(
        f"{EXAM_ATTACHMENT_STATUS_URL}/{quote(str(object_id), safe='')}",
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": EXAM_ATTACHMENT_IFRAME_URL,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=20,
    )
    try:
        if status_response.status_code == 403:
            raise _attachment_status_forbidden_error(status_response)
        status_response.raise_for_status()
        status_url = str(getattr(status_response, "url", "") or "").lower()
        if "passport2.chaoxing.com" in status_url:
            raise RuntimeError("登录状态已失效，请重新登录")
        try:
            payload = status_response.json()
        except ValueError as exc:
            raise RuntimeError("附件状态接口返回了无效响应") from exc
    finally:
        status_response.close()

    download_url = payload.get("download") if isinstance(payload, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        message = _attachment_response_message(status_response)
        if message:
            raise RuntimeError(f"附件状态接口未返回下载地址：{message}")
        raise RuntimeError("附件状态接口没有返回下载地址")
    download_url = urljoin(EXAM_ATTACHMENT_STATUS_URL, download_url.strip())
    parsed_url = urlsplit(download_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise RuntimeError("附件下载地址无效")
    if parsed_url.scheme == "http":
        download_url = urlunsplit(parsed_url._replace(scheme="https"))

    destination = Path(save_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    download_response = None
    try:
        download_response = session.get(
            download_url,
            headers={"Referer": EXAM_ATTACHMENT_IFRAME_URL},
            stream=True,
            timeout=(20, 120),
        )
        if download_response.status_code == 403:
            raise RuntimeError("附件下载返回 HTTP 403，请确认登录状态和下载权限")
        download_response.raise_for_status()
        response_url = str(getattr(download_response, "url", "") or "").lower()
        if "passport2.chaoxing.com" in response_url:
            raise RuntimeError("登录状态已失效，请重新登录")

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(destination.parent),
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as output:
            temporary_path = output.name
            for chunk in download_response.iter_content(chunk_size=65536):
                if chunk:
                    output.write(chunk)
        os.replace(temporary_path, destination)
        temporary_path = None
        return str(destination)
    finally:
        if download_response is not None:
            download_response.close()
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)
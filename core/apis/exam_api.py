from dataclasses import dataclass
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html import unescape
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import (
    parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit,
)

from bs4 import BeautifulSoup

from core.config import DATA_DIR


EXAM_REVIEW_LIST_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markresult-new"
)
EXAM_SUBQUESTIONS_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/subquestions"
)
EXAM_RECEIVE_IP_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/answers-receiveip"
)
EXAM_MARK_PAPER_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/markpaper"
)
EXAM_SUBMIT_MARK_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/submitmark"
)
EXAM_SUBMIT_QUESTION_MARK_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/submit-markquestion"
)
EXAM_SKIP_QUESTION_MARK_URL = (
    "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test/skipmarkquestion"
)
EXAM_ATTACHMENT_STATUS_URL = (
    "https://mooc2-gray.chaoxing.com/ananas/status"
)
EXAM_ATTACHMENT_IFRAME_URL = (
    "https://mooc2-gray.chaoxing.com/ananas/common-modules/attachment/insertCloud.html"
)
_MAX_EXAM_ANSWER_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_EXAM_ANSWER_IMAGES_PER_PAGE = 30
_EXAM_ANSWER_IMAGE_WORKERS = 6
_MAX_EXAM_ANSWER_IMAGES_PAGE_BYTES = 32 * 1024 * 1024


def _is_trusted_chaoxing_url(url):
    parsed = urlsplit(str(url or ""))
    host = (parsed.hostname or "").lower()
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and valid_port
        and parsed.username is None
        and parsed.password is None
        and (host == "chaoxing.com" or host.endswith(".chaoxing.com"))
    )


def _raster_image_mime_type(content):
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return ""


def _fetch_trusted_answer_image(session, image_url, request_headers):
    current_url = image_url
    redirect_statuses = {301, 302, 303, 307, 308}
    for redirect_count in range(4):
        response = session.get(
            current_url,
            headers=request_headers,
            timeout=(5, 20),
            allow_redirects=False,
        )
        status_code = getattr(response, "status_code", 0)
        if status_code in redirect_statuses:
            if redirect_count == 3:
                return b""
            location = getattr(response, "headers", {}).get("Location", "")
            redirect_url = urljoin(current_url, str(location))
            if not location or not _is_trusted_chaoxing_url(redirect_url):
                return b""
            current_url = redirect_url
            continue
        if status_code != 200:
            return b""
        response_url = getattr(response, "url", "") or current_url
        if not _is_trusted_chaoxing_url(response_url):
            return b""
        content = getattr(response, "content", b"")
        return content if isinstance(content, bytes) else b""
    return b""


def _embed_exam_answer_images(session, html, referer):
    soup = BeautifulSoup(html or "", "lxml")
    image_nodes = soup.select("img.ans-ued-img")
    if not image_nodes:
        return html

    page_bytes = 0
    origin = urlsplit(EXAM_MARK_PAPER_URL)
    image_referer = f"{origin.scheme}://{origin.netloc}/"
    request_headers = {
        "Accept": (
            "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        ),
        "Accept-Language": (
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5"
        ),
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Referer": image_referer,
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": (
            '"Chromium";v="154", "Google Chrome";v="154", '
            '"Not A(Brand";v="99"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }
    targets = []
    for image_node in image_nodes[:_MAX_EXAM_ANSWER_IMAGES_PER_PAGE]:
        image_url = urljoin(referer, str(image_node.get("src") or ""))
        if _is_trusted_chaoxing_url(image_url):
            targets.append((image_node, image_url))

    def fetch(image_url):
        try:
            return _fetch_trusted_answer_image(
                session, image_url, request_headers
            )
        except Exception:
            return b""

    if len(targets) > 1:
        with ThreadPoolExecutor(
            max_workers=min(_EXAM_ANSWER_IMAGE_WORKERS, len(targets))
        ) as executor:
            fetched = list(executor.map(fetch, [url for _, url in targets]))
    else:
        fetched = [fetch(url) for _, url in targets]

    for (image_node, _), image_bytes in zip(targets, fetched):
        if (
            not isinstance(image_bytes, bytes)
            or not image_bytes
            or len(image_bytes) > _MAX_EXAM_ANSWER_IMAGE_BYTES
            or page_bytes + len(image_bytes)
            > _MAX_EXAM_ANSWER_IMAGES_PAGE_BYTES
        ):
            continue
        mime_type = _raster_image_mime_type(image_bytes)
        if not mime_type:
            continue
        encoded = base64.b64encode(image_bytes).decode("ascii")
        image_node["src"] = f"data:{mime_type};base64,{encoded}"
        page_bytes += len(image_bytes)
    return str(soup)


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


def fetch_exam_review_questions(session, context: ExamReviewContext):
    if not context.course_id or not context.class_id or not context.cpi or not context.exam_id:
        raise ValueError("课程、班级或考试参数缺失")

    response = session.post(
        EXAM_SUBQUESTIONS_URL,
        data={
            "courseid": context.course_id,
            "clazzid": context.class_id,
            "cpi": context.cpi,
            "ut": "",
            "id": context.exam_id,
            "start": "0",
            "markType": "0",
            "groupIds": "",
        },
        headers={
            "Accept": "*/*",
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
        },
        timeout=20,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "按题批阅接口返回 HTTP 403：请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()
    response_url = str(getattr(response, "url", "") or "").lower()
    if "passport2.chaoxing.com" in response_url:
        raise RuntimeError("登录状态已失效，请重新登录")

    soup = BeautifulSoup(response.text, "html.parser")
    questions = []
    for row in soup.select("ul.dataBody_td"):
        cells = row.find_all("li", recursive=False)
        if len(cells) < 5:
            continue

        action = cells[4].select_one("a[onclick]")
        onclick = str(action.get("onclick", "")) if action else ""
        match = re.search(r"toMarkPaper\(\s*(['\"])(.*?)\1\s*\)", onclick)
        mark_url = ""
        question_id = ""
        if match:
            candidate_url = urljoin(EXAM_SUBQUESTIONS_URL, unescape(match.group(2)))
            candidate = urlsplit(candidate_url)
            expected = urlsplit(EXAM_SUBQUESTIONS_URL)
            if (
                candidate.scheme == expected.scheme
                and candidate.netloc == expected.netloc
                and candidate.path == (
                    "/mooc2-ans/exam/test/markquestionnew"
                )
            ):
                mark_url = candidate_url
                question_id = dict(parse_qsl(urlsplit(mark_url).query)).get(
                    "qid", ""
                )

        questions.append({
            "question_type": cells[0].get_text(" ", strip=True),
            "number": cells[1].get_text(" ", strip=True),
            "content": cells[2].get_text(" ", strip=True),
            "maximum_score": cells[3].get_text(" ", strip=True),
            "question_id": question_id,
            "mark_url": mark_url,
        })
    return questions


def _validated_exam_question_mark_url(mark_url):
    target_url = urljoin(EXAM_SUBQUESTIONS_URL, str(mark_url or ""))
    target = urlsplit(target_url)
    expected = urlsplit(EXAM_SUBQUESTIONS_URL)
    if (
        target.scheme != expected.scheme
        or target.netloc != expected.netloc
        or target.path != "/mooc2-ans/exam/test/markquestionnew"
    ):
        raise ValueError("题目批阅链接不是受信任的学习通页面")
    return target_url, target


def next_exam_question_mark_url(mark_url):
    _target_url, target = _validated_exam_question_mark_url(mark_url)
    query = [
        (key, value)
        for key, value in parse_qsl(target.query, keep_blank_values=True)
        if key.lower() not in {"answerid", "groupids", "num"}
    ]
    existing_keys = {key.lower() for key, _value in query}
    for name in ("ht", "ha", "wn"):
        if name not in existing_keys:
            query.append((name, "0"))
    query.append(("num", "1"))
    return urlunsplit((
        target.scheme, target.netloc, target.path, urlencode(query), ""
    ))


def exam_question_mark_referer(mark_url, answer_id):
    _target_url, target = _validated_exam_question_mark_url(mark_url)
    query = [
        (key, value)
        for key, value in parse_qsl(target.query, keep_blank_values=True)
        if key.lower() not in {"answerid", "groupids"}
    ]
    existing_keys = {key.lower() for key, _value in query}
    for name in ("ht", "ha", "wn"):
        if name not in existing_keys:
            query.append((name, "0"))
    query.append(("answerId", str(answer_id)))
    return urlunsplit((
        target.scheme, target.netloc, target.path, urlencode(query), ""
    ))


def skip_exam_question_answer(
    session, context, mark_url, answer_id, referer=""
):
    if session is None:
        raise ValueError("当前没有可用的学习通登录会话")
    if not answer_id:
        raise ValueError("当前答卷缺少 answerid，无法跳过")
    target_url, target = _validated_exam_question_mark_url(mark_url)
    query = dict(parse_qsl(target.query, keep_blank_values=True))
    question_id = str(query.get("qid") or "")
    if not question_id:
        raise ValueError("题目批阅链接缺少 qid，无法跳过")
    if not all((context.course_id, context.class_id, context.cpi, context.exam_id)):
        raise ValueError("课程、班级或考试参数缺失，无法跳过")

    response = session.post(
        EXAM_SKIP_QUESTION_MARK_URL,
        data={
            "courseid": context.course_id,
            "clazzid": context.class_id,
            "cpi": context.cpi,
            "id": context.exam_id,
            "qid": question_id,
            "ut": query.get("ut", ""),
            "answerid": str(answer_id),
        },
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": (
                "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5"
            ),
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Pragma": "no-cache",
            "Referer": referer or exam_question_mark_referer(
                mark_url, answer_id
            ),
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
        },
        timeout=20,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "跳过答卷接口返回 HTTP 403：请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()
    response_url = str(getattr(response, "url", "") or "").lower()
    if "passport2.chaoxing.com" in response_url:
        raise RuntimeError("登录状态已失效，请重新登录")
    try:
        result = response.json()
    except (AttributeError, ValueError) as exc:
        raise RuntimeError("跳过答卷接口未返回有效 JSON") from exc
    if not isinstance(result, dict) or result.get("status") != "success":
        message = (
            result.get("message", "跳过答卷失败")
            if isinstance(result, dict) else "跳过答卷失败"
        )
        raise RuntimeError(str(message))
    return result


def fetch_exam_question_mark_paper(
    session, context, mark_url, referer=None
):
    if session is None:
        raise ValueError("当前没有可用的学习通登录会话")
    target_url, _target = _validated_exam_question_mark_url(mark_url)

    response = session.get(
        target_url,
        headers={
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": (
                "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5"
            ),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer or context.marklist_url,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            "sec-ch-ua": (
                '"Chromium";v="154", "Google Chrome";v="154", '
                '"Not A(Brand";v="99"'
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        },
        timeout=20,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "按题批阅页面返回 HTTP 403：请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()
    response_url = str(getattr(response, "url", "") or "").lower()
    if "passport2.chaoxing.com" in response_url:
        raise RuntimeError("登录状态已失效，请重新登录")
    return _embed_exam_answer_images(session, response.text, target_url)


def fetch_exam_review_page(
    session,
    context: ExamReviewContext,
    state: int,
    page_num: int = 1,
    page_size: int = 20,
    include_ips: bool = True,
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

    if state == 1 and include_ips:
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
    include_ips: bool = True,
) -> list:
    first_page = fetch_exam_review_page(
        session,
        context,
        state=1,
        page_num=1,
        page_size=page_size,
        include_ips=include_ips,
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
            include_ips=include_ips,
        )
        records.extend(page.records)
        if progress_callback is not None:
            progress_callback(page_num, total_pages)
    return records


def _exam_mark_paper_params(context: ExamReviewContext, record_id: str):
    if not context.course_id or not context.class_id or not context.cpi:
        raise ValueError("课程、班级或考试参数缺失")
    if record_id in (None, ""):
        raise ValueError("答卷记录 ID 缺失")
    return {
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


def exam_mark_paper_referer(context: ExamReviewContext, record_id: str):
    params = _exam_mark_paper_params(context, record_id)
    return f"{EXAM_MARK_PAPER_URL}?{urlencode(params)}"


def fetch_exam_mark_paper(session, context: ExamReviewContext, record_id: str):
    params = _exam_mark_paper_params(context, record_id)
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
    page_referer = exam_mark_paper_referer(context, record_id)
    return _embed_exam_answer_images(
        session, response.text, page_referer
    )


def submit_exam_mark(session, action, query_params, form_fields, referer=""):
    if session is None:
        raise ValueError("当前没有可用的学习通登录会话")
    if not action:
        raise ValueError("批阅表单提交地址缺失")

    target_url = urljoin(EXAM_MARK_PAPER_URL, str(action))
    target = urlsplit(target_url)
    expected = urlsplit(EXAM_SUBMIT_MARK_URL)
    allowed_submit_paths = {
        urlsplit(EXAM_SUBMIT_MARK_URL).path,
        urlsplit(EXAM_SUBMIT_QUESTION_MARK_URL).path,
    }
    if (
        target.scheme != expected.scheme
        or target.netloc != expected.netloc
        or target.path not in allowed_submit_paths
    ):
        raise ValueError("批阅表单提交地址不是受信任的学习通接口")
    merged_query_params = dict(
        parse_qsl(target.query, keep_blank_values=True)
    )
    merged_query_params.update(dict(query_params))
    submit_url = urlunsplit((target.scheme, target.netloc, target.path, "", ""))
    question_submit = (
        target.path == urlsplit(EXAM_SUBMIT_QUESTION_MARK_URL).path
    )

    headers = {
        "Accept": (
            "*/*" if question_submit
            else "application/json, text/javascript, */*; q=0.01"
        ),
        "Accept-Language": (
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5"
        ),
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://mooc2-gray.chaoxing.com",
        "Pragma": "no-cache",
        "Referer": referer or EXAM_MARK_PAPER_URL,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    response = session.post(
        submit_url,
        params=list(merged_query_params.items()),
        data=list(form_fields),
        headers=headers,
        timeout=30,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "提交批阅返回 HTTP 403：请确认登录状态和考试批阅权限"
        )
    response.raise_for_status()
    response_url = str(getattr(response, "url", "") or "").lower()
    if "passport2.chaoxing.com" in response_url:
        raise RuntimeError("登录状态已失效，请重新登录")
    response_text = str(getattr(response, "text", "") or "").strip()
    if question_submit and response_text.lower() == "saveok":
        return {"status": "success", "msg": "批阅成功"}
    try:
        payload = response.json()
    except (AttributeError, ValueError) as exc:
        raise RuntimeError("提交批阅接口返回了无法识别的响应") from exc
    if question_submit and isinstance(payload, str) and payload.lower() == "saveok":
        return {"status": "success", "msg": "批阅成功"}
    if (
        not isinstance(payload, dict)
        or str(payload.get("status", "")).lower() != "success"
    ):
        message = payload.get("msg") if isinstance(payload, dict) else ""
        raise RuntimeError(message or "学习通未确认批阅提交成功")
    return payload


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
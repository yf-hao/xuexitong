from copy import deepcopy
import base64
from dataclasses import dataclass
import json
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from bs4 import Tag
from core.utils.image_utils import validated_image_data_uri


@dataclass(frozen=True)
class ExamAnswerAttachment:
    object_id: str
    filename: str
    file_type: str = ""
    file_size: str = ""


@dataclass(frozen=True)
class ExamQuestionContent:
    number: str
    question_type: str
    score: float | None
    earned_score: float | None
    score_confirmed: bool
    question_id: str
    stem_html: str
    student_answer_html: str
    correct_answer_html: str
    explanation_html: str
    attachments: tuple[ExamAnswerAttachment, ...] = ()

    @property
    def grading_status(self):
        if not self.score_confirmed or self.earned_score is None:
            return "pending"
        if self.question_type not in {"单选题", "多选题", "判断题"}:
            return "graded"
        if self.score is None or self.score <= 0:
            return "graded"
        if self.earned_score >= self.score - 1e-6:
            return "correct"
        if self.earned_score <= 1e-6:
            return "incorrect"
        return "partial"


@dataclass(frozen=True)
class ExamQuestionGroup:
    title: str
    question_type: str
    questions: tuple[ExamQuestionContent, ...]
    total_score: float | None


@dataclass(frozen=True)
class ExamMarkPaperSubmission:
    action: str
    fields: tuple[tuple[str, str], ...]
    query_params: tuple[tuple[str, str], ...]
    referer: str = ""


@dataclass(frozen=True)
class ExamMarkPaperContent:
    groups: tuple[ExamQuestionGroup, ...]
    submission: ExamMarkPaperSubmission | None = None

    @property
    def questions(self):
        return tuple(
            question
            for group in self.groups
            for question in group.questions
        )


@dataclass(frozen=True)
class ExamQuestionMarkPaper:
    content: ExamMarkPaperContent
    student_name: str
    student_id: str
    answer_id: str
    pending_count: int | None = None
    submitted_count: int | None = None


_REMOVED_TAGS = {
    "button", "embed", "form", "iframe", "input", "object", "script",
    "select", "style", "textarea",
}
_MEDIA_TAGS = {"audio", "svg", "video"}
_ALLOWED_TAGS = {
    "b", "blockquote", "br", "caption", "code", "dd", "del", "div",
    "dl", "dt", "em", "h1", "h2", "h3", "h4", "hr", "i", "img", "li",
    "ol", "p", "pre", "s", "span", "strike", "strong", "sub", "sup",
    "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}
_ALLOWED_ATTRIBUTES = {"colspan", "rowspan", "scope"}


def _safe_fragment(node):
    if node is None:
        return ""
    if isinstance(node, Tag):
        fragment = deepcopy(node)
    else:
        return ""

    for child in list(fragment.find_all(True)):
        if child.name in _REMOVED_TAGS:
            child.decompose()
        elif child.name == "img":
            image_src = validated_image_data_uri(child.get("src", ""))
            if image_src is None:
                child.replace_with("[附件或媒体内容]")
                continue
            image_attributes = {"src": image_src}
            for dimension in ("width", "height"):
                value = str(child.get(dimension, ""))
                if value.isdecimal() and 0 < int(value) <= 4096:
                    image_attributes[dimension] = value
            alt_text = str(child.get("alt", ""))[:256]
            if alt_text:
                image_attributes["alt"] = alt_text
            child.attrs = image_attributes
        elif child.name in _MEDIA_TAGS:
            child.replace_with("[附件或媒体内容]")
        elif child.name == "a":
            child.unwrap()
        elif child.name not in _ALLOWED_TAGS:
            child.unwrap()
        else:
            child.attrs = {
                key: value
                for key, value in child.attrs.items()
                if key in _ALLOWED_ATTRIBUTES
            }

    fragment.attrs = {}
    return "".join(str(child) for child in fragment.contents).strip()


def _question_score(question_node):
    score_node = question_node.select_one("input[id^='fullScore']")
    if score_node is None:
        score_node = question_node.select_one(
            "input[name^='score'][data-score]"
        )
        value = score_node.get("data-score") if score_node else None
    else:
        value = score_node.get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _earned_score(question_node):
    score_node = question_node.select_one("input[name^='score']")
    if score_node is None:
        return None, False
    try:
        earned_score = float(score_node.get("value"))
    except (TypeError, ValueError):
        earned_score = None
    return earned_score, score_node.has_attr("readonly")


def _stem_fragment(stem_node, choices_node=None, question_number=None):
    if stem_node is None:
        return ""
    stem_body = deepcopy(stem_node)
    for prefix in stem_body.find_all(
        "span", class_="colorShallow", recursive=False
    ):
        prefix.decompose()
    for wrapper in stem_body.find_all(
        "div", class_="hiddenTitle", recursive=False
    ):
        wrapper.unwrap()
    stem_html = _safe_fragment(stem_body)
    if question_number:
        stem_html = re.sub(
            rf"^\s*{re.escape(str(question_number))}\s*[.．、]\s*",
            "",
            stem_html,
            count=1,
        )
    if choices_node is not None:
        choices_body = deepcopy(choices_node)
        for choice in choices_body.find_all("li", recursive=False):
            choice.name = "div"
        stem_html += (
            '<div class="choices">'
            f'{_safe_fragment(choices_body)}'
            '</div>'
        )
    return stem_html


def _student_answer_fragment(answer_node):
    if answer_node is None:
        return ""

    mark_key = answer_node.select_one(".mark_key")
    if mark_key is None:
        return _safe_fragment(answer_node)

    answer_body = deepcopy(mark_key)
    for icon in answer_body.select(".studenticon"):
        icon.decompose()
    for text_node in list(answer_body.find_all(string=True)):
        cleaned_text = re.sub(
            r"^\s*学生答案\s*[:：]\s*", "", str(text_node), count=1
        )
        if cleaned_text != str(text_node):
            text_node.replace_with(cleaned_text)
    return _safe_fragment(answer_body)


def _student_answer_attachments(answer_node):
    if answer_node is None:
        return ()

    attachments = []
    for iframe in answer_node.select("iframe.attach-iframe"):
        metadata = {}
        encoded_metadata = iframe.get("name")
        if encoded_metadata:
            try:
                encoded_json = base64.b64decode(
                    encoded_metadata, validate=True
                ).decode("utf-8")
                metadata = json.loads(unquote(encoded_json))
            except (
                binascii.Error, UnicodeDecodeError, ValueError, TypeError,
            ):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}

        object_id = iframe.get("objectid") or metadata.get("objectid")
        filename = iframe.get("filename") or metadata.get("name")
        if not object_id or not filename:
            continue
        attachments.append(ExamAnswerAttachment(
            object_id=str(object_id),
            filename=str(filename),
            file_type=str(
                iframe.get("filetype") or metadata.get("type") or ""
            ),
            file_size=str(
                iframe.get("filesize") or metadata.get("size") or ""
            ),
        ))
    return tuple(attachments)


def _correct_answer_fragment(question_node):
    right_answer = question_node.select_one(".topicRightAnswer")
    if right_answer is None:
        return ""

    mark_key = right_answer.select_one(".mark_key")
    if mark_key is not None:
        answer_body = deepcopy(mark_key)
        for icon in answer_body.select(".studenticon"):
            icon.decompose()
        for label in answer_body.select(".fontWeight"):
            if label.get_text(" ", strip=True).rstrip("：:") in {
                "正确答案", "标准答案", "答案",
            }:
                label.decompose()
        for text_node in list(answer_body.find_all(string=True)):
            cleaned_text = re.sub(
                r"^\s*(?:正确答案|标准答案|答案)\s*[:：]?\s*",
                "",
                str(text_node),
                count=1,
            )
            if cleaned_text != str(text_node):
                text_node.replace_with(cleaned_text)
        return _safe_fragment(answer_body)

    answer_node = right_answer.select_one(".objAnswer_right")
    if answer_node is None:
        return ""
    answer_content = answer_node.select_one(".disablePosition") or answer_node
    return _safe_fragment(answer_content)


def _explanation_fragment(question_node):
    right_answer = question_node.select_one(".topicRightAnswer")
    analysis = (
        right_answer.select_one(".answerAnalysis")
        if right_answer is not None
        else question_node.select_one(".answerAnalysis")
    )
    if analysis is None:
        return ""
    explanation = analysis.select_one(
        ".AnalysisCon, .objAnswer_analysis"
    )
    if explanation is not None:
        return _safe_fragment(explanation)

    analysis_body = deepcopy(analysis)
    for label in analysis_body.select(".analysisTit"):
        label.decompose()
    return _safe_fragment(analysis_body)


def _chinese_number(number):
    numerals = "零一二三四五六七八九"
    if number <= 0:
        return str(number)
    if number < 10:
        return numerals[number]
    if number == 10:
        return "十"
    if number < 20:
        return f"十{numerals[number % 10]}"
    if number < 100:
        tens, ones = divmod(number, 10)
        return f"{numerals[tens]}十{numerals[ones] if ones else ''}"
    return str(number)


def _uniform_question_score(questions):
    if not questions or any(question.score is None for question in questions):
        return None
    score = questions[0].score
    if all(abs(question.score - score) <= 1e-6 for question in questions):
        return score
    return None


def _submission_template(soup, referer=""):
    form = soup.select_one("form#submitMarking")
    if form is None:
        form = soup.find(
            "form",
            action=re.compile(
                r"/exam/test/submit(?:-)?mark(?:question)?(?:\?|$)"
            ),
        )
    if form is None:
        return None

    fields = []
    for control in form.select("input[name], textarea[name], select[name]"):
        name = str(control.get("name") or "")
        if control.name == "input":
            control_type = str(control.get("type") or "text").lower()
            if control_type in {"button", "reset", "submit", "image"}:
                continue
            if control_type in {"checkbox", "radio"} and not control.has_attr("checked"):
                continue
            value = str(control.get("value", "on" if control_type in {
                "checkbox", "radio",
            } else ""))
        elif control.name == "textarea":
            value = control.decode_contents(formatter=None)
        else:
            options = control.select("option[selected]")
            if not options:
                options = control.select("option")[:1]
            for option in options:
                fields.append((name, str(option.get("value", option.get_text()))))
            continue
        fields.append((name, value))

    action = str(form.get("action") or "")
    query_params = parse_qsl(urlsplit(action).query, keep_blank_values=True)
    query_values = dict(query_params)
    query_field_names = {
        "classId", "markStyle", "submitType", "sumScore",
        "testUserRelationId",
    }
    for field_name in query_field_names:
        for name, value in fields:
            if name == field_name:
                query_values[name] = value

    page_option_names = (
        "checkHiddenTitle", "checkHiddenAnswer",
        "checkSubjectAnswerWordNum", "checkHiddenObjectQuestion",
        "hideRetest", "sw", "sorttype", "sort", "updateScore",
        "allowAnnotationRedoDownload", "from",
    )
    for name in page_option_names:
        control = soup.find(id=name)
        if control is not None:
            query_values[name] = str(control.get("value", ""))
    query_defaults = (
        ("checkHiddenTitle", "0"),
        ("checkHiddenAnswer", "0"),
        ("checkSubjectAnswerWordNum", "0"),
        ("checkHiddenObjectQuestion", "1"),
        ("hideRetest", "false"),
        ("sw", ""),
        ("sorttype", "0"),
        ("sort", ""),
        ("updateScore", "1"),
        ("allowAnnotationRedoDownload", "1"),
        ("from", "list"),
    )
    for name, default in query_defaults:
        query_values.setdefault(name, default)

    return ExamMarkPaperSubmission(
        action=action,
        fields=tuple(fields),
        query_params=tuple(query_values.items()),
        referer=referer,
    )


def _group_title(group_number, question_type, questions, total_score):
    score_text = f"{total_score:.1f}" if total_score is not None else "未知"
    question_score = _uniform_question_score(questions)
    if question_score is None:
        score_details = f"{score_text}分"
    else:
        score_details = f"每题{question_score:g}分，共{score_text}分"
    return (
        f"{_chinese_number(group_number)}.{question_type}"
        f"（共{len(questions)}题，{score_details}）"
    )


def _add_per_question_score(title, questions):
    question_score = _uniform_question_score(questions)
    if question_score is None or "每题" in title:
        return title
    pattern = re.compile(r"(共\s*\d+\s*题)[，,]\s*([\d.]+)\s*分")
    return pattern.sub(
        lambda match: (
            f"{match.group(1)}，每题{question_score:g}分，"
            f"共{match.group(2)}分"
        ),
        title,
        count=1,
    )


def parse_exam_mark_paper(html, referer=""):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    submission = _submission_template(soup, referer)
    question_nodes = soup.select(".questionWrap")
    if not question_nodes:
        raise ValueError("批阅页面中没有找到题目内容")

    grouped_questions = {}
    group_headers = {}
    for index, question_node in enumerate(question_nodes, 1):
        question_type = str(question_node.get("name") or "题目")
        group_node = question_node.find_parent(class_="ans-cc") or soup
        group_key = (id(group_node), question_type)
        grouped_questions.setdefault(group_key, [])
        if group_key not in group_headers:
            header_node = group_node.select_one(".left-typt-tit")
            header_text = (
                header_node.get_text(" ", strip=True) if header_node else ""
            )
            group_headers[group_key] = (
                header_text if question_type in header_text else ""
            )

        stem_node = question_node.select_one(
            "h3.mark_name[id^='questionStem_']"
        )
        if stem_node is None:
            stem_node = question_node.select_one(".mark_name")
        choices_node = question_node.select_one(
            ".topicArea > ul.mark_letter"
        )
        answer_node = question_node.select_one(
            ".stuAnswerWords .SubjectStuAnswer"
        )
        if answer_node is None:
            answer_node = question_node.select_one(".topicStudentAnswer")
        question_id = ""
        if stem_node is not None:
            question_id = str(stem_node.get("id") or "").removeprefix(
                "questionStem_"
            )
        question_number = str(question_node.get("index") or index)
        earned_score, score_confirmed = _earned_score(question_node)
        answer_attachments = _student_answer_attachments(answer_node)

        grouped_questions[group_key].append(ExamQuestionContent(
            number=question_number,
            question_type=question_type,
            score=_question_score(question_node),
            earned_score=earned_score,
            score_confirmed=score_confirmed,
            question_id=question_id,
            stem_html=_stem_fragment(
                stem_node, choices_node, question_number
            ),
            student_answer_html=_student_answer_fragment(answer_node),
            correct_answer_html=_correct_answer_fragment(question_node),
            explanation_html=_explanation_fragment(question_node),
            attachments=answer_attachments,
        ))

    groups = []
    for group_number, (group_key, questions) in enumerate(
        grouped_questions.items(), 1
    ):
        known_scores = [
            question.score for question in questions
            if question.score is not None
        ]
        total_score = sum(known_scores) if known_scores else None
        title = group_headers[group_key]
        if title:
            title = _add_per_question_score(title, questions)
        else:
            title = _group_title(
                group_number, group_key[1], questions, total_score
            )
        groups.append(ExamQuestionGroup(
            title=title,
            question_type=group_key[1],
            questions=tuple(questions),
            total_score=total_score,
        ))

    return ExamMarkPaperContent(tuple(groups), submission=submission)


def parse_exam_question_mark_paper(html, referer=""):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    form = soup.select_one("form#submitMarking")
    if form is None:
        raise ValueError("按题批阅页面缺少提交表单")

    question_id_node = form.select_one("input#qid[name='qid']")
    if question_id_node is None:
        question_id_node = form.select_one("input[name='qid']")
    question_id = str(question_id_node.get("value") or "") if question_id_node else ""
    if not question_id:
        raise ValueError("按题批阅页面缺少题目 ID")

    source_stem = soup.select_one(".stem")
    hidden_title = source_stem.select_one(".hiddenTitle") if source_stem else None
    stem_text = source_stem.get_text(" ", strip=True) if source_stem else ""
    question_type_match = re.search(
        r"[（(]\s*([^，,()（）]+?题)\s*[，,]", stem_text
    )
    question_type = question_type_match.group(1) if question_type_match else "题目"
    number_node = soup.select_one(".changeTimu .timuNum")
    number_text = number_node.get_text(" ", strip=True) if number_node else stem_text
    number_match = re.search(r"\d+", number_text)
    question_number = number_match.group(0) if number_match else "1"

    question_node = soup.new_tag(
        "div",
        attrs={
            "class": "questionWrap",
            "index": question_number,
            "name": question_type,
        },
    )
    stem_node = soup.new_tag(
        "h3",
        attrs={"class": "mark_name", "id": f"questionStem_{question_id}"},
    )
    if hidden_title is not None:
        stem_node.append(deepcopy(hidden_title))
    elif source_stem is not None:
        stem_node.append(deepcopy(source_stem))
    question_node.append(stem_node)

    for control in form.select(
        f"input#fullScore{question_id}, input[name='score{question_id}']"
    ):
        question_node.append(deepcopy(control))

    answer_source = soup.select_one(
        f"#stuAnswer_{question_id} .answerCon.stuAnswerWords"
    )
    if answer_source is not None:
        answer_node = soup.new_tag("div", attrs={"class": "topicStudentAnswer"})
        answer_node.append(deepcopy(answer_source))
        question_node.append(answer_node)

    correct_source = soup.select_one(f"#correctanswer_{question_id}")
    if correct_source is not None:
        correct_node = soup.new_tag("div", attrs={"class": "topicRightAnswer"})
        correct_node.append(deepcopy(correct_source))
        question_node.append(correct_node)

    body = soup.body or soup
    body.append(question_node)
    content = parse_exam_mark_paper(str(soup), referer=referer)

    name_node = soup.select_one(".infoHead h2")
    if name_node is not None:
        for status in name_node.select(".markStatus"):
            status.decompose()
    student_name = name_node.get_text(" ", strip=True) if name_node else ""
    student_id_node = soup.select_one(".infoHead .xuehao")
    student_id = student_id_node.get_text(" ", strip=True) if student_id_node else ""
    answer_id_node = form.select_one("input[name='answerid']")
    answer_id = str(answer_id_node.get("value") or "") if answer_id_node else ""
    pending_node = soup.select_one(".markNumBx .waitMark")
    submitted_node = soup.select_one(".markNumBx .alreadyMark")

    def parse_count(node):
        if node is None:
            return None
        match = re.search(r"\d+", node.get_text(" ", strip=True))
        return int(match.group(0)) if match else None

    return ExamQuestionMarkPaper(
        content=content,
        student_name=student_name,
        student_id=student_id,
        answer_id=answer_id,
        pending_count=parse_count(pending_node),
        submitted_count=parse_count(submitted_node),
    )

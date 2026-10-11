from copy import deepcopy
from dataclasses import dataclass
import re

from bs4 import Tag


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
    reference_answer_html: str


@dataclass(frozen=True)
class ExamQuestionGroup:
    title: str
    question_type: str
    questions: tuple[ExamQuestionContent, ...]
    total_score: float | None


@dataclass(frozen=True)
class ExamMarkPaperContent:
    groups: tuple[ExamQuestionGroup, ...]

    @property
    def questions(self):
        return tuple(
            question
            for group in self.groups
            for question in group.questions
        )


_REMOVED_TAGS = {
    "button", "embed", "form", "iframe", "input", "object", "script",
    "select", "style", "textarea",
}
_MEDIA_TAGS = {"audio", "img", "svg", "video"}
_ALLOWED_TAGS = {
    "b", "blockquote", "br", "caption", "code", "dd", "del", "div",
    "dl", "dt", "em", "h1", "h2", "h3", "h4", "hr", "i", "li",
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


def _stem_fragment(stem_node, choices_node=None):
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
    if choices_node is not None:
        stem_html += _safe_fragment(choices_node)
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


def _group_title(group_number, question_type, questions, total_score):
    score_text = f"{total_score:.1f}" if total_score is not None else "未知"
    return (
        f"{_chinese_number(group_number)}.{question_type}"
        f"（共{len(questions)}题，{score_text}分）"
    )


def parse_exam_mark_paper(html):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
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
        reference_node = question_node.select_one(".answerAnalysis")
        if reference_node is None:
            reference_node = question_node.select_one(".topicRightAnswer")
        question_id = ""
        if stem_node is not None:
            question_id = str(stem_node.get("id") or "").removeprefix(
                "questionStem_"
            )
        earned_score, score_confirmed = _earned_score(question_node)

        grouped_questions[group_key].append(ExamQuestionContent(
            number=str(question_node.get("index") or index),
            question_type=question_type,
            score=_question_score(question_node),
            earned_score=earned_score,
            score_confirmed=score_confirmed,
            question_id=question_id,
            stem_html=_stem_fragment(stem_node, choices_node),
            student_answer_html=_student_answer_fragment(answer_node),
            reference_answer_html=_safe_fragment(reference_node),
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
        title = group_headers[group_key] or _group_title(
            group_number, group_key[1], questions, total_score
        )
        groups.append(ExamQuestionGroup(
            title=title,
            question_type=group_key[1],
            questions=tuple(questions),
            total_score=total_score,
        ))

    return ExamMarkPaperContent(tuple(groups))

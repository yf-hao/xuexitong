from html import escape
import math
from urllib.parse import urlsplit


def set_submission_field(fields, name, value, required=False):
    found = False
    updated = []
    for field_name, field_value in fields:
        if field_name == name:
            updated.append((field_name, str(value)))
            found = True
        else:
            updated.append((field_name, field_value))
    if not found:
        if required:
            raise ValueError(f"批阅表单缺少字段：{name}")
        updated.append((name, str(value)))
    return updated


def format_ai_teacher_content(breakdown):
    body = []
    summary = str(breakdown.get("summary", "")).strip()
    if summary:
        body.append(f"<p>{escape(summary)}</p>")
    for title, key, prefix in (
        ("得分点", "earned_points", "+"),
        ("失分点", "lost_points", "−"),
    ):
        entries = breakdown.get(key, [])
        if not entries:
            continue
        body.append(f"<p><strong>{title}</strong></p><ul>")
        for entry in entries:
            points = _format_score(float(entry["points"]))
            item = escape(str(entry.get("item", "")))
            evidence = escape(str(entry.get("evidence", "")))
            body.append(
                "<li>"
                f"<strong>{prefix}{points}分：</strong>{item}"
                f"<br>依据：{evidence}"
                "</li>"
            )
        body.append("</ul>")
    return "".join(body)


def build_exam_mark_submission_payload(
    content, score_overrides=None, ai_breakdowns=None
):
    submission = content.submission
    if submission is None:
        raise ValueError("当前答卷没有可用的批阅提交表单")
    if not content.questions:
        raise ValueError("答卷中没有可提交的题目")

    score_overrides = {
        str(key): value for key, value in (score_overrides or {}).items()
    }
    ai_breakdowns = {
        str(key): value for key, value in (ai_breakdowns or {}).items()
    }
    form_fields = list(submission.fields)
    if urlsplit(submission.action).path.endswith("/submit-markquestion"):
        if len(content.questions) != 1:
            raise ValueError("按题批阅页面应只包含当前题目")
        question = content.questions[0]
        question_id = str(question.question_id or "")
        if not question_id:
            raise ValueError("当前题目缺少题目 ID")
        original_values = dict(form_fields)
        score_field = f"score{question_id}"
        if score_field not in original_values:
            raise ValueError("按题批阅表单缺少当前题目的分数字段")
        score = score_overrides.get(question_id, question.earned_score)
        if score is None:
            try:
                score = float(original_values[score_field])
            except (TypeError, ValueError):
                raise ValueError("当前题目尚无有效得分，不能提交") from None
        score = float(score)
        maximum_score = question.score
        if maximum_score is None or not math.isfinite(maximum_score):
            raise ValueError("当前题目缺少有效满分")
        if (
            not math.isfinite(score)
            or score < 0
            or score > maximum_score + 1e-6
        ):
            raise ValueError(
                f"当前题目得分超出有效范围 0–{maximum_score:g}"
            )
        form_fields = set_submission_field(
            form_fields, score_field, f"{score:g}", required=True
        )
        breakdown = ai_breakdowns.get(question_id)
        if breakdown is not None:
            form_fields = set_submission_field(
                form_fields,
                f"teacherContent{question_id}",
                format_ai_teacher_content(breakdown),
                required=True,
            )
        return (
            submission.action,
            submission.query_params,
            tuple(form_fields),
            submission.referer,
        )

    original_values = dict(form_fields)
    required_globals = (
        "testUserRelationId", "testPaperId", "courseId", "classId",
        "questionId", "sumScore",
    )
    for name in required_globals:
        if not original_values.get(name, "").strip():
            raise ValueError(f"批阅表单缺少必要信息：{name}")

    final_scores = []
    for question in content.questions:
        question_id = str(question.question_id or "")
        if not question_id:
            raise ValueError(f"第 {question.number} 题缺少题目 ID")
        score_field = f"score{question_id}"
        if score_field not in original_values:
            raise ValueError(f"批阅表单缺少第 {question.number} 题的分数字段")
        score = score_overrides.get(question_id, question.earned_score)
        if score is None:
            try:
                score = float(original_values[score_field])
            except (TypeError, ValueError):
                raise ValueError(
                    f"第 {question.number} 题尚无有效得分，不能提交"
                ) from None
        score = float(score)
        maximum_score = question.score
        if maximum_score is None:
            try:
                maximum_score = float(original_values[f"per{question_id}"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(
                    f"第 {question.number} 题缺少有效满分"
                ) from None
        if (
            not math.isfinite(score)
            or score < 0
            or score > maximum_score + 1e-6
        ):
            raise ValueError(
                f"第 {question.number} 题得分超出有效范围 0–"
                f"{maximum_score:g}"
            )
        final_scores.append(score)
        form_fields = set_submission_field(
            form_fields, score_field, f"{score:g}", required=True
        )
        breakdown = ai_breakdowns.get(question_id)
        if breakdown is not None:
            form_fields = set_submission_field(
                form_fields,
                f"teacherContent{question_id}",
                format_ai_teacher_content(breakdown),
                required=True,
            )

    total_score = math.fsum(final_scores)
    form_fields = set_submission_field(
        form_fields, "sumScore", f"{total_score:g}", required=True
    )
    final_values = dict(form_fields)
    query_values = dict(submission.query_params)
    for name in (
        "classId", "markStyle", "submitType", "sumScore",
        "testUserRelationId",
    ):
        if name in final_values:
            query_values[name] = final_values[name]
    return (
        submission.action,
        tuple(query_values.items()),
        tuple(form_fields),
        submission.referer,
    )


def _format_score(score):
    if math.isfinite(score):
        nearest_integer = round(score)
        if math.isclose(score, nearest_integer, rel_tol=0.0, abs_tol=1e-6):
            return str(nearest_integer)
    return format(score, ".15g")
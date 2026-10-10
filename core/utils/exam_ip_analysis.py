from collections import defaultdict
from datetime import datetime, timedelta
import re


HIGH_RISK = "高风险线索"
MEDIUM_RISK = "中风险线索"
REVIEW_RISK = "重复IP（时间条件不足）"


def _parse_submit_time(value):
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None

    normalized = text.replace("T", " ").replace("/", "-")
    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(normalized, date_format)
        except ValueError:
            continue

    yearless_text = normalized
    chinese_date = re.fullmatch(r"(\d{1,2})月(\d{1,2})日\s+(.+)", normalized)
    if chinese_date:
        month, day, time_text = chinese_date.groups()
        yearless_text = f"{month}-{day} {time_text}"
    for date_format in ("%m-%d %H:%M:%S", "%m-%d %H:%M"):
        try:
            return datetime.strptime(f"2000-{yearless_text}", f"%Y-{date_format}")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_duration_minutes(value):
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    text = str(value or "").strip().lower()
    if not text:
        return None

    unit_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(小时|时|分钟|分|秒)", text)
    if unit_matches:
        minutes = 0.0
        for amount_text, unit in unit_matches:
            amount = float(amount_text)
            if unit in ("小时", "时"):
                minutes += amount * 60
            elif unit == "秒":
                minutes += amount / 60
            else:
                minutes += amount
        return minutes

    clock_match = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", text)
    if clock_match:
        first, second, third = clock_match.groups()
        if third is None:
            return int(first) + int(second) / 60
        return int(first) * 60 + int(second) + int(third) / 60

    try:
        minutes = float(text)
    except ValueError:
        return None
    return minutes if minutes >= 0 else None


def _format_minutes(minutes):
    if minutes is None:
        return "未知"
    if float(minutes).is_integer():
        return f"{int(minutes)}分钟"
    return f"{minutes:.1f}分钟"


def _student_label(record):
    name = str(record.get("createUserName") or "未知学生").strip()
    student_id = str(record.get("loginName") or "").strip()
    return f"{name}（{student_id}）" if student_id else name


def analyze_exam_ip_risks(records):
    grouped = defaultdict(dict)
    ip_displays = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        ip_value = str(record.get("receiveIp") or "").strip()
        if not ip_value or ip_value == "---":
            continue
        ip, separator, location = ip_value.partition("/")
        ip = ip.strip()
        if not ip:
            continue
        ip_displays.setdefault(ip, f"{ip}/{location.strip()}" if separator else ip)

        student_key = str(
            record.get("loginName")
            or record.get("studentId")
            or record.get("id")
            or _student_label(record)
        ).strip()
        entry = {
            "student_key": student_key,
            "label": _student_label(record),
            "submit_text": str(record.get("submitTime") or "未知"),
            "submit_at": _parse_submit_time(record.get("submitTime")),
            "duration_minutes": _parse_duration_minutes(
                record.get("examConsumeTime")
            ),
        }
        grouped[ip].setdefault(student_key, entry)

    results = []
    risk_order = {HIGH_RISK: 2, MEDIUM_RISK: 1, REVIEW_RISK: 0}
    for ip, students_by_id in grouped.items():
        students = list(students_by_id.values())
        if len(students) < 2:
            continue
        timed_students = sorted(
            (student for student in students if student["submit_at"] is not None),
            key=lambda student: student["submit_at"],
        )
        risk_level = REVIEW_RISK
        evidence = "同一 IP 涉及多名学生，但提交时间或答题用时不足以判断时间关联。"

        for previous, following in zip(timed_students, timed_students[1:]):
            submit_gap = following["submit_at"] - previous["submit_at"]
            candidate_level = None
            candidate_evidence = ""

            duration = following["duration_minutes"]
            if duration is not None:
                estimated_start = following["submit_at"] - timedelta(minutes=duration)
                handoff_gap = estimated_start - previous["submit_at"]
                if timedelta(0) <= handoff_gap <= timedelta(minutes=10):
                    candidate_level = HIGH_RISK
                    candidate_evidence = (
                        f"{previous['label']} 于 {previous['submit_at']:%m-%d %H:%M} 提交；"
                        f"{following['label']} 用时 {_format_minutes(duration)}，"
                        f"于 {following['submit_at']:%m-%d %H:%M} 提交，"
                        f"推算开考约为 {estimated_start:%m-%d %H:%M}，"
                        f"在前者提交后约 {int(handoff_gap.total_seconds() // 60)} 分钟开始。"
                    )

            if candidate_level is None and submit_gap >= timedelta(hours=2):
                candidate_level = MEDIUM_RISK
                candidate_evidence = (
                    f"{previous['label']} 与 {following['label']} 使用相同 IP，"
                    f"提交时间间隔约 {int(submit_gap.total_seconds() // 60)} 分钟"
                    "（达到 2 小时阈值）。"
                )

            if candidate_level and risk_order[candidate_level] > risk_order[risk_level]:
                risk_level = candidate_level
                evidence = candidate_evidence

        student_rows = sorted(
            students,
            key=lambda student: (
                student["submit_at"] is None,
                student["submit_at"] or datetime.max,
            ),
        )
        results.append({
            "ip": ip,
            "ip_display": ip_displays[ip],
            "risk_level": risk_level,
            "student_count": len(students),
            "students": student_rows,
            "evidence": evidence,
        })

    results.sort(
        key=lambda item: (
            -risk_order[item["risk_level"]],
            -item["student_count"],
            item["ip"],
        )
    )
    return results
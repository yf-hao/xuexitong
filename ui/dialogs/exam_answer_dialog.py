import base64
from html import escape

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from core.utils.exam_mark_paper_parser import ExamMarkPaperContent
from ui.theme import (
    apply_theme_stylesheet, bind_theme_tree, get_theme_palette, theme_manager,
)


class ExamAnswerDialog(QDialog):
    def __init__(
        self,
        exam_title: str,
        student_name: str,
        student_id: str,
        content: ExamMarkPaperContent,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"答卷查看 - {student_name or student_id}")
        self.resize(1000, 760)
        self._content = content
        self._setup_ui(exam_title, student_name, student_id, content)

    def _setup_ui(self, exam_title, student_name, student_id, content):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel(exam_title or "考试答卷")
        title.setObjectName("answer_exam_title")
        layout.addWidget(title)
        student_text = student_name or "未知学生"
        if student_id:
            student_text = f"{student_text}（{student_id}）"
        student = QLabel(student_text)
        student.setObjectName("answer_student")
        layout.addWidget(student)

        self.paper_browser = QTextBrowser()
        self.paper_browser.setObjectName("answer_paper")
        self.paper_browser.setReadOnly(True)
        self.paper_browser.setOpenLinks(False)
        self.paper_browser.setOpenExternalLinks(False)
        self.paper_browser.setHtml(self._paper_html(content))
        theme_manager().theme_changed.connect(self._refresh_paper_theme)
        layout.addWidget(self.paper_browser, 1)

        footer = QHBoxLayout()
        self.read_only_note = QLabel("只读查看，不会修改或提交成绩")
        self.read_only_note.setObjectName("answer_read_only_note")
        footer.addWidget(self.read_only_note)
        footer.addStretch()
        self.close_button = QPushButton("关闭")
        self.close_button.setMinimumWidth(84)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        apply_theme_stylesheet(self, lambda palette: f"""
            QWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QLabel#answer_exam_title {{
                color: {palette.text};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#answer_student {{
                color: {palette.text_secondary};
                font-size: 15px;
            }}
            QLabel#answer_read_only_note {{
                color: {palette.text_muted};
                font-size: 13px;
            }}
            QTextBrowser#answer_paper {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 3px;
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                border-color: {palette.accent};
            }}
        """)
        bind_theme_tree(self)

    def _refresh_paper_theme(self, mode):
        scroll_position = self.paper_browser.verticalScrollBar().value()
        self.paper_browser.setHtml(self._paper_html(self._content, mode))
        self.paper_browser.verticalScrollBar().setValue(scroll_position)

    def _paper_html(self, content, mode=None):
        palette = get_theme_palette(mode)
        avatar_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" '
            'viewBox="0 0 24 24">'
            f'<circle cx="12" cy="7.5" r="4" fill="{palette.accent}"/>'
            f'<path d="M3.5 21a8.5 8.5 0 0 1 17 0" fill="{palette.accent}"/>'
            '</svg>'
        )
        avatar_uri = "data:image/svg+xml;base64," + base64.b64encode(
            avatar_svg.encode("utf-8")
        ).decode("ascii")
        body = []
        for group in content.groups:
            body.append(
                f'<h2 class="group-title">{escape(group.title)}</h2>'
            )
            for question in group.questions:
                score_text = (
                    f", {question.score:.1f}分"
                    if question.score is not None else ""
                )
                heading = (
                    f"{question.number}. ({question.question_type}"
                    f"{score_text})"
                )
                earned_score = (
                    f"{question.earned_score:g}"
                    if question.earned_score is not None else "—"
                )
                body.append('<div class="question">')
                body.append('<div class="stem">')
                body.append(
                    f'<span class="question-prefix">{escape(heading)}</span> '
                )
                if question.stem_html:
                    body.append(question.stem_html)
                body.append("</div>")
                body.append(
                    '<table class="answer-row" width="100%"><tr>'
                    '<td class="answer-copy">'
                    f'<img class="student-avatar" src="{avatar_uri}" '
                    'width="22" height="22" align="middle"/> '
                    '<b>学生答案：</b>'
                    f'{question.student_answer_html or "暂无作答"}</td>'
                    '<td class="answer-score"><span class="score-label">得分：</span>'
                    f'<span class="score-value">{earned_score}</span>'
                    ' <span>分</span>'
                    f'{"&nbsp;&nbsp;<span class=score-check>✓</span>" if question.score_confirmed else ""}'
                    '</td></tr></table>'
                )
                if question.reference_answer_html:
                    body.append(
                        '<div class="reference"><b>参考答案：</b>'
                        f'{question.reference_answer_html}</div>'
                    )
                body.append("</div>")

        return f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"><style>
            body {{
                color: {palette.text};
                font-size: 14pt;
                margin: 8px;
            }}
            .group-title {{
                border-bottom: 1px solid {palette.border};
                font-size: 20pt;
                margin: 20px 0 14px;
                padding-bottom: 10px;
            }}
            .question {{
                background-color: {palette.panel_alt_bg};
                border: 1px solid {palette.border};
                border-radius: 4px;
                margin: 0 0 14px;
                padding: 10px 12px;
            }}
            .stem {{
                font-size: 14pt;
                margin: 4px 0 12px;
            }}
            .question-prefix {{
                color: {palette.text_muted};
                font-size: 14pt;
                font-weight: normal;
                margin-right: 4px;
            }}
            .answer-row {{
                background-color: {palette.panel_alt_bg};
                border-collapse: collapse;
                margin-top: 10px;
                width: 100%;
            }}
            .answer-row td {{
                border: none;
                padding: 8px 10px;
                vertical-align: middle;
            }}
            .answer-copy {{ font-size: 14pt; }}
            .answer-score {{
                text-align: right;
                white-space: nowrap;
            }}
            .score-label {{ font-size: 14pt; }}
            .score-value {{
                background-color: {palette.panel_bg};
                border: 1px solid {palette.border};
                border-radius: 4px;
                border-color: {palette.success};
                color: {palette.success};
                display: inline-block;
                font-size: 14pt;
                min-width: 52px;
                padding: 3px 10px;
                text-align: center;
            }}
            .score-check {{
                color: {palette.success};
                font-size: 22pt;
                font-weight: bold;
                padding-left: 8px;
            }}
            .stem p, .answer p, .reference p {{ margin: 4px 0; }}
            .reference {{ margin-top: 10px; }}
            .reference {{ color: {palette.text_secondary}; }}
            table {{ border-collapse: collapse; }}
            td, th {{ border: 1px solid {palette.border}; padding: 4px; }}
        </style></head><body>{''.join(body)}</body></html>"""

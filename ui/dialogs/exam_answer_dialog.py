import base64
import math
import os
from html import escape

from bs4 import BeautifulSoup
from PyQt6.QtCore import QThread, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QApplication, QDialog, QDoubleSpinBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QInputDialog, QMenu, QMessageBox, QScrollArea, QTextBrowser, QVBoxLayout,
    QWidget,
)

from core.apis.exam_api import (
    download_exam_attachment, exam_attachment_cache_path,
)
from core.logger import get_logger
from core.ui_diagnostics import log_dialog_state, log_exception_frames
from core.utils.attachment_preview import (
    UnsupportedAttachmentPreviewError, render_attachment_preview,
)
from core.utils.exam_mark_paper_parser import ExamMarkPaperContent
from core.utils.exam_score_drafts import (
    ExamScoreDraftStore, distribute_group_score,
)
from ui.dialogs.attachment_preview_dialog import AttachmentPreviewDialog
from ui.theme import (
    apply_theme_stylesheet, bind_theme_tree, get_theme_palette, theme_manager,
)

logger = get_logger()


class _SelectAllOnFocusLineEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.selectAll()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selectAll()


class _GroupTotalScoreSpinBox(QDoubleSpinBox):
    cancelled = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _ExamAttachmentDownloadWorker(QThread):
    completed = pyqtSignal(str, bool, object)

    def __init__(self, session, attachment, save_path, action, parent=None):
        super().__init__(parent)
        self.session = session
        self.attachment = attachment
        self.save_path = save_path
        self.action = action

    def run(self):
        try:
            cache_hit = (
                os.path.isfile(self.save_path)
                and os.path.getsize(self.save_path) > 0
            )
            logger.info(
                "UI_DIAG attachment_worker_started action=%s cache_hit=%s",
                self.action,
                cache_hit,
            )
            if self.action == "open":
                if not cache_hit:
                    logger.info("UI_DIAG attachment_download_started")
                    download_exam_attachment(
                        self.session,
                        self.attachment.object_id,
                        self.save_path,
                    )
                    logger.info("UI_DIAG attachment_download_completed")
                logger.info("UI_DIAG attachment_render_started")
                try:
                    preview = render_attachment_preview(self.save_path)
                except UnsupportedAttachmentPreviewError:
                    preview = None
                logger.info(
                    "UI_DIAG attachment_render_completed supported=%s",
                    preview is not None,
                )
                result = {
                    "action": self.action,
                    "path": self.save_path,
                    "preview": preview,
                }
                self.completed.emit(self.attachment.object_id, True, result)
                return

            result = download_exam_attachment(
                self.session,
                self.attachment.object_id,
                self.save_path,
            )
            self.completed.emit(
                self.attachment.object_id,
                True,
                {"action": self.action, "path": result},
            )
        except Exception as exc:
            log_exception_frames("attachment_worker_failed", exc)
            self.completed.emit(self.attachment.object_id, False, str(exc))


class ExamAnswerDialog(QDialog):
    def __init__(
        self,
        exam_title: str,
        student_name: str,
        student_id: str,
        content: ExamMarkPaperContent,
        parent=None,
        exam_id: str = "",
        answer_id: str = "",
        session=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"答卷查看 - {student_name or student_id}")
        self.resize(1280, 800)
        self._content = content
        self._selected_navigation_button = None
        self._exam_id = str(exam_id or exam_title or "")
        self._answer_id = str(answer_id or student_id or "")
        self._student_id = str(student_id or student_name or "")
        self._session = session
        self._answer_attachments = {
            attachment.object_id: attachment
            for question in content.questions
            for attachment in question.attachments
        }
        self._attachment_workers = {}
        self._score_draft_store = ExamScoreDraftStore()
        self._score_draft_questions = {}
        self._draft_scores = {}
        self._load_score_drafts(content)
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
        self.paper_browser.anchorClicked.connect(self._on_paper_link_clicked)
        self.paper_browser.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.paper_browser.customContextMenuRequested.connect(
            self._show_attachment_context_menu
        )
        self.paper_browser.setHtml(self._paper_html(content))
        theme_manager().theme_changed.connect(self._refresh_paper_theme)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        content_layout.addWidget(self.paper_browser, 1)
        self._build_question_navigation(content)
        content_layout.addWidget(self.navigation_scroll)
        layout.addLayout(content_layout, 1)

        footer = QHBoxLayout()
        note = "分数只保存到本地草稿，不会提交成绩" if self._score_draft_questions else "只读查看，不会修改或提交成绩"
        self.read_only_note = QLabel(note)
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
            QLabel#question_navigation_title {{
                color: {palette.text};
                font-size: 16px;
                font-weight: bold;
                padding: 4px 0;
            }}
            QLabel#question_navigation_group {{
                color: {palette.text};
                font-size: 13px;
                font-weight: bold;
                padding-top: 5px;
            }}
            QPushButton#question_navigation_total_score {{
                background-color: {palette.panel_alt_bg};
                border: 1px solid {palette.border};
                border-radius: 3px;
                color: {palette.accent_focus};
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
            }}
            QPushButton#question_navigation_total_score:enabled:hover,
            QPushButton#question_navigation_total_score:focus {{
                background-color: {palette.hover_bg};
                border-color: {palette.accent};
            }}
            QPushButton#question_navigation_total_score:disabled {{
                color: {palette.text_muted};
            }}
            QLabel#question_navigation_summary {{
                color: {palette.text_muted};
                font-size: 11px;
            }}
            QPushButton#question_navigation_tile {{
                background-color: {palette.panel_alt_bg};
                border: 1px solid {palette.border};
                border-radius: 6px;
                color: {palette.text};
                font-size: 12px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton#question_navigation_tile[gradingStatus="correct"] {{
                background-color: {palette.panel_alt_bg};
                border-color: {palette.success};
                color: {palette.success};
            }}
            QPushButton#question_navigation_tile[gradingStatus="incorrect"] {{
                background-color: {palette.danger_soft};
                border-color: {palette.danger};
                color: {palette.danger};
            }}
            QPushButton#question_navigation_tile[gradingStatus="partial"] {{
                background-color: {palette.accent_soft};
                border-color: {palette.accent};
                color: {palette.accent};
            }}
            QPushButton#question_navigation_tile[gradingStatus="graded"] {{
                background-color: {palette.panel_alt_bg};
                border-color: {palette.accent};
                color: {palette.accent};
            }}
            QPushButton#question_navigation_tile[selectedQuestion="true"] {{
                border: 2px solid {palette.accent_focus};
            }}
            QDoubleSpinBox#question_navigation_score_input {{
                background-color: {palette.panel_bg};
                border: 1px solid {palette.border};
                border-radius: 3px;
                color: {palette.text};
                font-size: 10px;
                padding: 1px 2px;
            }}
            QDoubleSpinBox#question_navigation_total_score_input {{
                background-color: {palette.panel_bg};
                border: 1px solid {palette.border};
                border-radius: 3px;
                color: {palette.text};
                font-size: 11px;
                padding: 2px 6px;
            }}
            QDoubleSpinBox#question_navigation_score_input:focus {{
                border-color: {palette.accent};
            }}
            QDoubleSpinBox#question_navigation_total_score_input:focus {{
                border-color: {palette.accent};
            }}
            QLabel#question_navigation_badge {{
                border: 2px solid {palette.panel_bg};
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }}
            QLabel#question_navigation_badge[gradingStatus="correct"] {{
                background-color: {palette.success};
                color: #ffffff;
            }}
            QLabel#question_navigation_badge[gradingStatus="incorrect"] {{
                background-color: {palette.danger};
                color: #ffffff;
            }}
            QLabel#question_navigation_badge[gradingStatus="partial"],
            QLabel#question_navigation_badge[gradingStatus="graded"] {{
                background-color: {palette.accent};
                color: #ffffff;
            }}
            QLabel#question_navigation_badge[gradingStatus="pending"] {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
            }}
        """)
        bind_theme_tree(self)

    @staticmethod
    def _is_objective_question(question):
        return question.question_type in {"单选题", "多选题", "判断题"}

    @classmethod
    def _can_edit_score(cls, question):
        return (
            not question.score_confirmed
            and question.earned_score is not None
        )

    def _score_draft_key(self, question):
        return self._score_draft_store.make_key(
            self._exam_id,
            self._answer_id,
            self._student_id,
            question.question_id,
            question.number,
            question.question_type,
        )

    def _load_score_drafts(self, content):
        for question in content.questions:
            if not self._can_edit_score(question):
                continue
            key = self._score_draft_key(question)
            self._score_draft_questions[key] = question
            try:
                saved_score = self._score_draft_store.get_score(key)
            except (OSError, ValueError):
                saved_score = None
            if saved_score is not None:
                self._draft_scores[key] = float(saved_score)

    def _on_paper_link_clicked(self, url):
        if url.scheme() == "exam-attachment":
            object_id = url.path().lstrip("/") or url.host()
            self._open_answer_attachment(object_id)
            return
        if url.scheme() != "score-draft":
            return
        key = url.path().lstrip("/")
        question = self._score_draft_questions.get(key)
        if question is None:
            return
        current_score = self._draft_scores.get(key, question.earned_score)
        maximum_score = question.score if question.score and question.score > 0 else 1000
        score, accepted = QInputDialog.getDouble(
            self,
            f"修改第 {question.number} 题得分",
            f"输入分数（0–{maximum_score:g}）：",
            current_score,
            0,
            maximum_score,
            2,
        )
        if not accepted:
            return
        self._save_score_draft(key, question, score)

    def _download_answer_attachment(self, object_id):
        attachment = self._answer_attachments.get(str(object_id))
        if attachment is None:
            return
        if self._session is None:
            QMessageBox.warning(self, "下载失败", "当前没有可用的学习通登录会话")
            return
        if object_id in self._attachment_workers:
            return

        filename = os.path.basename(attachment.filename.replace("\\", "/"))
        if not filename:
            filename = str(object_id)
        default_path = os.path.join(
            os.path.expanduser("~/Downloads"), filename
        )
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "下载学生答案附件",
            default_path,
            "所有文件 (*)",
        )
        if not save_path:
            return

        self._start_attachment_worker(
            attachment, save_path, "download"
        )

    def _open_answer_attachment(self, object_id):
        attachment = self._answer_attachments.get(str(object_id))
        if attachment is None:
            return
        if self._session is None:
            QMessageBox.warning(self, "打开失败", "当前没有可用的学习通登录会话")
            return
        cache_path = exam_attachment_cache_path(
            attachment.object_id, attachment.filename
        )
        self._start_attachment_worker(attachment, cache_path, "open")

    def _start_attachment_worker(self, attachment, save_path, action):
        object_id = str(attachment.object_id)
        if object_id in self._attachment_workers:
            return
        logger.info("UI_DIAG attachment_action_started action=%s", action)
        worker = _ExamAttachmentDownloadWorker(
            self._session,
            attachment,
            save_path,
            action,
            QApplication.instance(),
        )
        worker.completed.connect(self._on_attachment_download_completed)
        worker.finished.connect(worker.deleteLater)
        self._attachment_workers[object_id] = worker
        action_text = "打开" if action == "open" else "下载"
        self.read_only_note.setText(
            f"正在{action_text}附件：{attachment.filename}"
        )
        worker.start()

    def _show_attachment_context_menu(self, position):
        href = self.paper_browser.anchorAt(position)
        url = QUrl(href)
        if url.scheme() != "exam-attachment":
            return
        object_id = url.path().lstrip("/") or url.host()
        if object_id not in self._answer_attachments:
            return

        menu = QMenu(self)
        apply_theme_stylesheet(menu, lambda palette: f"""
            QMenu {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: 1px solid {palette.border_strong};
                padding: 6px 4px;
            }}
            QMenu::item {{
                min-width: 132px;
                min-height: 24px;
                padding: 10px 28px;
                margin: 3px 4px;
                border: 1px solid transparent;
                border-radius: 4px;
            }}
            QMenu::item:hover,
            QMenu::item:selected,
            QMenu::item:focus {{
                background-color: {palette.accent};
                color: #ffffff;
                border-color: {palette.accent_focus};
            }}
        """)
        download_action = menu.addAction("下载")
        open_action = menu.addAction("打开")
        selected_action = menu.exec(
            self.paper_browser.viewport().mapToGlobal(position)
        )
        if selected_action == download_action:
            self._download_answer_attachment(object_id)
        elif selected_action == open_action:
            self._open_answer_attachment(object_id)

    def _on_attachment_download_completed(self, object_id, succeeded, detail):
        self._attachment_workers.pop(str(object_id), None)
        logger.info(
            "UI_DIAG attachment_action_completed succeeded=%s",
            succeeded,
        )
        if not succeeded:
            self.read_only_note.setText("附件下载失败")
            QMessageBox.warning(self, "附件下载失败", detail)
            return

        action = detail.get("action")
        path = detail.get("path", "")
        if action == "open":
            preview = detail.get("preview")
            if preview is not None:
                preview_dialog = AttachmentPreviewDialog(preview, self)
                logger.info("UI_DIAG preview_dialog_exec_enter")
                log_dialog_state("preview_dialog_exec_enter", preview_dialog)
                preview_dialog.exec()
                logger.info("UI_DIAG preview_dialog_exec_returned")
                log_dialog_state("preview_dialog_exec_returned", self)
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
                QMessageBox.warning(
                    self,
                    "打开失败",
                    f"当前系统无法打开此附件：{path}",
                )
            self.read_only_note.setText(
                f"附件已打开：{os.path.basename(path)}"
            )
        else:
            self.read_only_note.setText(
                f"附件已下载：{os.path.basename(path)}"
            )

    def _save_score_draft(self, key, question, score):
        try:
            self._score_draft_store.save_score(
                key,
                score,
                exam_id=self._exam_id,
                answer_id=self._answer_id,
                student_id=self._student_id,
                question_id=question.question_id,
                question_number=question.number,
                question_type=question.question_type,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "保存失败", f"分数未能保存到本地：{exc}")
            return False
        self._draft_scores[key] = score
        self.read_only_note.setText("分数已保存到本地草稿，不会提交成绩")
        self._refresh_group_score_buttons()
        self._refresh_navigation_summaries()
        self._refresh_paper_theme(None)
        return True

    def _begin_group_score_edit(self, group, editor, badge):
        current_score = self._group_earned_score(group)
        editor.setValue(float(current_score or 0))
        badge.hide()
        editor.show()
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        editor.lineEdit().selectAll()

    @staticmethod
    def _cancel_group_score_edit(editor, badge):
        editor.hide()
        badge.show()

    def _apply_group_score_edit(self, group, editor, badge):
        if editor.isHidden():
            return
        if not all(self._can_edit_score(question) for question in group.questions):
            self._cancel_group_score_edit(editor, badge)
            QMessageBox.warning(
                self,
                "无法批量赋分",
                "该题型中有试题已确认评分或不能修改，请逐题检查。",
            )
            return

        try:
            scores = distribute_group_score(
                editor.value(), [question.score for question in group.questions]
            )
        except ValueError as exc:
            QMessageBox.warning(self, "总分无效", str(exc))
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
            editor.lineEdit().selectAll()
            return

        entries = []
        keyed_scores = []
        for question, score in zip(group.questions, scores):
            key = self._score_draft_key(question)
            metadata = {
                "exam_id": self._exam_id,
                "answer_id": self._answer_id,
                "student_id": self._student_id,
                "question_id": question.question_id,
                "question_number": question.number,
                "question_type": question.question_type,
            }
            entries.append((key, score, metadata))
            keyed_scores.append((key, question, score))

        try:
            self._score_draft_store.save_scores(entries)
        except (OSError, ValueError) as exc:
            self._cancel_group_score_edit(editor, badge)
            QMessageBox.warning(
                self, "保存失败", f"分数未能保存到本地：{exc}"
            )
            return

        editor.hide()
        badge.show()
        for key, question, score in keyed_scores:
            self._draft_scores[key] = score
            score_input = self.question_navigation_score_inputs.get(key)
            if score_input is not None:
                score_input.blockSignals(True)
                score_input.setValue(score)
                score_input.blockSignals(False)

        self.read_only_note.setText(
            "已将总分随机均分到本题型各题，并保存到本地草稿；不会提交成绩"
        )
        self._refresh_group_score_buttons()
        self._refresh_navigation_summaries()
        self._refresh_paper_theme(None)

    @staticmethod
    def _format_score(score):
        if math.isfinite(score):
            nearest_integer = round(score)
            if math.isclose(
                score, nearest_integer, rel_tol=0.0, abs_tol=1e-6
            ):
                return str(nearest_integer)
        return format(score, ".15g")

    def _group_earned_score(self, group):
        scores = []
        for question in group.questions:
            key = self._score_draft_key(question)
            score = self._draft_scores.get(key, question.earned_score)
            if score is None:
                return None
            scores.append(float(score))
        return math.fsum(scores) if scores else None

    def _refresh_group_score_buttons(self):
        for button, group in self._navigation_group_totals:
            earned_score = self._group_earned_score(group)
            text = (
                f"得分 {self._format_score(earned_score)}"
                if earned_score is not None
                else "得分未知"
            )
            button.setText(text)

    def _group_score_summary(self, group):
        score_groups = []
        for question in group.questions:
            if question.score is None:
                continue
            matching_group = next(
                (
                    score_group for score_group in score_groups
                    if math.isclose(
                        question.score,
                        score_group["score"],
                        rel_tol=0.0,
                        abs_tol=1e-6,
                    )
                ),
                None,
            )
            if matching_group is None:
                matching_group = {
                    "score": question.score,
                    "questions": [],
                }
                score_groups.append(matching_group)
            matching_group["questions"].append(question)

        reviewed_count = sum(
            (
                question.score_confirmed
                and question.earned_score is not None
            )
            or self._score_draft_key(question) in self._draft_scores
            for question in group.questions
        )
        question_count = len(group.questions)

        if len(score_groups) == 1 and len(score_groups[0]["questions"]) == question_count:
            score = score_groups[0]["score"]
            total_score = math.fsum(q.score for q in group.questions)
            score_text = (
                f"每题{self._format_score(score)}分，"
                f"共{self._format_score(total_score)}分"
            )
        elif score_groups and sum(
            len(score_group["questions"]) for score_group in score_groups
        ) == question_count:
            score_details = "，".join(
                f"第{'、'.join(q.number for q in score_group['questions'])}题"
                f"{self._format_score(score_group['score'])}分"
                for score_group in score_groups
            )
            total_score = math.fsum(
                question.score for question in group.questions
            )
            score_text = (
                f"{score_details}，共"
                f"{self._format_score(total_score)}分"
            )
        else:
            score_text = "分值未完整识别"

        return f"{score_text}，已批阅{reviewed_count}/{question_count}"

    def _refresh_navigation_summaries(self):
        for label, group in self._navigation_group_summaries:
            label.setText(self._group_score_summary(group))

    def _build_question_navigation(self, content):
        self.navigation_scroll = QScrollArea()
        self.navigation_scroll.setObjectName("question_navigation_scroll")
        self.navigation_scroll.setWidgetResizable(True)
        self.navigation_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.navigation_scroll.setFixedWidth(270)

        panel = QWidget()
        panel.setObjectName("question_navigation_panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(8)

        title = QLabel("题目导航")
        title.setObjectName("question_navigation_title")
        panel_layout.addWidget(title)
        self.question_navigation_buttons = {}
        self._navigation_group_summaries = []

        status_labels = {
            "correct": "正确",
            "incorrect": "错误",
            "partial": "部分得分",
            "graded": "已批阅",
            "pending": "待批阅",
        }
        status_symbols = {
            "correct": "✓",
            "incorrect": "×",
            "partial": "•",
            "graded": "✓",
            "pending": "·",
        }

        for group_index, group in enumerate(content.groups, 1):
            group_header = QWidget()
            group_header_layout = QHBoxLayout(group_header)
            group_header_layout.setContentsMargins(0, 0, 0, 0)
            group_header_layout.setSpacing(6)

            group_heading = QLabel(group.title.split("（", 1)[0])
            group_heading.setObjectName("question_navigation_group")
            group_header_layout.addWidget(group_heading, 1)

            scores_complete = bool(group.questions) and all(
                question.score is not None for question in group.questions
            )
            current_group_score = self._group_earned_score(group)
            total_score_text = (
                f"得分 {self._format_score(current_group_score)}"
                if current_group_score is not None
                else "得分未知"
            )
            bulk_score_enabled = (
                scores_complete
                and group.total_score is not None
                and group.total_score >= 0
                and all(
                    self._can_edit_score(question)
                    for question in group.questions
                )
            )
            group_total_score = QPushButton(total_score_text)
            group_total_score.setObjectName("question_navigation_total_score")
            group_total_score.setFixedWidth(100)
            group_total_score.setEnabled(bulk_score_enabled)
            group_total_score.setToolTip(
                "点击输入本题型得分，按各题满分随机均分；只保存到本地草稿"
                if bulk_score_enabled
                else "评分已确认或分值未完整识别，无法批量赋分"
            )
            group_header_layout.addWidget(group_total_score)
            if not hasattr(self, "_navigation_group_totals"):
                self._navigation_group_totals = []
            self._navigation_group_totals.append((group_total_score, group))

            group_score_input = _GroupTotalScoreSpinBox()
            group_score_input.setLineEdit(_SelectAllOnFocusLineEdit())
            group_score_input.setObjectName(
                "question_navigation_total_score_input"
            )
            group_score_input.setFixedWidth(100)
            group_score_input.setButtonSymbols(
                QAbstractSpinBox.ButtonSymbols.NoButtons
            )
            group_score_input.setDecimals(2)
            group_score_input.setKeyboardTracking(False)
            group_score_input.setRange(
                0, max(0.0, float(group.total_score or 0))
            )
            group_score_input.setToolTip(
                "输入本题型要分配的总得分，回车保存；Esc 取消"
            )
            group_score_input.hide()
            group_header_layout.addWidget(group_score_input)
            group_total_score.clicked.connect(
                lambda checked=False, target=group, editor=group_score_input,
                badge=group_total_score: self._begin_group_score_edit(
                    target, editor, badge
                )
            )
            group_score_input.editingFinished.connect(
                lambda target=group, editor=group_score_input,
                badge=group_total_score: self._apply_group_score_edit(
                    target, editor, badge
                )
            )
            group_score_input.cancelled.connect(
                lambda editor=group_score_input, badge=group_total_score:
                self._cancel_group_score_edit(editor, badge)
            )
            panel_layout.addWidget(group_header)

            summary_label = QLabel(self._group_score_summary(group))
            summary_label.setObjectName("question_navigation_summary")
            summary_label.setWordWrap(True)
            panel_layout.addWidget(summary_label)
            self._navigation_group_summaries.append((summary_label, group))

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(2)
            grid.setVerticalSpacing(5)
            if not hasattr(self, "question_navigation_score_inputs"):
                self.question_navigation_score_inputs = {}
            for question_index, question in enumerate(group.questions, 1):
                status = question.grading_status
                anchor = self._question_anchor(group_index, question_index)
                tooltip = f"第 {question.number} 题 · {status_labels[status]}"
                if question.earned_score is not None and question.score is not None:
                    tooltip += (
                        f" · {question.earned_score:g}/{question.score:g} 分"
                    )

                tile = QWidget()
                tile_layout = QVBoxLayout(tile)
                tile_layout.setContentsMargins(0, 0, 0, 0)
                tile_layout.setSpacing(2)

                button_tile = QWidget()
                button_tile.setFixedSize(44, 44)
                button_tile_layout = QGridLayout(button_tile)
                button_tile_layout.setContentsMargins(0, 0, 0, 0)

                button = QPushButton(question.number)
                button.setObjectName("question_navigation_tile")
                button.setFixedSize(38, 38)
                button.setProperty("gradingStatus", status)
                button.setProperty("selectedQuestion", False)
                button.setToolTip(tooltip)
                button.setAccessibleName(tooltip)
                button.clicked.connect(
                    lambda checked=False, target=anchor, item=button:
                    self._navigate_to_question(target, item)
                )
                button_tile_layout.addWidget(
                    button, 0, 0,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )

                badge = QLabel(status_symbols[status])
                badge.setObjectName("question_navigation_badge")
                badge.setProperty("gradingStatus", status)
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setFixedSize(19, 19)
                badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                button_tile_layout.addWidget(
                    badge, 0, 0,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                )
                tile_layout.addWidget(
                    button_tile, alignment=Qt.AlignmentFlag.AlignHCenter
                )

                if self._can_edit_score(question):
                    score_key = self._score_draft_key(question)
                    maximum_score = (
                        question.score
                        if question.score and question.score > 0 else 1000
                    )
                    score_input = QDoubleSpinBox()
                    score_input.setLineEdit(_SelectAllOnFocusLineEdit())
                    score_input.setObjectName(
                        "question_navigation_score_input"
                    )
                    score_input.setFixedWidth(48)
                    score_input.setButtonSymbols(
                        QAbstractSpinBox.ButtonSymbols.NoButtons
                    )
                    score_input.setDecimals(2)
                    score_input.setKeyboardTracking(False)
                    score_input.setRange(0, maximum_score)
                    score_input.setValue(
                        self._draft_scores.get(
                            score_key, question.earned_score
                        )
                    )
                    score_input.setToolTip(
                        f"第 {question.number} 题得分，修改后保存到本地草稿"
                    )
                    score_input.valueChanged.connect(
                        lambda value, key=score_key, item=question:
                        self._save_score_draft(key, item, value)
                    )
                    tile_layout.addWidget(
                        score_input, alignment=Qt.AlignmentFlag.AlignHCenter
                    )
                    self.question_navigation_score_inputs[score_key] = score_input

                row, column = divmod(question_index - 1, 5)
                grid.addWidget(tile, row, column)
                self.question_navigation_buttons[anchor] = button
            panel_layout.addLayout(grid)

        panel_layout.addStretch(1)
        self.navigation_scroll.setWidget(panel)

    @staticmethod
    def _question_anchor(group_index, question_index):
        return f"exam-question-{group_index}-{question_index}"

    def _navigate_to_question(self, anchor, button):
        self.paper_browser.scrollToAnchor(anchor)
        previous = self._selected_navigation_button
        if previous is not None:
            previous.setProperty("selectedQuestion", False)
            previous.style().unpolish(previous)
            previous.style().polish(previous)
        button.setProperty("selectedQuestion", True)
        button.style().unpolish(button)
        button.style().polish(button)
        self._selected_navigation_button = button

    @staticmethod
    def _stem_with_question_number(question):
        fragment = BeautifulSoup(question.stem_html or "", "html.parser")
        first_text = next(
            (node for node in fragment.find_all(string=True) if node.strip()),
            None,
        )
        target = first_text.parent if first_text is not None else fragment
        block_tags = {"blockquote", "div", "h1", "h2", "h3", "li", "p", "pre", "td", "th"}
        while target is not fragment and target.name not in block_tags:
            target = target.parent

        prefix = fragment.new_tag("span", attrs={"class": "question-prefix"})
        prefix.string = f"{question.number}."
        target.insert(0, prefix)
        prefix.insert_after(" ")
        return fragment.decode_contents()

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
        correct_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
            'viewBox="0 0 24 24">'
            f'<circle cx="12" cy="12" r="11" fill="{palette.success}"/>'
            '<path d="m7 12.5 3.2 3.2L17.5 8" fill="none" stroke="#ffffff" '
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
        )
        explanation_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
            'viewBox="0 0 24 24" fill="none" '
            f'stroke="{palette.text_muted}" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M9 18h6M10 22h4M8.4 14.6a6 6 0 1 1 7.2 0c-.9.6-1.4 1.5-1.6 3.4h-4c-.2-1.9-.7-2.8-1.6-3.4Z"/>'
            '</svg>'
        )
        avatar_uri = self._svg_data_uri(avatar_svg)
        correct_uri = self._svg_data_uri(correct_svg)
        explanation_uri = self._svg_data_uri(explanation_svg)
        body = []
        question_order = 0
        for group_index, group in enumerate(content.groups, 1):
            body.append(
                f'<h2 class="group-title">{escape(group.title)}</h2>'
            )
            for question_index, question in enumerate(group.questions, 1):
                question_class = (
                    "question-card question-card-alternate"
                    if question_order % 2 else "question-card"
                )
                question_order += 1
                anchor = self._question_anchor(group_index, question_index)
                grading_status = question.grading_status
                student_answer_class = {
                    "correct": "student-answer-correct",
                    "incorrect": "student-answer-incorrect",
                }.get(grading_status, "")
                score_value_class = {
                    "correct": "score-value-correct",
                    "incorrect": "score-value-incorrect",
                }.get(grading_status, "")
                score_indicator = {
                    "correct": '<span class="score-check">✓</span>',
                    "incorrect": '<span class="score-cross">&times;</span>',
                }.get(grading_status, "")
                editable_score = self._can_edit_score(question)
                score_key = (
                    self._score_draft_key(question) if editable_score else ""
                )
                displayed_score = self._draft_scores.get(
                    score_key, question.earned_score
                )
                score_text = (
                    f"{displayed_score:g}"
                    if displayed_score is not None else "—"
                )
                is_objective = self._is_objective_question(question)
                if editable_score and not is_objective:
                    score_value = (
                    f'<a class="score-value score-value-editable" '
                    f'href="score-draft:{score_key}" '
                    'title="点击编辑并保存到本地草稿">'
                    f'{score_text}</a>'
                    )
                else:
                    value_class = (
                        "score-value-editable"
                        if editable_score else score_value_class
                    )
                    score_value = (
                        f'<span class="score-value {value_class}">'
                        f'{score_text}</span>'
                    )
                answer_has_text = bool(
                    BeautifulSoup(
                        question.student_answer_html or "",
                        "html.parser",
                    ).get_text(strip=True)
                )
                empty_answer = (
                    "答案以附件提交" if question.attachments else "暂无作答"
                )
                student_answer = (
                    question.student_answer_html
                    if answer_has_text else empty_answer
                )
                attachment_only_answer = (
                    bool(question.attachments) and not answer_has_text
                )
                if student_answer_class:
                    student_answer = (
                        f'<span class="{student_answer_class}">'
                        f'{student_answer}</span>'
                    )
                body.append(
                    f'<a name="{anchor}"></a><table class="{question_class}" width="100%"><tr><td class="question-surface">'
                )
                body.append('<div class="stem-panel">')
                body.append(self._stem_with_question_number(question))
                body.append('</div>')
                body.append('<hr class="answer-divider"/>')
                body.append('<div class="answer-details">')
                body.append(
                    '<table class="answer-details-table" width="100%">'
                )
                body.append(
                    '<tr>'
                    '<td class="answer-icon-cell" width="32">'
                    f'<img class="student-avatar" src="{avatar_uri}" '
                    'width="22" height="22" align="middle"/></td>'
                )
                if is_objective:
                    body.append(
                        '<td class="answer-content"><b>学生答案：</b>&nbsp;'
                        f'{student_answer}</td>'
                    )
                elif attachment_only_answer:
                    body.append(
                        '<td class="answer-content"><b>学生答案：</b>&nbsp;'
                        f'{student_answer}</td>'
                    )
                else:
                    body.append(
                        '<td class="answer-content"><b>学生答案：</b></td>'
                    )
                body.append(
                    '<td class="answer-score"><span class="score-label">得分：</span>'
                    f'{score_value}'
                    ' <span>分</span>'
                    f'{"&nbsp;&nbsp;" if score_indicator else ""}'
                    f'{score_indicator}'
                    '</td></tr>'
                )
                if not is_objective and not attachment_only_answer:
                    body.append(
                        '<tr><td class="subjective-answer" colspan="3">'
                        f'{student_answer}</td></tr>'
                    )
                if question.attachments:
                    body.append(
                        '<tr><td class="answer-icon-cell" width="32"></td>'
                        '<td class="answer-content answer-attachments" colspan="2">'
                    )
                    for attachment in question.attachments:
                        attachment_href = escape(
                            attachment.object_id, quote=True
                        )
                        body.append(
                            '<div class="answer-attachment-item">'
                            f'<a class="answer-attachment" '
                            f'href="exam-attachment:{attachment_href}" '
                            f'title="点击下载 {escape(attachment.filename, quote=True)}">'
                            f'{escape(attachment.filename)}</a>'
                        )
                        if attachment.file_size:
                            body.append(
                                f' <span class="answer-attachment-size">'
                                f'{escape(attachment.file_size)}</span>'
                            )
                        body.append('</div>')
                    body.append('</td></tr>')
                if question.correct_answer_html:
                    body.append(
                        '<tr>'
                        '<td class="answer-icon-cell" width="32">'
                        f'<img class="answer-check-icon" src="{correct_uri}" '
                        'width="20" height="20" align="middle"/></td>'
                        '<td class="answer-content correct-answer" colspan="2">'
                        '<b>正确答案：</b>&nbsp;'
                        f'{question.correct_answer_html}</td>'
                        '</tr>'
                    )
                if question.explanation_html:
                    body.append(
                        '<tr>'
                        '<td class="answer-icon-cell" width="32">'
                        f'<img class="explanation-icon" src="{explanation_uri}" '
                        'width="20" height="20" align="middle"/></td>'
                        '<td class="answer-content answer-explanation" colspan="2">'
                        '<b>答案解析：</b>&nbsp;'
                        f'{question.explanation_html}</td>'
                        '</tr>'
                    )
                body.append('</table>')
                body.append("</div>")
                body.append("</td></tr></table>")

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
            .question-card {{
                border-collapse: collapse;
                margin: 0 0 28px;
                width: 100%;
            }}
            .question-surface {{
                background-color: {palette.panel_alt_bg};
                border: 1px solid {palette.border_strong};
                border-radius: 4px;
                padding: 10px 12px;
            }}
            .question-card-alternate .question-surface {{
                background-color: {palette.card_bg};
            }}
            .stem-panel {{
                margin: 0;
                padding: 4px 0 8px;
            }}
            .choices {{
                margin-top: 10px;
            }}
            .choices div {{
                margin: 6px 0 6px 28px;
            }}
            .question-prefix {{
                color: {palette.text_muted};
                font-size: 14pt;
                font-weight: normal;
                margin-right: 4px;
            }}
            .answer-details {{
                margin: 0;
                padding: 8px 0 4px;
            }}
            .answer-divider {{
                background-color: {palette.border_strong};
                border: none;
                height: 1px;
                margin: 0 0 8px;
            }}
            .answer-details-table {{
                border-collapse: collapse;
                margin: 0;
                width: 100%;
            }}
            .answer-details-table td {{
                border: none;
                padding: 1px 8px;
                vertical-align: middle;
            }}
            .answer-details-table .answer-icon-cell {{
                padding-left: 0;
            }}
            .answer-icon-cell {{ white-space: nowrap; }}
            .answer-content {{ font-size: 14pt; }}
            .subjective-answer {{
                padding: 4px 8px 4px 40px;
                vertical-align: top;
            }}
            .answer-attachments {{
                padding: 2px 8px 4px 40px !important;
                vertical-align: top !important;
            }}
            .answer-attachment-item {{
                line-height: 1.5;
            }}
            .answer-attachment {{
                color: {palette.accent};
                text-decoration: none;
            }}
            .answer-attachment:hover {{
                text-decoration: underline;
            }}
            .answer-attachment-size {{
                color: {palette.text_muted};
                font-size: 11pt;
            }}
            .student-answer-correct {{ color: {palette.success}; }}
            .student-answer-incorrect {{ color: {palette.danger}; }}
            .answer-score {{
                text-align: right;
                white-space: nowrap;
            }}
            .score-label {{ font-size: 14pt; }}
            .score-value {{
                background-color: transparent;
                border: 1px solid {palette.border};
                border-radius: 4px;
                color: {palette.text_secondary};
                display: inline-block;
                font-size: 14pt;
                min-width: 52px;
                padding: 3px 10px;
                text-align: center;
            }}
            .score-value-correct {{
                border-color: {palette.success};
                color: {palette.success};
            }}
            .score-value-editable {{
                border-style: dashed;
                border-color: {palette.accent};
                color: {palette.accent};
                text-decoration: none;
            }}
            .score-value-editable:hover {{
                background-color: {palette.hover_bg};
            }}
            .score-value-incorrect {{
                border-color: {palette.danger};
                color: {palette.danger};
            }}
            .score-check {{
                color: {palette.success};
                font-size: 22pt;
                font-weight: bold;
                padding-left: 8px;
            }}
            .score-cross {{
                color: {palette.danger};
                font-size: 22pt;
                font-weight: bold;
                padding-left: 8px;
            }}
            .stem p, .answer p, .reference p {{ margin: 4px 0; }}
            .correct-answer {{
                color: {palette.success};
            }}
            .answer-explanation {{
                color: {palette.text_secondary};
            }}
            table {{ border-collapse: collapse; }}
            td, th {{ border: 1px solid {palette.border}; padding: 4px; }}
        </style></head><body>{''.join(body)}</body></html>"""

    @staticmethod
    def _svg_data_uri(svg):
        return "data:image/svg+xml;base64," + base64.b64encode(
            svg.encode("utf-8")
        ).decode("ascii")

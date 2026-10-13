from PyQt6.QtCore import QByteArray, QEvent, QSettings, QThread, QTimer, Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QComboBox, QGridLayout,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem,
    QMessageBox, QToolButton, QSizePolicy, QVBoxLayout, QWidget,
)
from threading import Event

from core.apis.exam_api import (
    ExamReviewContext, exam_mark_paper_referer,
    exam_question_mark_referer, fetch_exam_mark_paper,
    fetch_exam_question_mark_paper, fetch_exam_review_page,
    fetch_exam_review_questions, next_exam_question_mark_url,
    skip_exam_question_answer,
)
from core.services.exam_ai_bulk_grading_service import ExamAIBulkGradingService
from core.services.exam_ai_scoring_service import ExamAIScoringService
from core.utils.exam_ai_grading_jobs import ExamAIGradingJobStore
from core.utils.exam_score_drafts import ExamScoreDraftStore
from core.utils.exam_mark_paper_parser import (
    parse_exam_mark_paper, parse_exam_question_mark_paper,
)
from ui.dialogs.exam_answer_dialog import ExamAnswerDialog
from ui.dialogs.exam_ai_grading_records_dialog import ExamAIGradingRecordsDialog
from ui.theme import (
    apply_theme_stylesheet, bind_theme_tree, get_theme_palette, theme_manager,
)

class ExamReviewLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(
        self, session, context, state, page_num, page_size, request_id, parent=None
    ):
        super().__init__(parent)
        self.session = session
        self.context = context
        self.state = state
        self.page_num = page_num
        self.page_size = page_size
        self.request_id = request_id

    def run(self):
        try:
            page = fetch_exam_review_page(
                self.session,
                self.context,
                self.state,
                page_num=self.page_num,
                page_size=self.page_size,
            )
            self.loaded.emit(self.request_id, page)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class ExamQuestionLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, session, context, request_id, parent=None):
        super().__init__(parent)
        self.session = session
        self.context = context
        self.request_id = request_id

    def run(self):
        try:
            questions = fetch_exam_review_questions(self.session, self.context)
            self.loaded.emit(self.request_id, questions)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class MarkPaperWorker(QThread):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, session, context, record_id, parent=None):
        super().__init__(parent)
        self.session = session
        self.context = context
        self.record_id = str(record_id)

    def run(self):
        try:
            html = fetch_exam_mark_paper(
                self.session, self.context, self.record_id
            )
            content = parse_exam_mark_paper(
                html,
                referer=exam_mark_paper_referer(
                    self.context, self.record_id
                ),
            )
            self.loaded.emit(self.record_id, content)
        except Exception as exc:
            self.failed.emit(self.record_id, str(exc))


class ExamAIBulkGradingWorker(QThread):
    progress = pyqtSignal(int, int, object)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service, answer_ids=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.answer_ids = answer_ids
        self._stop_event = Event()

    def request_stop(self):
        self._stop_event.set()

    def run(self):
        try:
            result = self.service.run(
                progress_callback=lambda current, total, outcome: (
                    self.progress.emit(current, total, outcome)
                ),
                stop_requested=self._stop_event.is_set,
                answer_ids=self.answer_ids,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class QuestionMarkPaperWorker(QThread):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, session, context, question_id, mark_url, parent=None):
        super().__init__(parent)
        self.session = session
        self.context = context
        self.question_id = str(question_id)
        self.mark_url = mark_url

    def run(self):
        try:
            html = fetch_exam_question_mark_paper(
                self.session, self.context, self.mark_url
            )
            page = parse_exam_question_mark_paper(
                html, referer=self.mark_url
            )
            self.loaded.emit(self.question_id, page)
        except Exception as exc:
            self.failed.emit(self.question_id, str(exc))


class QuestionAnswerAdvanceWorker(QThread):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)
    skip_succeeded = pyqtSignal(str)

    def __init__(
        self, session, context, question_id, mark_url, answer_id,
        skip_current=False, parent=None,
    ):
        super().__init__(parent)
        self.session = session
        self.context = context
        self.question_id = str(question_id)
        self.mark_url = mark_url
        self.answer_id = str(answer_id or "")
        self.skip_current = bool(skip_current)

    def run(self):
        try:
            current_answer_referer = exam_question_mark_referer(
                self.mark_url, self.answer_id
            )
            if self.skip_current:
                skip_exam_question_answer(
                    self.session,
                    self.context,
                    self.mark_url,
                    self.answer_id,
                    referer=current_answer_referer,
                )
                self.skip_succeeded.emit(self.question_id)
            next_url = next_exam_question_mark_url(self.mark_url)
            page_referer = (
                current_answer_referer
                if self.skip_current else self.mark_url
            )
            html = fetch_exam_question_mark_paper(
                self.session,
                self.context,
                next_url,
                referer=page_referer,
            )
            page = parse_exam_question_mark_paper(
                html, referer=page_referer
            )
            self.loaded.emit(self.question_id, page)
        except Exception as exc:
            self.failed.emit(self.question_id, str(exc))


class ContentWidthComboBox(QComboBox):
    def showPopup(self):
        self.view().setFixedWidth(self.width())
        super().showPopup()


class ExamReviewView(QWidget):
    back_requested = pyqtSignal()
    PAGE_SIZE_OPTIONS = (20, 50, 100)
    PAGE_SIZE_SETTINGS_PREFIX = "exam_review/page_size"

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.context = None
        self.mode = "person"
        self.state = 1
        self.page_num = 1
        self.page_size = 20
        self.total_pages = 0
        self._request_id = 0
        self._workers = []
        self._question_workers = []
        self._question_markpaper_workers = []
        self._question_advance_workers = []
        self._question_advance_dialogs = {}
        self._question_mark_urls = {}
        self._markpaper_workers = []
        self._active_answer_dialog = None
        self._bulk_grading_worker = None
        self._ai_grading_job_store = ExamAIGradingJobStore()
        self._state_totals = {0: None, 1: None}
        self._setup_ui()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_bulk_grading_for_shutdown)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.back_button = QPushButton("返回考试列表")
        self.back_button.setObjectName("review_back_button")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button)

        self.title_label = QLabel("考试批阅")
        self.title_label.setObjectName("review_title")
        header.addWidget(self.title_label, 1)
        layout.addLayout(header)

        mode_row = QHBoxLayout()
        self.person_mode_button = QPushButton("按人批阅")
        self.question_mode_button = QPushButton("按题批阅")
        self.person_mode_button.setObjectName("review_mode_button")
        self.question_mode_button.setObjectName("review_mode_button")
        for button in (self.person_mode_button, self.question_mode_button):
            button.setCheckable(True)
            button.setMinimumHeight(34)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.person_mode_button, 0)
        self.mode_group.addButton(self.question_mode_button, 1)
        self.person_mode_button.setChecked(True)
        self.person_mode_button.clicked.connect(self._show_person_mode)
        self.question_mode_button.clicked.connect(self._show_question_mode)
        mode_row.addWidget(self.person_mode_button)
        mode_row.addWidget(self.question_mode_button)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.person_panel = QWidget()
        person_layout = QVBoxLayout(self.person_panel)
        person_layout.setContentsMargins(0, 0, 0, 0)
        person_layout.setSpacing(10)

        filter_row = QHBoxLayout()
        self.submitted_button = QPushButton("已交")
        self.unsubmitted_button = QPushButton("未交")
        for button in (self.submitted_button, self.unsubmitted_button):
            button.setObjectName("review_filter_button")
            button.setCheckable(True)
            button.setMinimumHeight(30)
        self.state_group = QButtonGroup(self)
        self.state_group.setExclusive(True)
        self.state_group.addButton(self.unsubmitted_button, 0)
        self.state_group.addButton(self.submitted_button, 1)
        self.submitted_button.setChecked(True)
        self.submitted_button.clicked.connect(lambda: self._select_state(1))
        self.unsubmitted_button.clicked.connect(lambda: self._select_state(0))
        filter_row.addWidget(self.submitted_button)
        filter_row.addWidget(self.unsubmitted_button)
        filter_row.addStretch()
        self.student_search_input = QLineEdit()
        self.student_search_input.setPlaceholderText("搜索姓名或学号")
        self.student_search_input.setClearButtonEnabled(True)
        self.student_search_input.setFixedWidth(220)
        self.student_search_input.setToolTip("筛选当前页的姓名或学号，支持输入部分内容")
        self.student_search_input.textChanged.connect(
            self._filter_current_page_records
        )
        filter_row.addWidget(self.student_search_input)
        filter_row.addWidget(QLabel("每页"))
        self.page_size_combo = ContentWidthComboBox()
        self.page_size_combo.addItems(
            [str(size) for size in self.PAGE_SIZE_OPTIONS]
        )
        self.page_size_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        size_policy = self.page_size_combo.sizePolicy()
        size_policy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
        self.page_size_combo.setSizePolicy(size_policy)
        self.page_size_combo.currentTextChanged.connect(
            self._on_page_size_changed
        )
        filter_row.addWidget(self.page_size_combo)
        filter_row.addWidget(QLabel("份"))
        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("review_refresh_button")
        self.refresh_button.setFixedSize(32, 30)
        self.refresh_button.setIconSize(QSize(18, 18))
        self.refresh_button.setAutoRaise(True)
        self.refresh_button.setToolTip("刷新当前批阅列表")
        self.refresh_button.setAccessibleName("刷新当前批阅列表")
        self.refresh_button.clicked.connect(self._refresh_current_page)
        filter_row.addWidget(self.refresh_button)
        person_layout.addLayout(filter_row)

        self.status_label = QLabel("等待加载")
        self.status_label.setObjectName("review_status")
        person_layout.addWidget(self.status_label)

        self.records_table = QTableWidget(0, 8)
        self.records_table.setHorizontalHeaderLabels(
            [
                "姓名", "学号/账号", "状态", "提交时间", "考试用时",
                "提交IP", "成绩", "操作",
            ]
        )
        self.records_table.verticalHeader().setVisible(False)
        self.records_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.records_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.records_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.records_table.setWordWrap(True)
        self.records_table.setAlternatingRowColors(True)
        self.records_table.viewport().installEventFilter(self)
        review_header = self.records_table.horizontalHeader()
        review_header.setStretchLastSection(False)
        review_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._resize_record_columns()
        person_layout.addWidget(self.records_table, 1)

        page_row = QGridLayout()
        page_row.setColumnStretch(1, 1)
        side_gutter = QWidget()
        side_gutter.setFixedWidth(88)
        page_row.addWidget(side_gutter, 0, 0)
        page_controls = QWidget()
        page_controls_layout = QHBoxLayout(page_controls)
        page_controls_layout.setContentsMargins(0, 0, 0, 0)
        page_controls_layout.setSpacing(6)
        self.previous_button = QPushButton("上一页")
        self.previous_button.clicked.connect(self._previous_page)
        self.page_label = QLabel("第 0 / 0 页")
        self.page_label.setMinimumWidth(110)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self._next_page)
        page_controls_layout.addWidget(self.previous_button)
        page_controls_layout.addWidget(self.page_label)
        page_controls_layout.addWidget(self.next_button)
        page_row.addWidget(page_controls, 0, 1, Qt.AlignmentFlag.AlignCenter)
        action_buttons = QWidget()
        action_buttons_layout = QHBoxLayout(action_buttons)
        action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        action_buttons_layout.setSpacing(6)
        self.grading_records_button = QPushButton("批改记录")
        self.grading_records_button.clicked.connect(
            self._open_ai_grading_records
        )
        self.grading_records_button.hide()
        action_buttons_layout.addWidget(self.grading_records_button)
        self.ai_grade_button = QPushButton("AI改卷")
        self.ai_grade_button.setObjectName("review_ai_grade_button")
        self.ai_grade_button.setMinimumSize(104, 38)
        self.ai_grade_button.setToolTip(
            "批改本场考试全部已交答卷中的主观题，完成后自动提交"
        )
        self.ai_grade_button.clicked.connect(self._toggle_ai_bulk_grading)
        action_buttons_layout.addWidget(self.ai_grade_button)
        page_row.addWidget(
            action_buttons, 0, 2, Qt.AlignmentFlag.AlignRight
        )
        person_layout.addLayout(page_row)
        layout.addWidget(self.person_panel, 1)

        self.question_panel = QWidget()
        question_layout = QVBoxLayout(self.question_panel)
        question_toolbar = QHBoxLayout()
        self.question_status_label = QLabel("按题批阅列表尚未加载")
        self.question_status_label.setObjectName("review_status")
        question_toolbar.addWidget(self.question_status_label, 1)
        self.question_refresh_button = QToolButton()
        self.question_refresh_button.setObjectName("review_refresh_button")
        self.question_refresh_button.setFixedSize(32, 30)
        self.question_refresh_button.setIconSize(QSize(18, 18))
        self.question_refresh_button.setAutoRaise(True)
        self.question_refresh_button.setToolTip("刷新按题批阅列表")
        self.question_refresh_button.setAccessibleName("刷新按题批阅列表")
        self.question_refresh_button.clicked.connect(self._load_questions)
        question_toolbar.addWidget(self.question_refresh_button)
        question_layout.addLayout(question_toolbar)

        self.questions_table = QTableWidget(0, 5)
        self.questions_table.setHorizontalHeaderLabels(
            ["题型", "题号", "题目内容", "满分", "操作"]
        )
        self.questions_table.verticalHeader().setVisible(False)
        self.questions_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.questions_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.questions_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.questions_table.setWordWrap(True)
        self.questions_table.setAlternatingRowColors(True)
        question_header = self.questions_table.horizontalHeader()
        question_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        question_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.questions_table.setColumnWidth(0, 120)
        self.questions_table.setColumnWidth(1, 64)
        self.questions_table.setColumnWidth(3, 64)
        self.questions_table.setColumnWidth(4, 88)
        question_layout.addWidget(self.questions_table, 1)
        self.question_panel.hide()
        layout.addWidget(self.question_panel, 1)

        apply_theme_stylesheet(self, lambda palette: f"""
            QWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QLabel#review_title {{
                color: {palette.text};
                font-size: 18px;
                font-weight: bold;
            }}
            QLabel#review_status {{
                color: {palette.text_muted};
            }}
            QLabel#review_placeholder {{
                color: {palette.text_muted};
                font-size: 15px;
            }}
            QComboBox {{
                background-color: {palette.input_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 5px 4px;
            }}
            QComboBox:hover, QComboBox:focus {{
                border-color: {palette.accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QTableWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                gridline-color: {palette.border};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QTableWidget::item {{
                padding: 5px;
            }}
            QTableWidget::item:alternate {{
                background-color: {palette.panel_alt_bg};
            }}
            QTableWidget::item:selected,
            QTableWidget::item:alternate:selected {{
                background-color: {palette.accent};
                color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: none;
                border-bottom: 1px solid {palette.border};
                padding: 7px;
            }}
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text_secondary};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                border-color: {palette.accent};
                color: {palette.text};
            }}
            QPushButton#review_mark_button {{
                background-color: {palette.accent};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 13px;
            }}
            QPushButton#review_mark_button:hover {{
                background-color: {palette.accent_hover};
                color: #ffffff;
            }}
            QPushButton#review_mark_button:disabled {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
                border: 1px solid {palette.border};
            }}
            QPushButton#review_ai_grade_button {{
                background-color: {palette.accent};
                color: #ffffff;
                border: 1px solid {palette.accent};
                border-radius: 4px;
                padding: 7px 16px;
                font-weight: bold;
            }}
            QPushButton#review_ai_grade_button:hover {{
                background-color: {palette.accent_hover};
                border-color: {palette.accent_hover};
                color: #ffffff;
            }}
            QPushButton#review_ai_grade_button:pressed {{
                background-color: {palette.accent_focus};
                border-color: {palette.accent_focus};
            }}
            QPushButton#review_ai_grade_button:disabled {{
                background-color: {palette.disabled_bg};
                border-color: {palette.border};
                color: {palette.disabled_text};
            }}
            QPushButton:checked {{
                background-color: {palette.accent};
                border-color: {palette.accent};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
                border-color: {palette.border};
            }}
        """)
        bind_theme_tree(self)
        theme_manager().theme_changed.connect(self._apply_runtime_theme)
        self._apply_runtime_theme(theme_manager().mode)

    def _build_refresh_icon(self, mode=None):
        color = get_theme_palette(mode).text_secondary
        svg = f"""
        <svg width="24" height="24" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
            <path d="M934.4 206.933333c-17.066667-4.266667-34.133333 6.4-38.4 23.466667l-23.466667 87.466667C797.866667 183.466667 654.933333 96 497.066667 96 264.533333 96 74.666667 281.6 74.666667 512s189.866667 416 422.4 416c179.2 0 339.2-110.933333 398.933333-275.2 6.4-17.066667-2.133333-34.133333-19.2-40.533333-17.066667-6.4-34.133333 2.133333-40.533333 19.2-51.2 138.666667-187.733333 232.533333-339.2 232.533333C298.666667 864 138.666667 706.133333 138.666667 512S300.8 160 497.066667 160c145.066667 0 277.333333 87.466667 330.666666 217.6l-128-36.266667c-17.066667-4.266667-34.133333 6.4-38.4 23.466667-4.266667 17.066667 6.4 34.133333 23.466667 38.4l185.6 49.066667c2.133333 0 6.4 2.133333 8.533333 2.133333 6.4 0 10.666667-2.133333 17.066667-4.266667 6.4-4.266667 12.8-10.666667 14.933333-19.2l49.066667-185.6c0-17.066667-8.533333-34.133333-25.6-38.4z" fill="{color}"/>
        </svg>
        """
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _apply_runtime_theme(self, mode):
        self.refresh_button.setIcon(self._build_refresh_icon(mode))
        self.question_refresh_button.setIcon(self._build_refresh_icon(mode))
        self._fit_page_size_combo()

    def _fit_page_size_combo(self):
        self.page_size_combo.setFixedWidth(self.page_size_combo.sizeHint().width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_record_columns)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_page_size_combo)
        QTimer.singleShot(0, self._resize_record_columns)

    def eventFilter(self, watched, event):
        if (
            hasattr(self, "records_table")
            and watched is self.records_table.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._resize_record_columns)
        return super().eventFilter(watched, event)

    def _resize_record_columns(self):
        if not hasattr(self, "records_table"):
            return

        available_width = self.records_table.viewport().width()
        if available_width <= 0:
            available_width = self.records_table.width()

        min_widths = (145, 120, 75, 135, 95, 130, 72, 88)
        if available_width < sum(min_widths):
            widths = min_widths
        else:
            extra_width = available_width - sum(min_widths)
            weights = (0.22, 0.15, 0.08, 0.15, 0.10, 0.15, 0.07, 0.08)
            widths = [
                base + int(extra_width * weight)
                for base, weight in zip(min_widths, weights)
            ]
            widths[0] += available_width - sum(widths)

        for column, width in enumerate(widths):
            self.records_table.setColumnWidth(column, width)

    def open_exam(self, context: ExamReviewContext):
        self.context = context
        self.title_label.setText(context.exam_title or "考试批阅")
        self.title_label.setToolTip(context.exam_title)
        self.state = 1
        self.page_num = 1
        self.total_pages = 0
        self._state_totals = {0: None, 1: None}
        self._restore_page_size()
        self._update_state_labels()
        self._refresh_ai_grading_records_button()
        self.person_mode_button.setChecked(True)
        self.question_mode_button.setChecked(False)
        self.mode = "person"
        self.person_panel.show()
        self.question_panel.hide()
        self._load_page(1)

    def _show_person_mode(self):
        self.mode = "person"
        self.person_panel.show()
        self.question_panel.hide()
        self._load_page(1)

    def _show_question_mode(self):
        self.mode = "question"
        self._request_id += 1
        self.person_panel.hide()
        self.question_panel.show()
        self._load_questions()

    def _load_questions(self):
        if self.context is None or self.crawler is None:
            return
        self._request_id += 1
        request_id = self._request_id
        self.questions_table.setRowCount(0)
        self.question_refresh_button.setEnabled(False)
        self.question_status_label.setText("正在加载按题批阅列表…")

        worker = ExamQuestionLoadWorker(
            self.crawler.session, self.context, request_id, self
        )
        self._question_workers.append(worker)
        worker.loaded.connect(self._on_questions_loaded)
        worker.failed.connect(self._on_questions_failed)
        worker.finished.connect(self._on_question_worker_finished)
        worker.start()

    def _on_questions_loaded(self, request_id, questions):
        if request_id != self._request_id or self.mode != "question":
            return
        self._question_mark_urls = {
            str(question.get("question_id") or ""): question.get("mark_url", "")
            for question in questions
        }
        self.questions_table.setRowCount(len(questions))
        for row, question in enumerate(questions):
            values = (
                question.get("question_type", ""),
                question.get("number", ""),
                question.get("content", ""),
                question.get("maximum_score", ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value) if value not in (None, "") else "---")
                item.setToolTip(item.text())
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (
                        Qt.AlignmentFlag.AlignLeft
                        if column in (0, 2)
                        else Qt.AlignmentFlag.AlignCenter
                    )
                )
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        question.get("question_id", ""),
                    )
                self.questions_table.setItem(row, column, item)

            mark_url = question.get("mark_url", "")
            marking_button = QPushButton("批阅")
            marking_button.setObjectName("review_mark_button")
            marking_button.setMinimumHeight(36)
            marking_button.setEnabled(bool(mark_url))
            if mark_url:
                marking_button.setToolTip("在应用内打开该题的批阅页面")
                marking_button.clicked.connect(
                    lambda checked=False, url=mark_url, item=question:
                    self._request_question_mark_paper(item, url)
                )
            else:
                marking_button.setToolTip("接口未返回有效的题目批阅链接")
            self.questions_table.setCellWidget(row, 4, marking_button)
            self.questions_table.setRowHeight(
                row, max(self.questions_table.rowHeight(row), 44)
            )

        self.question_status_label.setText(
            f"共 {len(questions)} 道题" if questions else "暂无题目"
        )

    def _on_questions_failed(self, request_id, message):
        if request_id != self._request_id or self.mode != "question":
            return
        self.question_status_label.setText(f"按题批阅列表加载失败：{message}")

    def _on_question_worker_finished(self):
        worker = self.sender()
        if worker in self._question_workers:
            self._question_workers.remove(worker)
            worker.deleteLater()
        if worker is not None and worker.request_id == self._request_id:
            self.question_refresh_button.setEnabled(True)

    def _request_question_mark_paper(self, question, mark_url):
        question_id = str(question.get("question_id") or "")
        if not question_id or self.context is None or self.crawler is None:
            return
        button = self._find_question_mark_button(question_id)
        if button is None or not button.isEnabled():
            return

        button.setEnabled(False)
        self.question_status_label.setText(
            f"正在加载第 {question.get('number', '')} 题的批阅页面…"
        )
        request_id = self._request_id
        worker = QuestionMarkPaperWorker(
            self.crawler.session,
            self.context,
            question_id,
            mark_url,
            self,
        )
        self._question_markpaper_workers.append(worker)
        worker.loaded.connect(
            lambda loaded_id, page, generation=request_id:
            self._on_question_mark_paper_loaded(
                generation, loaded_id, page
            )
        )
        worker.failed.connect(
            lambda failed_id, message, generation=request_id:
            self._on_question_mark_paper_failed(
                generation, failed_id, message
            )
        )
        worker.finished.connect(self._on_question_mark_paper_worker_finished)
        worker.start()

    def _find_question_mark_button(self, question_id):
        for row in range(self.questions_table.rowCount()):
            item = self.questions_table.item(row, 0)
            if (
                item is not None
                and str(item.data(Qt.ItemDataRole.UserRole)) == str(question_id)
            ):
                button = self.questions_table.cellWidget(row, 4)
                if isinstance(button, QPushButton):
                    return button
        return None

    def _on_question_mark_paper_loaded(self, request_id, question_id, page):
        button = self._find_question_mark_button(question_id)
        if button is not None:
            button.setEnabled(True)
        if request_id != self._request_id or self.mode != "question":
            return

        question_number = ""
        for row in range(self.questions_table.rowCount()):
            item = self.questions_table.item(row, 0)
            if (
                item is not None
                and str(item.data(Qt.ItemDataRole.UserRole)) == str(question_id)
            ):
                number_item = self.questions_table.item(row, 1)
                question_number = number_item.text() if number_item else ""
                break
        self.question_status_label.setText(
            f"已加载第 {question_number} 题，学生："
            f"{page.student_name or page.student_id or '未知'}"
        )
        active_dialog = self._active_answer_dialog
        if (
            active_dialog is not None
            and active_dialog._question_review_mode
        ):
            active_dialog.load_question_page(
                self.context.exam_title, page
            )
            self.question_status_label.setText(
                f"已加载第 {question_number} 题，下一份："
                f"{page.student_name or page.student_id or '未知'}"
            )
            return

        dialog = ExamAnswerDialog(
            self.context.exam_title,
            page.student_name,
            page.student_id,
            page.content,
            self,
            exam_id=self.context.exam_id,
            answer_id=page.answer_id or f"question-{question_id}",
            session=self.crawler.session,
            show_question_navigation=False,
            question_review_mode=True,
            pending_count=page.pending_count,
            submitted_count=page.submitted_count,
        )
        mark_url = self._question_mark_urls.get(str(question_id), "")
        answer_id = page.answer_id or f"question-{question_id}"
        if not page.answer_id:
            dialog.skip_button.setEnabled(False)
            dialog.skip_button.setToolTip("当前答卷缺少 answerid，无法跳过")
        self._active_answer_dialog = dialog
        dialog.finished.connect(
            lambda _result, answer_dialog=dialog:
            self._release_answer_dialog(answer_dialog)
        )
        dialog.next_requested.connect(
            lambda qid=str(question_id), url=mark_url, aid=answer_id:
            self._request_next_question_answer(
                qid, url, aid, dialog=dialog
            )
        )
        dialog.skip_requested.connect(
            lambda qid=str(question_id), url=mark_url, aid=answer_id,
            answer_dialog=dialog:
            self._request_next_question_answer(
                qid, url, aid, skip_current=True, dialog=answer_dialog
            )
        )
        dialog.finished.connect(self._refresh_after_question_submission)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()

    def _request_next_question_answer(
        self, question_id, mark_url, answer_id, skip_current=False,
        dialog=None,
    ):
        if self.context is None or self.crawler is None or not mark_url:
            if dialog is not None:
                message = "缺少课程上下文或题目链接，无法加载下一份"
                if dialog._skip_pending:
                    dialog._finish_question_skip(False, message)
                else:
                    dialog._finish_question_advance(message)
            self.question_status_label.setText("无法加载下一份：题目链接缺失")
            return
        action = "跳过当前答卷并加载下一份" if skip_current else "正在加载下一份答卷"
        self.question_status_label.setText(action + "…")
        worker = QuestionAnswerAdvanceWorker(
            self.crawler.session,
            self.context,
            question_id,
            mark_url,
            answer_id,
            skip_current=skip_current,
            parent=self,
        )
        worker.loaded.connect(self._on_question_advance_loaded)
        worker.failed.connect(self._on_question_advance_failed)
        worker.skip_succeeded.connect(self._on_question_skip_succeeded)
        worker.finished.connect(self._on_question_advance_worker_finished)
        self._question_advance_workers.append(worker)
        self._question_advance_dialogs[worker] = dialog
        worker.start()

    def _on_question_advance_loaded(self, question_id, page):
        dialog = self._question_advance_dialogs.get(self.sender())
        if self.mode != "question":
            return
        if dialog is None or self._active_answer_dialog is not dialog:
            return
        self._on_question_mark_paper_loaded(
            self._request_id, question_id, page
        )

    def _on_question_advance_failed(self, question_id, message):
        dialog = self._question_advance_dialogs.get(self.sender())
        if dialog is not None and self._active_answer_dialog is dialog:
            if dialog._skip_pending:
                dialog._finish_question_skip(False, message)
            else:
                dialog._finish_question_advance(message)
        self.question_status_label.setText(f"加载下一份失败：{message}")

    def _on_question_skip_succeeded(self, _question_id):
        dialog = self._question_advance_dialogs.get(self.sender())
        if dialog is not None and self._active_answer_dialog is dialog:
            dialog._question_skip_succeeded()

    def _on_question_advance_worker_finished(self):
        worker = self.sender()
        self._question_advance_dialogs.pop(worker, None)
        if worker in self._question_advance_workers:
            self._question_advance_workers.remove(worker)
            worker.deleteLater()

    def _refresh_after_question_submission(self):
        if self.mode == "question":
            self._load_questions()

    def _on_question_mark_paper_failed(self, request_id, question_id, message):
        button = self._find_question_mark_button(question_id)
        if button is not None:
            button.setEnabled(True)
        if request_id != self._request_id or self.mode != "question":
            return
        self.question_status_label.setText(
            f"题目批阅页面请求失败：{message}"
        )

    def _on_question_mark_paper_worker_finished(self):
        worker = self.sender()
        if worker in self._question_markpaper_workers:
            self._question_markpaper_workers.remove(worker)
            worker.deleteLater()

    def _restore_page_size(self):
        settings = QSettings("HaoSoft", "XuexitongManager")
        key = self._page_size_settings_key()
        try:
            page_size = int(settings.value(key, 20))
        except (TypeError, ValueError):
            page_size = 20
        if page_size not in self.PAGE_SIZE_OPTIONS:
            page_size = 20

        self.page_size_combo.blockSignals(True)
        self.page_size_combo.setCurrentText(str(page_size))
        self.page_size_combo.blockSignals(False)
        self.page_size = page_size

    def _page_size_settings_key(self):
        return (
            f"{self.PAGE_SIZE_SETTINGS_PREFIX}/"
            f"{self.context.course_id}/{self.context.class_id}"
        )

    def _on_page_size_changed(self, value):
        try:
            page_size = int(value)
        except (TypeError, ValueError):
            return
        if page_size not in self.PAGE_SIZE_OPTIONS or page_size == self.page_size:
            return

        self.page_size = page_size
        if self.context is None:
            return

        settings = QSettings("HaoSoft", "XuexitongManager")
        settings.setValue(self._page_size_settings_key(), page_size)
        settings.sync()
        self._load_page(1)

    def _select_state(self, state):
        if state == self.state:
            return
        self.state = state
        self.page_num = 1
        self._load_page(1)

    def _load_page(self, page_num):
        if self.context is None:
            return
        self._request_id += 1
        request_id = self._request_id
        self.page_num = page_num
        self.records_table.setRowCount(0)
        self.refresh_button.setEnabled(False)
        self.status_label.show()
        self.status_label.setText(
            "正在加载已交列表..." if self.state == 1 else "正在加载未交列表..."
        )
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)

        worker = ExamReviewLoadWorker(
            self.crawler.session,
            self.context,
            self.state,
            page_num,
            self.page_size,
            request_id,
            self,
        )
        self._workers.append(worker)
        worker.loaded.connect(self._on_page_loaded)
        worker.failed.connect(self._on_page_failed)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_page_loaded(self, request_id, page):
        if request_id != self._request_id or self.mode != "person":
            return
        self.page_num = page.page_num
        self.total_pages = page.total_pages
        self._state_totals[self.state] = page.total
        if self.state == 1:
            self._state_totals[0] = max(0, page.class_size - page.total)
        self._update_state_labels()

        self.records_table.setRowCount(len(page.records))
        for row, record in enumerate(page.records):
            values = (
                record.get("createUserName", ""),
                record.get("loginName", ""),
                record.get("mark", ""),
                record.get("submitTime", "---"),
                record.get("examConsumeTime", "---"),
                record.get("receiveIp", "---") if self.state == 1 else "---",
                record.get("answerScore", "---") if self.state == 1 else "---",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value) if value not in (None, "") else "---")
                item.setData(Qt.ItemDataRole.UserRole, record.get("id"))
                self.records_table.setItem(row, column, item)
                item.setToolTip(item.text())
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (
                        Qt.AlignmentFlag.AlignLeft
                        if column == 0
                        else Qt.AlignmentFlag.AlignCenter
                    )
                )
            record_id = record.get("id")
            marking_button = QPushButton("批阅")
            marking_button.setObjectName("review_mark_button")
            marking_button.setMinimumHeight(36)
            marking_button.setEnabled(self.state == 1 and record_id not in (None, ""))
            if self.state != 1:
                marking_button.setToolTip("未交学生暂无可批阅的答卷")
            elif record_id in (None, ""):
                marking_button.setToolTip("缺少答卷记录 ID，无法打开批阅页面")
            else:
                marking_button.clicked.connect(
                    lambda checked=False, answer_id=record_id: (
                        self._request_mark_paper(answer_id)
                    )
                )
            self.records_table.setCellWidget(row, 7, marking_button)
            self.records_table.setRowHeight(
                row, max(self.records_table.rowHeight(row), 44)
            )

        state_name = "已交" if self.state == 1 else "未交"
        if page.total:
            self.status_label.clear()
            self.status_label.hide()
        else:
            self.status_label.setText(f"暂无{state_name}学生")
            self.status_label.show()
        self.page_label.setText(
            f"第 {self.page_num} / {self.total_pages} 页"
            if self.total_pages else "第 0 / 0 页"
        )
        self.previous_button.setEnabled(self.page_num > 1)
        self.next_button.setEnabled(self.page_num < self.total_pages)
        self._filter_current_page_records()

    def _filter_current_page_records(self):
        query = self.student_search_input.text().strip().casefold()
        match_count = 0
        for row in range(self.records_table.rowCount()):
            matches = not query
            if query:
                matches = any(
                    item is not None and query in item.text().casefold()
                    for column in (0, 1)
                    for item in (self.records_table.item(row, column),)
                )
            self.records_table.setRowHidden(row, not matches)
            match_count += matches

        if not query:
            if self.records_table.rowCount():
                self.status_label.hide()
            return

        self.status_label.show()
        if match_count:
            self.status_label.setText(f"当前页匹配 {match_count} 名学生")
        else:
            self.status_label.setText("当前页没有匹配的姓名或学号")

    def _on_page_failed(self, request_id, message):
        if request_id != self._request_id or self.mode != "person":
            return
        self.status_label.show()
        self.status_label.setText(f"批阅列表加载失败: {message}")

    def _update_state_labels(self):
        submitted = self._state_totals[1]
        unsubmitted = self._state_totals[0]
        self.submitted_button.setText(
            f"已交 ({submitted})" if submitted is not None else "已交"
        )
        self.unsubmitted_button.setText(
            f"未交 ({unsubmitted})" if unsubmitted is not None else "未交"
        )

    def _previous_page(self):
        if self.page_num > 1:
            self._load_page(self.page_num - 1)

    def _next_page(self):
        if self.page_num < self.total_pages:
            self._load_page(self.page_num + 1)

    def _on_worker_finished(self):
        worker = self.sender()
        if worker in self._workers:
            self._workers.remove(worker)
            worker.deleteLater()
        if worker is not None and worker.request_id == self._request_id:
            self.refresh_button.setEnabled(True)

    def _refresh_current_page(self):
        self._load_page(self.page_num or 1)

    def _create_ai_bulk_grading_service(self):
        def rubric_provider(question):
            settings = QSettings("HaoSoft", "XuexitongManager")
            key = ExamAIScoringService.rubric_settings_key(
                self.context.exam_id, question
            )
            return settings.value(key, "", str).strip()

        return ExamAIBulkGradingService(
            self.crawler.session,
            self.context,
            job_store=self._ai_grading_job_store,
            score_draft_store=ExamScoreDraftStore(),
            rubric_provider=rubric_provider,
        )

    def _toggle_ai_bulk_grading(self):
        worker = self._bulk_grading_worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            self.ai_grade_button.setText("正在安全停止…")
            self.ai_grade_button.setEnabled(False)
            return
        self._start_ai_bulk_grading()

    def _start_ai_bulk_grading(self, answer_ids=None):
        if self.context is None or self.crawler is None:
            return

        self.ai_grade_button.setText(
            "停止改卷" if answer_ids is None else "重试中…"
        )
        self.back_button.setEnabled(False)
        self.status_label.show()
        self.status_label.setText("正在读取本场考试已交答卷名单…")
        self._refresh_ai_grading_records_button()
        worker = ExamAIBulkGradingWorker(
            self._create_ai_bulk_grading_service(), answer_ids, self
        )
        worker.progress.connect(self._on_ai_bulk_grading_progress)
        worker.completed.connect(self._on_ai_bulk_grading_completed)
        worker.failed.connect(self._on_ai_bulk_grading_failed)
        worker.finished.connect(worker.deleteLater)
        self._bulk_grading_worker = worker
        worker.start()
        self._refresh_ai_grading_records_button()

    def _on_ai_bulk_grading_progress(self, current, total, outcome):
        name = outcome.get("student_name") or outcome.get("answer_id", "")
        status = ExamAIGradingRecordsDialog.STATUS_LABELS.get(
            outcome.get("status"), outcome.get("status", "处理中")
        )
        self.status_label.show()
        self.status_label.setText(
            f"AI改卷进度：{current}/{total}，{name}：{status}"
        )
        self._refresh_ai_grading_records_button()

    def _on_ai_bulk_grading_completed(self, result):
        self._bulk_grading_worker = None
        self.ai_grade_button.setText("AI改卷")
        self.ai_grade_button.setEnabled(True)
        self.back_button.setEnabled(True)
        outcomes = result.get("outcomes", [])
        try:
            issues = self._ai_grading_job_store.get_exam_issues(
                self.context.exam_id
            )
        except (OSError, ValueError):
            issues = [
                outcome for outcome in outcomes
                if outcome.get("status") in {
                    "grading_failed", "submission_failed",
                }
            ]
        submitted = sum(
            outcome.get("status") == "submitted" for outcome in outcomes
        )
        stopped = result.get("stopped", False)
        summary = (
            f"AI改卷完成：已提交 {submitted} 份，异常 {len(issues)} 份"
        )
        if stopped:
            summary = f"AI改卷已停止；{summary}"
        self.status_label.show()
        self.status_label.setText(summary)
        self._refresh_ai_grading_records_button()
        if issues:
            details = "\n".join(
                f"{item.get('student_name') or item.get('answer_id')}："
                f"{item.get('stage', '')} {item.get('error', '')}".strip()
                for item in issues[:10]
            )
            QMessageBox.warning(
                self,
                "AI改卷有异常",
                summary + "\n\n" + details,
            )
        elif stopped:
            QMessageBox.information(self, "AI改卷已停止", summary)

    def _on_ai_bulk_grading_failed(self, message):
        self._bulk_grading_worker = None
        self.ai_grade_button.setText("AI改卷")
        self.ai_grade_button.setEnabled(True)
        self.back_button.setEnabled(True)
        self.status_label.show()
        self.status_label.setText(f"AI改卷任务启动失败：{message}")
        self._refresh_ai_grading_records_button()
        QMessageBox.warning(self, "AI改卷失败", message)

    def _refresh_ai_grading_records_button(self):
        if self.context is None:
            self.grading_records_button.hide()
            return
        try:
            records = self._ai_grading_job_store.get_exam_visible_records(
                self.context.exam_id
            )
            issue_count = len(
                self._ai_grading_job_store.get_exam_issues(
                    self.context.exam_id
                )
            )
        except (OSError, ValueError) as exc:
            records = []
            issue_count = 0
            self.status_label.show()
            self.status_label.setText(f"批改记录读取失败：{exc}")
        worker_active = (
            self._bulk_grading_worker is not None
            and self._bulk_grading_worker.isRunning()
        )
        self.grading_records_button.setText(
            f"批改记录 ({issue_count})" if issue_count else "批改记录"
        )
        self.grading_records_button.setVisible(bool(records) or worker_active)

    def _open_ai_grading_records(self):
        if self.context is None:
            return
        records = self._ai_grading_job_store.get_exam_visible_records(
            self.context.exam_id
        )
        if not records:
            self._refresh_ai_grading_records_button()
            return
        dialog = ExamAIGradingRecordsDialog(records, self)
        dialog.resolve_requested.connect(self._resolve_ai_grading_issue)
        dialog.retry_requested.connect(self._retry_ai_grading_issue)
        dialog.exec()
        self._refresh_ai_grading_records_button()

    def _resolve_ai_grading_issue(self, answer_id):
        if self.context is None:
            return
        self._ai_grading_job_store.resolve_issue(
            self.context.exam_id, answer_id
        )

    def _retry_ai_grading_issue(self, answer_id):
        self._start_ai_bulk_grading([answer_id])

    def _stop_bulk_grading_for_shutdown(self):
        worker = self._bulk_grading_worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            worker.wait()

    def _request_mark_paper(self, record_id):
        if self.context is None or self.crawler is None:
            return
        button = self._find_mark_paper_button(record_id)
        if button is None or not button.isEnabled():
            return

        button.setEnabled(False)
        self.status_label.show()
        self.status_label.setText("正在请求该学生的批阅页面...")
        request_id = self._request_id
        worker = MarkPaperWorker(
            self.crawler.session, self.context, record_id, self
        )
        self._markpaper_workers.append(worker)
        worker.loaded.connect(
            lambda answer_id, content, generation=request_id: self._on_mark_paper_loaded(
                generation, answer_id, content
            )
        )
        worker.failed.connect(
            lambda answer_id, message, generation=request_id: self._on_mark_paper_failed(
                generation, answer_id, message
            )
        )
        worker.finished.connect(self._on_mark_paper_worker_finished)
        worker.start()

    def _find_mark_paper_button(self, record_id):
        for row in range(self.records_table.rowCount()):
            item = self.records_table.item(row, 0)
            if item is None or str(item.data(Qt.ItemDataRole.UserRole)) != str(record_id):
                continue
            button = self.records_table.cellWidget(row, 7)
            if isinstance(button, QPushButton):
                return button
        return None

    def _on_mark_paper_loaded(self, request_id, record_id, content):
        button = self._find_mark_paper_button(record_id)
        if button is not None:
            button.setEnabled(True)
        if request_id != self._request_id or self.mode != "person":
            return
        row = self._find_mark_paper_row(record_id)
        student_name = ""
        student_id = ""
        if row is not None:
            name_item = self.records_table.item(row, 0)
            id_item = self.records_table.item(row, 1)
            student_name = name_item.text() if name_item is not None else ""
            student_id = id_item.text() if id_item is not None else ""
        self.status_label.show()
        self.status_label.setText(f"已加载 {student_name or student_id} 的答卷（只读）")
        dialog = ExamAnswerDialog(
            self.context.exam_title,
            student_name,
            student_id,
            content,
            self,
            exam_id=self.context.exam_id,
            answer_id=record_id,
            session=self.crawler.session,
        )
        self._active_answer_dialog = dialog
        dialog.finished.connect(
            lambda _result, answer_dialog=dialog:
            self._release_answer_dialog(answer_dialog)
        )
        dialog.submitted.connect(self._refresh_current_page)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()

    def _release_answer_dialog(self, dialog):
        if self._active_answer_dialog is dialog:
            self._active_answer_dialog = None
        dialog.deleteLater()

    def _find_mark_paper_row(self, record_id):
        for row in range(self.records_table.rowCount()):
            item = self.records_table.item(row, 0)
            if item is not None and str(item.data(Qt.ItemDataRole.UserRole)) == str(record_id):
                return row
        return None

    def _on_mark_paper_failed(self, request_id, record_id, message):
        button = self._find_mark_paper_button(record_id)
        if button is not None:
            button.setEnabled(True)
        if request_id != self._request_id:
            return
        self.status_label.show()
        self.status_label.setText(f"批阅页面请求失败：{message}")

    def _on_mark_paper_worker_finished(self):
        worker = self.sender()
        if worker in self._markpaper_workers:
            self._markpaper_workers.remove(worker)
            worker.deleteLater()
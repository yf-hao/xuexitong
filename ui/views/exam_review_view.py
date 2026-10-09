from PyQt6.QtCore import QByteArray, QEvent, QSettings, QThread, QTimer, Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QHeaderView, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QToolButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core.apis.exam_api import ExamReviewContext, fetch_exam_review_page
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
        self._state_totals = {0: None, 1: None}
        self._setup_ui()

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

        self.records_table = QTableWidget(0, 7)
        self.records_table.setHorizontalHeaderLabels(
            ["姓名", "学号/账号", "状态", "提交时间", "考试用时", "提交IP", "成绩"]
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

        page_row = QHBoxLayout()
        page_row.addStretch()
        self.previous_button = QPushButton("上一页")
        self.previous_button.clicked.connect(self._previous_page)
        self.page_label = QLabel("第 0 / 0 页")
        self.page_label.setMinimumWidth(110)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self._next_page)
        page_row.addWidget(self.previous_button)
        page_row.addWidget(self.page_label)
        page_row.addWidget(self.next_button)
        page_row.addStretch()
        person_layout.addLayout(page_row)
        layout.addWidget(self.person_panel, 1)

        self.question_panel = QWidget()
        question_layout = QVBoxLayout(self.question_panel)
        question_layout.addStretch()
        self.question_placeholder = QLabel("按题批阅界面已预留，接口暂未接入")
        self.question_placeholder.setObjectName("review_placeholder")
        self.question_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        question_layout.addWidget(self.question_placeholder)
        question_layout.addStretch()
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

        min_widths = (150, 130, 80, 145, 100, 150, 80)
        if available_width < sum(min_widths):
            widths = min_widths
        else:
            extra_width = available_width - sum(min_widths)
            weights = (0.24, 0.16, 0.08, 0.17, 0.10, 0.17, 0.08)
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
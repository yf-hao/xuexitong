"""签到详情对话框。"""
from datetime import datetime
from PyQt6.QtCore import QByteArray, QEvent, QSize, QSettings, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QHeaderView, QRadioButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget
)
from models.attendance_record import AttendanceDetail
from models.activity import Activity
from ui.theme import apply_theme_stylesheet, bind_theme_tree, get_theme_palette, theme_manager
from ui.workers import AttendanceStatusUpdateWorker


class AttendanceStatusEditDialog(QDialog):
    """签到状态修改对话框。"""

    NAME_COLUMN_FONT_SIZE_KEY = "attendance_detail/name_column_font_size"
    NAME_COLUMN_FONT_SIZE = 72
    NAME_COLUMN_FONT_SIZE_MIN = 36
    NAME_COLUMN_MIN_WIDTH = 340
    STATUS_OPTIONS = [
        ("1", "已签", 1),
        ("2", "缺勤", 5),
        ("3", "迟到", 9),
        ("4", "早退", 10),
        ("5", "事假", 8),
        ("6", "病假", 7),
        ("7", "公假", 12),
    ]

    def __init__(self, record, crawler=None, active_id="", source_tab_key="", source_records_provider=None, parent=None):
        super().__init__(parent)
        self.record = record
        self.crawler = crawler
        self.active_id = str(active_id or "")
        self.source_tab_key = str(source_tab_key or "")
        self.source_records_provider = source_records_provider
        self.settings = QSettings("HaoSoft", "XuexitongManager")
        self._app = QApplication.instance()
        self._shift_pressed = False
        self._status_worker = None
        self._submit_mode = ""
        self.button_group = QButtonGroup(self)
        self.shortcut_buttons = {}
        self._load_name_column_font_size()
        self.setup_ui()
        if self._app is not None:
            self._app.installEventFilter(self)

    def setup_ui(self):
        self.setWindowTitle(f"修改签到状态 - {self.record.name}")
        self.setModal(True)
        apply_theme_stylesheet(self, """
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #e0e0e0; }
            QRadioButton { color: #e0e0e0; spacing: 8px; padding: 4px 0; }
            QRadioButton::indicator { width: 14px; height: 14px; }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #005a9e; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.name_column = QWidget()
        self.name_column.setMinimumWidth(self.NAME_COLUMN_MIN_WIDTH)
        apply_theme_stylesheet(self.name_column, """
            QWidget {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-weight: bold;
                padding: 24px;
            }
        """)
        name_column_layout = QVBoxLayout(self.name_column)
        name_column_layout.setContentsMargins(0, 0, 0, 0)
        self.name_zoom_btn = QPushButton("", self.name_column)
        self.name_zoom_btn.setFixedSize(34, 34)
        self.name_zoom_btn.setToolTip("点击放大，按住 Shift 点击缩小")
        apply_theme_stylesheet(self.name_zoom_btn, """
            QPushButton {
                padding: 0;
                border-radius: 17px;
                background-color: rgba(0, 122, 204, 220);
            }
            QPushButton:hover {
                background-color: rgba(0, 90, 158, 235);
            }
        """)
        self.name_zoom_btn.clicked.connect(self._adjust_name_font_size)
        self.name_column_label = QLabel("")
        self.name_column_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_column_label.setWordWrap(True)
        name_column_layout.addWidget(self.name_column_label)
        layout.addWidget(self.name_column)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.info_label = QLabel(f"<b>当前状态：</b>{self.record.status_name}")
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.info_label)

        for key, text, status in self.STATUS_OPTIONS:
            radio = QRadioButton(f"{key}. {text}")
            self.button_group.addButton(radio, status)
            self.shortcut_buttons[key] = radio
            if status == self.record.status:
                radio.setChecked(True)
            right_layout.addWidget(radio)

        checked = self.button_group.checkedButton()
        if checked is None and self.shortcut_buttons:
            self.shortcut_buttons["1"].setChecked(True)

        hint_label = QLabel("快捷键：1-7 选择状态，Enter 确认")
        apply_theme_stylesheet(hint_label, "color: #aaaaaa; font-size: 12px;")
        right_layout.addWidget(hint_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.next_btn = QPushButton("下一个")
        self.next_btn.setFixedWidth(100)
        self.next_btn.clicked.connect(self._handle_next_clicked)
        btn_layout.addWidget(self.next_btn)
        self.next_shortcut = QShortcut(QKeySequence("N"), self)
        self.next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.next_shortcut.activated.connect(self._handle_next_clicked)
        self.zoom_in_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomIn), self)
        self.zoom_in_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.zoom_in_shortcut.activated.connect(self._zoom_in_name_column)
        self.zoom_out_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomOut), self)
        self.zoom_out_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.zoom_out_shortcut.activated.connect(self._zoom_out_name_column)

        ok_btn = QPushButton("确定")
        self.ok_btn = ok_btn
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._handle_accept_clicked)
        btn_layout.addWidget(ok_btn)
        right_layout.addLayout(btn_layout)
        layout.addWidget(right_panel, stretch=1)

        self._update_name_column_appearance()
        self._update_zoom_button_icon()
        self._apply_name_column_visibility()
        self._update_navigation_state()
        bind_theme_tree(self)
        theme_manager().theme_changed.connect(self._apply_runtime_theme)
        self._apply_runtime_theme(theme_manager().mode)

    @property
    def selected_status(self) -> int:
        return self.button_group.checkedId()

    def _apply_name_column_visibility(self):
        self.name_column.setVisible(True)
        column_width = self._current_name_column_width()
        self.name_column.setMinimumWidth(column_width)
        self.resize(420 + column_width, 360)
        self._position_name_zoom_button()
        self._update_navigation_state()

    def _adjust_name_font_size(self):
        AttendanceStatusEditDialog._change_name_font_size(self, -6 if self._is_shift_pressed() else 6)

    def _zoom_in_name_column(self):
        AttendanceStatusEditDialog._change_name_font_size(self, 6)

    def _zoom_out_name_column(self):
        AttendanceStatusEditDialog._change_name_font_size(self, -6)

    def _change_name_font_size(self, delta: int):
        if int(delta) < 0:
            self.__class__.NAME_COLUMN_FONT_SIZE = max(
                self.NAME_COLUMN_FONT_SIZE_MIN,
                self.__class__.NAME_COLUMN_FONT_SIZE + int(delta),
            )
        else:
            self.__class__.NAME_COLUMN_FONT_SIZE = self.__class__.NAME_COLUMN_FONT_SIZE + int(delta)
        self._save_name_column_font_size()
        self._update_name_column_appearance()
        self._update_zoom_button_icon()
        self._apply_name_column_visibility()

    def _update_name_column_appearance(self):
        palette = get_theme_palette()
        username_size = max(24, int(self.__class__.NAME_COLUMN_FONT_SIZE * 0.5))
        username_text = str(self.record.username or "")
        self.name_column_label.setText(
            f"<div style='text-align:center;'>"
            f"<div style='color:{palette.text}; font-size:{int(self.__class__.NAME_COLUMN_FONT_SIZE)}px; font-weight:bold;'>{self.record.name}</div>"
            f"<div style='color:{palette.text_muted}; font-size:{username_size}px; margin-top:8px;'>{username_text}</div>"
            f"</div>"
        )
        self.name_column_label.setStyleSheet("padding: 24px;")
        self._update_info_label()

    def _update_info_label(self):
        if not hasattr(self, "info_label"):
            return
        palette = get_theme_palette()
        self.info_label.setText(
            f"<span style='color:{palette.accent}; font-weight:bold;'>当前状态：</span>"
            f"<span style='color:{palette.text};'>{self.record.status_name}</span>"
        )

    def _apply_runtime_theme(self, _mode: str):
        self._update_name_column_appearance()

    def _current_name_column_width(self) -> int:
        font = QFont(self.name_column_label.font())
        font.setPixelSize(int(self.__class__.NAME_COLUMN_FONT_SIZE))
        name_metrics = QFontMetrics(font)
        name_width = name_metrics.horizontalAdvance(str(self.record.name or ""))
        username_font = QFont(self.name_column_label.font())
        username_font.setPixelSize(max(24, int(self.__class__.NAME_COLUMN_FONT_SIZE * 0.5)))
        username_width = QFontMetrics(username_font).horizontalAdvance(str(self.record.username or ""))
        return max(self.NAME_COLUMN_MIN_WIDTH, max(name_width, username_width) + 96)

    def _position_name_zoom_button(self):
        if not hasattr(self, "name_zoom_btn") or not hasattr(self, "name_column"):
            return
        margin = 10
        x = max(margin, self.name_column.width() - self.name_zoom_btn.width() - margin)
        self.name_zoom_btn.move(x, margin)
        self.name_zoom_btn.raise_()

    def _update_zoom_button_icon(self):
        symbol = "-" if self._is_shift_pressed() else "+"
        self.name_zoom_btn.setIcon(self._build_zoom_icon(symbol))
        self.name_zoom_btn.setIconSize(QSize(20, 20))

    def _is_shift_pressed(self) -> bool:
        return bool(getattr(self, "_shift_pressed", False))

    def _source_records(self):
        if callable(self.source_records_provider):
            try:
                return list(self.source_records_provider())
            except Exception:
                return []
        return [self.record]

    def _current_record_index_in_source(self) -> int:
        uid = str(getattr(self.record, "uid", "") or "")
        for index, record in enumerate(self._source_records()):
            if str(getattr(record, "uid", "") or "") == uid:
                return index
        return -1

    def _next_record_for_current_source(self):
        records = self._source_records()
        current_index = self._current_record_index_in_source()
        if current_index < 0:
            return None
        next_index = current_index + 1
        if 0 <= next_index < len(records):
            return records[next_index]
        return None

    def _update_navigation_state(self):
        if hasattr(self, "next_btn"):
            self.next_btn.setEnabled(self._next_record_for_current_source() is not None and self._status_worker is None)

    def _apply_record(self, record):
        self.record = record
        self.setWindowTitle(f"修改签到状态 - {self.record.name}")
        for button in self.shortcut_buttons.values():
            button.setAutoExclusive(False)
            button.setChecked(False)
            button.setAutoExclusive(True)
        matched = False
        for status, button in ((button_id, button) for button_id, button in ((self.button_group.id(btn), btn) for btn in self.button_group.buttons())):
            if int(status) == int(getattr(self.record, "status", -1)):
                button.setChecked(True)
                matched = True
                break
        if not matched and self.shortcut_buttons:
            self.shortcut_buttons["1"].setChecked(True)
        self._update_name_column_appearance()
        self._apply_name_column_visibility()

    def _selected_submitted_status(self) -> int:
        selected_status = int(self.selected_status)
        parent = self.parent()
        if parent is not None and hasattr(parent, "_resolve_submitted_status"):
            return int(parent._resolve_submitted_status(self.source_tab_key, selected_status))
        return selected_status

    def _set_controls_enabled(self, enabled: bool):
        self.setEnabled(enabled)
        if hasattr(self, "next_shortcut"):
            self.next_shortcut.setEnabled(enabled)

    def _handle_accept_clicked(self):
        self._submit_mode = "accept"
        self._submit_current_status()

    def _handle_next_clicked(self):
        if not self.next_btn.isEnabled():
            return
        self._submit_mode = "next"
        self._submit_current_status()

    def _submit_current_status(self):
        new_status = self._selected_submitted_status()
        if new_status < 0:
            return
        if new_status == int(getattr(self.record, "status", -1)):
            self._advance_after_submit(new_status, status_changed=False)
            return
        if self.crawler is None or not self.active_id:
            QMessageBox.warning(self, "修改失败", "缺少签到状态提交参数")
            return
        self._set_controls_enabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._status_worker = AttendanceStatusUpdateWorker(
            self.crawler,
            self.active_id,
            self.record.uid,
            new_status,
            "",
        )
        self._status_worker.update_finished.connect(self._on_status_update_finished)
        self._status_worker.start()

    def _refresh_parent_after_update(self, uid: int, status: int, preferred_uid: str = ""):
        parent = self.parent()
        if parent is None or not hasattr(parent, "detail"):
            return False
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        changed = parent.detail.update_record_status(uid, status, current_time)
        if changed and hasattr(parent, "_refresh_tables"):
            parent._refresh_tables(preferred_uid=preferred_uid, preferred_tab_key=self.source_tab_key)
        elif hasattr(parent, "_apply_selection"):
            parent._apply_selection(preferred_uid=preferred_uid, preferred_tab_key=self.source_tab_key)
        return changed

    def _sync_parent_selection(self, preferred_uid: str = ""):
        parent = self.parent()
        if parent is None:
            return
        if hasattr(parent, "_refresh_tables"):
            parent._refresh_tables(preferred_uid=preferred_uid, preferred_tab_key=self.source_tab_key)
        elif hasattr(parent, "_apply_selection"):
            parent._apply_selection(preferred_uid=preferred_uid, preferred_tab_key=self.source_tab_key)

    def _advance_after_submit(self, submitted_status: int, status_changed: bool):
        current_uid = str(getattr(self.record, "uid", "") or "")
        current_index = self._current_record_index_in_source()
        next_record = self._next_record_for_current_source()
        if self._submit_mode == "next" and next_record is not None:
            preferred_uid = str(getattr(next_record, "uid", "") or "")
            if status_changed:
                self._refresh_parent_after_update(self.record.uid, submitted_status, preferred_uid=preferred_uid)
            else:
                self._sync_parent_selection(preferred_uid=preferred_uid)
            refreshed_records = self._source_records()
            if current_index >= 0:
                current_uid_present = any(str(getattr(record, "uid", "") or "") == current_uid for record in refreshed_records)
                target_index = current_index + 1 if current_uid_present else current_index
                if 0 <= target_index < len(refreshed_records):
                    self._apply_record(refreshed_records[target_index])
                    self._submit_mode = ""
                    self._set_controls_enabled(True)
                    self._update_navigation_state()
                    return
        else:
            if status_changed:
                self._refresh_parent_after_update(self.record.uid, submitted_status)
        self._submit_mode = ""
        self._set_controls_enabled(True)
        self._update_navigation_state()
        self.accept()

    def _build_zoom_icon(self, symbol: str) -> QIcon:
        svg = f"""
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="10" cy="10" r="6.5" stroke="white" stroke-width="2"/>
            <line x1="14.8" y1="14.8" x2="20" y2="20" stroke="white" stroke-width="2.2" stroke-linecap="round"/>
            <line x1="7" y1="10" x2="13" y2="10" stroke="white" stroke-width="2" stroke-linecap="round"/>
            {"<line x1='10' y1='7' x2='10' y2='13' stroke='white' stroke-width='2' stroke-linecap='round'/>" if symbol == "+" else ""}
        </svg>
        """
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _load_name_column_font_size(self):
        saved_size = self.settings.value(self.NAME_COLUMN_FONT_SIZE_KEY, self.NAME_COLUMN_FONT_SIZE)
        try:
            self.__class__.NAME_COLUMN_FONT_SIZE = max(self.NAME_COLUMN_FONT_SIZE_MIN, int(saved_size))
        except (TypeError, ValueError):
            self.__class__.NAME_COLUMN_FONT_SIZE = self.NAME_COLUMN_FONT_SIZE

    def _save_name_column_font_size(self):
        self.settings.setValue(self.NAME_COLUMN_FONT_SIZE_KEY, int(self.__class__.NAME_COLUMN_FONT_SIZE))

    def _on_status_update_finished(self, success: bool, message: str, uid: int, status: int):
        worker = self._status_worker
        self._status_worker = None
        if worker is not None:
            worker.deleteLater()
        QApplication.restoreOverrideCursor()
        if not success:
            self._set_controls_enabled(True)
            self._update_navigation_state()
            QMessageBox.warning(self, "修改失败", message)
            return
        self._advance_after_submit(status, status_changed=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self._shift_pressed = True
            self._update_zoom_button_icon()
        key_text = event.text()
        button = self.shortcut_buttons.get(key_text)
        if button is not None:
            button.setChecked(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Shift:
            self._shift_pressed = False
            self._update_zoom_button_icon()
        super().keyReleaseEvent(event)

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() == Qt.Key.Key_Shift:
                self._shift_pressed = event.type() == QEvent.Type.KeyPress
                self._update_zoom_button_icon()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        self._position_name_zoom_button()
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self._app is not None:
            self._app.removeEventFilter(self)
        self._shift_pressed = False
        if self._status_worker is not None:
            self._status_worker.deleteLater()
            self._status_worker = None
        super().closeEvent(event)


class AttendanceDetailDialog(QDialog):
    """签到详情对话框。"""
    
    def __init__(self, crawler, activity: Activity, detail: AttendanceDetail, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.activity = activity
        self.detail = detail
        self._active_search_query = ""
        self._status_worker = None
        self._tables = {}
        self._pending_selection_uid = ""
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle(f"签到详情 - {self.activity.title}")
        screen = QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen else 720
        dialog_height = max(420, min(540, available_height - 180))
        self.resize(860, dialog_height)
        
        # 设置对话框背景为暗色主题
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e0e0e0;
            }
            QTableWidget {
                background-color: #2d2d2d;
                alternate-background-color: #252526;
                color: #e0e0e0;
                gridline-color: #404040;
                border: 1px solid #404040;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #007acc;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                color: #e0e0e0;
                padding: 5px;
                border: 1px solid #404040;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 活动信息
        self.info_label = QLabel()
        apply_theme_stylesheet(self.info_label, "padding: 10px; background: #2d2d2d; border-radius: 5px; border: 1px solid #404040;")
        layout.addWidget(self.info_label)
        
        # 统计信息
        self.stats_label = QLabel(self._build_stats_text())
        apply_theme_stylesheet(self.stats_label, "padding: 10px; background: #2d2d2d; font-size: 13px; border-radius: 5px; border: 1px solid #404040;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索姓名或学号...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(220)
        apply_theme_stylesheet(self.search_input, """
            QLineEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #404040;
                border-radius: 5px;
                font-size: 12px;
                padding: 6px 8px;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._execute_search)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setFixedWidth(72)
        apply_theme_stylesheet(self.search_btn, """
            QPushButton {
                font-size: 12px;
                padding: 6px 12px;
            }
        """)
        self.search_btn.clicked.connect(self._execute_search)

        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        self.tabs.setCornerWidget(search_container, Qt.Corner.TopRightCorner)
        layout.addWidget(self.tabs, stretch=1)
        self._refresh_tables()
        
        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.close_btn = QPushButton("关闭")
        self.close_btn.setFixedWidth(100)
        self.close_btn.setAutoDefault(False)
        self.close_btn.setDefault(False)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
        bind_theme_tree(self)
        theme_manager().theme_changed.connect(self._apply_runtime_theme)
        self._apply_runtime_theme(theme_manager().mode)

    def _build_records_tab(self, records, empty_text: str, tab_key: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["姓名", "学号", "签到状态", "签到时间"])
        table.setRowCount(len(records))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(2, 100)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setProperty("tab_key", tab_key)
        table.cellClicked.connect(lambda row, _col, t=table: self._activate_record(t, row))
        table.cellActivated.connect(lambda row, _col, t=table: self._activate_record(t, row))

        for row, record in enumerate(records):
            table.setItem(row, 0, QTableWidgetItem(record.name))
            table.setItem(row, 1, QTableWidgetItem(record.username))

            status_item = QTableWidgetItem(record.status_name)
            status_item.setForeground(QColor(self._status_color_for_record(record)))
            table.setItem(row, 2, status_item)

            table.setItem(row, 3, QTableWidgetItem(record.submit_time or record.create_time))

        if not records:
            table.setRowCount(1)
            empty_item = QTableWidgetItem(empty_text)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor(get_theme_palette().text_muted))
            table.setSpan(0, 0, 1, 4)
            table.setItem(0, 0, empty_item)

        self._tables[tab_key] = table
        layout.addWidget(table)
        return container

    def _build_activity_info_text(self, mode: str | None = None) -> str:
        palette = get_theme_palette(mode)
        return (
            f"<b style='color: {palette.accent};'>活动名称：</b>"
            f"<span style='color: {palette.text};'>{self.activity.title}</span><br>"
            f"<b style='color: {palette.accent};'>活动时间：</b>"
            f"<span style='color: {palette.text};'>{self.activity.time_range}</span>"
        )

    def _status_color_for_record(self, record, mode: str | None = None) -> str:
        palette = get_theme_palette(mode)
        if record.is_normal or record.is_proxy:
            return palette.success
        if record.is_late or record.is_early_leave:
            return "#9a6700" if palette.mode == "light" else "#dcdcaa"
        if record.is_absent or record.is_unsign:
            return palette.danger
        if record.is_leave:
            return palette.accent
        return palette.text_secondary

    def _apply_runtime_theme(self, mode: str):
        self.info_label.setText(self._build_activity_info_text(mode))
        self.stats_label.setText(self._build_stats_text(mode))
        palette = get_theme_palette(mode)
        for table in self._tables.values():
            tab_key = str(table.property("tab_key") or "")
            records = self._filtered_records_for_tab_key(tab_key)
            if records:
                for row, record in enumerate(records):
                    status_item = table.item(row, 2)
                    if status_item is not None:
                        status_item.setForeground(QColor(self._status_color_for_record(record, mode)))
            else:
                empty_item = table.item(0, 0)
                if empty_item is not None:
                    empty_item.setForeground(QColor(palette.text_muted))

    def _build_stats_text(self, mode: str | None = None) -> str:
        palette = get_theme_palette(mode)
        stats = self.detail.get_statistics()
        return (
            f"<b style='color: {palette.accent};'>签到统计：</b>"
            f"<span style='color: {palette.text};'>总人数：{stats['总人数']} | </span>"
            f"<span style='color: {palette.success};'>已签：{stats['已签']} | </span>"
            f"<span style='color: {palette.danger};'>未签：{stats['未签']} | </span>"
            f"<span style='color: {'#9a6700' if palette.mode == 'light' else '#dcdcaa'};'>迟到：{stats['迟到']} | </span>"
            f"<span style='color: {'#9a6700' if palette.mode == 'light' else '#dcdcaa'};'>早退：{stats['早退']} | </span>"
            f"<span style='color: {palette.danger};'>缺勤：{stats['缺勤']} | </span>"
            f"<span style='color: {palette.accent};'>病假：{stats['病假']} | </span>"
            f"<span style='color: {palette.accent};'>事假：{stats['事假']} | </span>"
            f"<span style='color: {palette.accent};'>公假：{stats['公假']} | </span>"
            f"<span style='color: {palette.text_muted};'>代签：{stats['代签']}</span>"
        )

    def _refresh_tables(self, preferred_uid: str = "", preferred_tab_key: str = ""):
        current_index = self.tabs.currentIndex() if self.tabs.count() else 0
        self.stats_label.setText(self._build_stats_text())
        self._tables = {}
        self.tabs.blockSignals(True)
        self.tabs.clear()
        signed_records = self._filtered_records_for_tab_key("signed")
        unsigned_records = self._filtered_records_for_tab_key("unsigned")
        self.tabs.addTab(
            self._build_records_tab(signed_records, empty_text=self._empty_text_for_tab("signed"), tab_key="signed"),
            f"已签({len(self.detail.signed_records)})",
        )
        self.tabs.addTab(
            self._build_records_tab(unsigned_records, empty_text=self._empty_text_for_tab("unsigned"), tab_key="unsigned"),
            f"未签({len(self.detail.unsigned_records)})",
        )
        if self.tabs.count():
            self.tabs.setCurrentIndex(min(current_index, self.tabs.count() - 1))
        self.tabs.blockSignals(False)
        self._apply_selection(
            preferred_uid,
            preferred_tab_key=preferred_tab_key or self._tab_key_for_index(current_index),
        )

    def _records_for_table(self, table: QTableWidget):
        tab_key = table.property("tab_key")
        return self.detail.signed_records if tab_key == "signed" else self.detail.unsigned_records

    def _records_for_tab_key(self, tab_key: str):
        return self.detail.signed_records if tab_key == "signed" else self.detail.unsigned_records

    def _filtered_records_for_tab_key(self, tab_key: str):
        records = self._records_for_tab_key(tab_key)
        query = self._search_query()
        if not query:
            return list(records)
        return [record for record in records if self._record_matches_query(record, query)]

    def _search_query(self) -> str:
        active_query = getattr(self, "_active_search_query", None)
        if active_query is not None:
            return str(active_query or "").strip().lower()
        if not hasattr(self, "search_input"):
            return ""
        return str(self.search_input.text() or "").strip().lower()

    def _record_matches_query(self, record, query: str) -> bool:
        if not query:
            return True
        return query in str(record.name or "").lower() or query in str(record.username or "").lower()

    def _empty_text_for_tab(self, tab_key: str) -> str:
        if self._search_query():
            return "无匹配结果"
        return "暂无已签学生" if tab_key == "signed" else "暂无未签学生"

    def _tab_key_for_index(self, index: int) -> str:
        return "signed" if index == 0 else "unsigned"

    def _apply_selection(self, preferred_uid: str = "", preferred_tab_key: str = ""):
        target_uid = str(preferred_uid or self._pending_selection_uid or "").strip()
        self._pending_selection_uid = ""
        if target_uid and self._select_record_by_uid(target_uid):
            return
        self._select_first_record(preferred_tab_key=preferred_tab_key)

    def _select_first_record(self, preferred_tab_key: str = ""):
        tab_keys = ["signed", "unsigned"]
        if preferred_tab_key in tab_keys:
            tab_keys.remove(preferred_tab_key)
            tab_keys.insert(0, preferred_tab_key)
        for tab_key in tab_keys:
            if self._filtered_records_for_tab_key(tab_key):
                self._focus_record(tab_key, 0)
                return

    def _select_record_by_uid(self, uid: str) -> bool:
        uid_str = str(uid or "").strip()
        if not uid_str:
            return False
        for tab_key in ("signed", "unsigned"):
            for row, record in enumerate(self._filtered_records_for_tab_key(tab_key)):
                if str(record.uid) == uid_str:
                    self._focus_record(tab_key, row)
                    return True
        return False

    def _focus_record(self, tab_key: str, row: int):
        table = self._tables.get(tab_key)
        records = self._filtered_records_for_tab_key(tab_key)
        if table is None or row < 0 or row >= len(records):
            return
        self.tabs.setCurrentIndex(0 if tab_key == "signed" else 1)
        table.setFocus()
        table.setCurrentCell(row, 0)
        table.selectRow(row)

    def _select_first_record_in_tab(self, tab_key: str):
        records = self._filtered_records_for_tab_key(tab_key)
        if records:
            self._focus_record(tab_key, 0)

    def _on_tab_changed(self, index: int):
        if index == 0:
            self._select_first_record_in_tab("signed")
        elif index == 1:
            self._select_first_record_in_tab("unsigned")

    def _execute_search(self):
        self._active_search_query = str(self.search_input.text() or "").strip().lower()
        self._refresh_tables(preferred_tab_key=self._tab_key_for_index(self.tabs.currentIndex() if self.tabs.count() else 0))

    def _on_search_text_changed(self, _text: str):
        if str(_text or "").strip():
            return
        self._active_search_query = ""
        self._refresh_tables(preferred_tab_key=self._tab_key_for_index(self.tabs.currentIndex() if self.tabs.count() else 0))

    def _next_record_uid(self, records, row: int) -> str:
        next_index = row + 1
        if 0 <= next_index < len(records):
            return str(records[next_index].uid)
        return ""

    def _activate_record(self, table: QTableWidget, row: int):
        source_tab_key = str(table.property("tab_key") or "")
        records = self._filtered_records_for_tab_key(source_tab_key)
        if row < 0 or row >= len(records):
            return

        record = records[row]
        self._pending_selection_uid = ""
        dialog = AttendanceStatusEditDialog(
            record,
            crawler=self.crawler,
            active_id=self.activity.active_id,
            source_tab_key=source_tab_key,
            source_records_provider=lambda tab_key=source_tab_key: self._filtered_records_for_tab_key(tab_key),
            parent=self,
        )
        dialog.exec()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus_widget = self.focusWidget()
            for table in self._tables.values():
                if focus_widget is table:
                    row = table.currentRow()
                    if row >= 0:
                        self._activate_record(table, row)
                        event.accept()
                        return
                    break
        super().keyPressEvent(event)


    def _resolve_submitted_status(self, source_tab_key: str, selected_status: int) -> int:
        if source_tab_key == "unsigned" and int(selected_status) == 1:
            return 2
        return int(selected_status)

    def _submit_status_change(self, record, new_status: int):
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._status_worker = AttendanceStatusUpdateWorker(
            self.crawler,
            self.activity.active_id,
            record.uid,
            new_status,
            "",
        )
        self._status_worker.update_finished.connect(self._on_status_update_finished)
        self._status_worker.start()

    def _on_status_update_finished(self, success: bool, message: str, uid: int, status: int):
        worker = self._status_worker
        self._status_worker = None
        if worker is not None:
            worker.deleteLater()

        if not success:
            QApplication.restoreOverrideCursor()
            self.setEnabled(True)
            QMessageBox.warning(self, "修改失败", message)
            return

        QApplication.restoreOverrideCursor()
        self.setEnabled(True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.detail.update_record_status(uid, status, current_time):
            self._refresh_tables(preferred_uid=self._pending_selection_uid)
        else:
            self._apply_selection()

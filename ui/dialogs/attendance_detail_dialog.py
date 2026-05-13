"""签到详情对话框。"""
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QHeaderView, QRadioButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt
from models.attendance_record import AttendanceDetail
from models.activity import Activity
from ui.workers import AttendanceStatusUpdateWorker


class AttendanceStatusEditDialog(QDialog):
    """签到状态修改对话框。"""

    STATUS_OPTIONS = [
        ("1", "已签", 1),
        ("2", "缺勤", 5),
        ("3", "迟到", 9),
        ("4", "早退", 10),
        ("5", "事假", 8),
        ("6", "病假", 7),
        ("7", "公假", 12),
    ]

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.button_group = QButtonGroup(self)
        self.shortcut_buttons = {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"修改签到状态 - {self.record.name}")
        self.resize(320, 360)
        self.setModal(True)
        self.setStyleSheet("""
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

        layout = QVBoxLayout(self)
        info_label = QLabel(
            f"<b>姓名：</b>{self.record.name}<br>"
            f"<b>学号：</b>{self.record.username}<br>"
            f"<b>当前状态：</b>{self.record.status_name}"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        for key, text, status in self.STATUS_OPTIONS:
            radio = QRadioButton(f"{key}. {text}")
            self.button_group.addButton(radio, status)
            self.shortcut_buttons[key] = radio
            if status == self.record.status:
                radio.setChecked(True)
            layout.addWidget(radio)

        checked = self.button_group.checkedButton()
        if checked is None and self.shortcut_buttons:
            self.shortcut_buttons["1"].setChecked(True)

        hint_label = QLabel("快捷键：1-7 选择状态，Enter 确认")
        hint_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(hint_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    @property
    def selected_status(self) -> int:
        return self.button_group.checkedId()

    def keyPressEvent(self, event):
        key_text = event.text()
        button = self.shortcut_buttons.get(key_text)
        if button is not None:
            button.setChecked(True)
            event.accept()
            return
        super().keyPressEvent(event)


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
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e0e0e0;
            }
            QTableWidget {
                background-color: #2d2d2d;
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
        info_label = QLabel(
            f"<b style='color: #569cd6;'>活动名称：</b><span style='color: #e0e0e0;'>{self.activity.title}</span><br>"
            f"<b style='color: #569cd6;'>活动时间：</b><span style='color: #e0e0e0;'>{self.activity.time_range}</span>"
        )
        info_label.setStyleSheet("padding: 10px; background: #2d2d2d; border-radius: 5px; border: 1px solid #404040;")
        layout.addWidget(info_label)
        
        # 统计信息
        self.stats_label = QLabel(self._build_stats_text())
        self.stats_label.setStyleSheet("padding: 10px; background: #2d2d2d; font-size: 13px; border-radius: 5px; border: 1px solid #404040;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索姓名或学号...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(220)
        self.search_input.setStyleSheet("""
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
        self.search_btn.setStyleSheet("""
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
            if record.is_normal or record.is_proxy:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif record.is_late or record.is_early_leave:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            elif record.is_absent or record.is_unsign:
                status_item.setForeground(Qt.GlobalColor.red)
            elif record.is_leave:
                status_item.setForeground(Qt.GlobalColor.blue)
            table.setItem(row, 2, status_item)

            table.setItem(row, 3, QTableWidgetItem(record.submit_time or record.create_time))

        if not records:
            table.setRowCount(1)
            empty_item = QTableWidgetItem(empty_text)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setSpan(0, 0, 1, 4)
            table.setItem(0, 0, empty_item)

        self._tables[tab_key] = table
        layout.addWidget(table)
        return container

    def _build_stats_text(self) -> str:
        stats = self.detail.get_statistics()
        return (
            f"<b style='color: #569cd6;'>签到统计：</b>"
            f"<span style='color: #e0e0e0;'>总人数：{stats['总人数']} | </span>"
            f"<span style='color: #4ec9b0;'>已签：{stats['已签']} | </span>"
            f"<span style='color: #f44747;'>未签：{stats['未签']} | </span>"
            f"<span style='color: #dcdcaa;'>迟到：{stats['迟到']} | </span>"
            f"<span style='color: #dcdcaa;'>早退：{stats['早退']} | </span>"
            f"<span style='color: #f44747;'>缺勤：{stats['缺勤']} | </span>"
            f"<span style='color: #9cdcfe;'>病假：{stats['病假']} | </span>"
            f"<span style='color: #9cdcfe;'>事假：{stats['事假']} | </span>"
            f"<span style='color: #9cdcfe;'>公假：{stats['公假']} | </span>"
            f"<span style='color: #aaaaaa;'>代签：{stats['代签']}</span>"
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
        records = self._filtered_records_for_tab_key(str(table.property("tab_key") or ""))
        if row < 0 or row >= len(records):
            return

        record = records[row]
        source_tab_key = str(table.property("tab_key") or "")
        self._pending_selection_uid = self._next_record_uid(records, row)
        dialog = AttendanceStatusEditDialog(record, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._pending_selection_uid = ""
            return

        new_status = self._resolve_submitted_status(source_tab_key, dialog.selected_status)
        if new_status < 0 or new_status == record.status:
            self._pending_selection_uid = ""
            return
        self._submit_status_change(record, new_status)

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

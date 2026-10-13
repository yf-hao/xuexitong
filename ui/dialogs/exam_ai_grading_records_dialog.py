from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class ExamAIGradingRecordsDialog(QDialog):
    resolve_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(str)

    STATUS_LABELS = {
        "pending": "待处理",
        "grading": "评分中",
        "ready_to_submit": "待提交",
        "grading_failed": "评分异常",
        "submission_failed": "提交异常",
        "stopped": "已暂停",
    }

    def __init__(self, records, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI改卷记录")
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        self.records_table = QTableWidget(len(records), 5, self)
        self.records_table.setHorizontalHeaderLabels(
            ["姓名", "学号", "状态", "处理阶段", "异常原因"]
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
        self.records_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.records_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self._answer_ids = []
        for row, record in enumerate(records):
            self._answer_ids.append(str(record.get("answer_id", "")))
            values = (
                record.get("student_name", ""),
                record.get("student_id", ""),
                self.STATUS_LABELS.get(
                    record.get("status"), record.get("status", "")
                ),
                record.get("stage", ""),
                record.get("error", ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(item.text())
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | Qt.AlignmentFlag.AlignLeft
                )
                self.records_table.setItem(row, column, item)
        layout.addWidget(self.records_table, 1)

        buttons = QHBoxLayout()
        self.retry_button = QPushButton("重试")
        self.retry_button.clicked.connect(self._retry_selected)
        buttons.addWidget(self.retry_button)
        self.resolve_button = QPushButton("标记已处理")
        self.resolve_button.clicked.connect(self._resolve_selected)
        buttons.addWidget(self.resolve_button)
        buttons.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.records_table.itemSelectionChanged.connect(
            self._update_resolve_enabled
        )
        self._update_resolve_enabled()

    def _update_resolve_enabled(self):
        row = self.records_table.currentRow()
        self.resolve_button.setEnabled(
            row >= 0
            and self.records_table.item(row, 2).text()
            in {"评分异常", "提交异常"}
        )
        self.retry_button.setEnabled(self.resolve_button.isEnabled())

    def _retry_selected(self):
        row = self.records_table.currentRow()
        if row < 0 or row >= len(self._answer_ids):
            return
        self.retry_requested.emit(self._answer_ids[row])
        self.accept()

    def _resolve_selected(self):
        row = self.records_table.currentRow()
        if row < 0 or row >= len(self._answer_ids):
            return
        self.resolve_requested.emit(self._answer_ids[row])
        self.records_table.removeRow(row)
        self._answer_ids.pop(row)
        self._update_resolve_enabled()
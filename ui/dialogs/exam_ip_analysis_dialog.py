from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.apis.exam_api import (
    ExamReviewContext, fetch_all_submitted_exam_records,
)
from core.utils.exam_ip_analysis import (
    HIGH_RISK, MEDIUM_RISK, analyze_exam_ip_risks,
)
from ui.theme import apply_theme_stylesheet, bind_theme_tree, get_theme_palette


class ExamIpAnalysisWorker(QThread):
    progress = pyqtSignal(int, int)
    loaded = pyqtSignal(object, int)
    failed = pyqtSignal(str)

    def __init__(self, session, context: ExamReviewContext, parent=None):
        super().__init__(parent)
        self.session = session
        self.context = context

    def run(self):
        try:
            records = fetch_all_submitted_exam_records(
                self.session,
                self.context,
                page_size=100,
                progress_callback=lambda current, total: self.progress.emit(
                    current, total
                ),
            )
            self.loaded.emit(analyze_exam_ip_risks(records), len(records))
        except Exception as exc:
            self.failed.emit(str(exc))


class ExamIpAnalysisDialog(QDialog):
    def __init__(self, session, context: ExamReviewContext, parent=None):
        super().__init__(parent)
        self.context = context
        self._groups = []
        self.setWindowTitle(f"IP分析 - {context.exam_title or '考试'}")
        self.resize(1080, 580)
        self._setup_ui()

        self.worker = ExamIpAnalysisWorker(session, context, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.loaded.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.status_label = QLabel("正在读取本场考试所有已交记录…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(8)
        layout.addWidget(self.progress_bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["风险线索", "提交 IP / 归属地", "人数", "涉及学生", "触发依据"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("关闭")
        self.close_button.setMinimumWidth(84)
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        apply_theme_stylesheet(self, lambda palette: f"""
            QWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QTableWidget {{
                background-color: {palette.panel_bg};
                alternate-background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                gridline-color: {palette.border};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QTableWidget::item {{ padding: 5px; }}
            QHeaderView::section {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text_secondary};
                border: none;
                border-bottom: 1px solid {palette.border};
                padding: 7px;
            }}
            QProgressBar {{
                background-color: {palette.panel_alt_bg};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{ background-color: {palette.accent}; }}
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
            QPushButton:disabled {{ color: {palette.disabled_text}; }}
        """)
        bind_theme_tree(self)

    def _on_progress(self, current, total):
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(current)
        self.status_label.setText(f"正在读取第 {current} / {total} 页的已交记录…")

    def _on_loaded(self, groups, record_count):
        self._groups = groups
        self.table.setRowCount(len(groups))
        palette = get_theme_palette()

        for row, group in enumerate(groups):
            student_lines = []
            for student in group["students"]:
                duration = student["duration_minutes"]
                duration_text = "未知"
                if duration is not None:
                    duration_text = (
                        f"{int(duration)}分钟"
                        if float(duration).is_integer()
                        else f"{duration:.1f}分钟"
                    )
                student_lines.append(
                    f"{student['label']} · {student['submit_text']} · 用时 {duration_text}"
                )

            values = (
                group["risk_level"],
                group["ip_display"],
                str(group["student_count"]),
                "\n".join(student_lines),
                group["evidence"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    if group["risk_level"] == HIGH_RISK:
                        item.setForeground(QColor(palette.danger))
                    elif group["risk_level"] == MEDIUM_RISK:
                        item.setForeground(QColor(palette.warning))
                self.table.setItem(row, column, item)

        self.table.resizeRowsToContents()
        high_count = sum(group["risk_level"] == HIGH_RISK for group in groups)
        medium_count = sum(group["risk_level"] == MEDIUM_RISK for group in groups)
        self.status_label.setText(
            f"读取 {record_count} 份已交记录，发现 {len(groups)} 个重复 IP 组；"
            f"高风险线索 {high_count} 组，中风险线索 {medium_count} 组。"
            "风险线索仅供人工复核，不代表作弊结论。"
        )
        if not groups:
            self.status_label.setText(
                f"读取 {record_count} 份已交记录，未发现同一 IP 下的多名学生。"
            )

    def _on_failed(self, message):
        self.progress_bar.hide()
        self.status_label.setText(f"IP分析失败：{message}")

    def _on_worker_finished(self):
        self.progress_bar.hide()
        self.close_button.setEnabled(True)

    def closeEvent(self, event):
        if self.worker.isRunning():
            event.ignore()
            self.status_label.setText("分析仍在进行，完成后即可关闭。")
            return
        super().closeEvent(event)

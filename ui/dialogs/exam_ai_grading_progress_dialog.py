from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QLabel, QProgressBar, QVBoxLayout,
)

from ui.theme import apply_theme_stylesheet, bind_theme_tree


class ExamAIBulkGradingProgressDialog(QDialog):
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI改卷进度")
        self.setFixedWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        self.status_label = QLabel("正在读取本场考试已交答卷名单…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.stage_label = QLabel("")
        self.stage_label.setObjectName("progressStage")
        self.stage_label.setWordWrap(True)
        self.stage_label.hide()
        layout.addWidget(self.stage_label)
        layout.addSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_bar)

        apply_theme_stylesheet(self, lambda palette: f"""
            QDialog {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QLabel {{
                color: {palette.text};
            }}
            QLabel#progressStage {{
                color: {palette.text_muted};
                font-size: 12px;
            }}
            QProgressBar {{
                min-height: 18px;
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 9px;
                background-color: {palette.panel_alt_bg};
            }}
            QProgressBar::chunk {{
                border-radius: 8px;
                background-color: {palette.accent};
            }}
        """)
        bind_theme_tree(self)

    def set_progress(self, current, total, text, student="", stage=""):
        if student:
            self.status_label.setText(f"正在批改：{student}")
            self.stage_label.setText(stage)
            self.stage_label.setVisible(bool(stage))
        else:
            self.status_label.setText(text)
            self.stage_label.hide()
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat("%v / %m")
        else:
            self.progress_bar.setRange(0, 0)

    def set_finished(self, text):
        self.status_label.setText(text)
        self.stage_label.hide()
        maximum = self.progress_bar.maximum()
        if maximum <= 0:
            self.progress_bar.setRange(0, 1)
            maximum = 1
        self.progress_bar.setValue(maximum)

    def closeEvent(self, event):
        self.dismissed.emit()
        super().closeEvent(event)

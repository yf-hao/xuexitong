from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QLabel, QProgressBar, QVBoxLayout,
)

from ui.theme import apply_theme_stylesheet, bind_theme_tree


class ExamAIBulkGradingProgressDialog(QDialog):
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI改卷进度")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.status_label = QLabel("正在读取本场考试已交答卷名单…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        apply_theme_stylesheet(self, lambda palette: f"""
            QDialog {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QLabel {{
                color: {palette.text};
            }}
            QProgressBar {{
                min-height: 10px;
                border: 1px solid {palette.border};
                border-radius: 5px;
                background-color: {palette.panel_alt_bg};
            }}
            QProgressBar::chunk {{
                border-radius: 4px;
                background-color: {palette.accent};
            }}
        """)
        bind_theme_tree(self)

    def set_progress(self, current, total, text):
        self.status_label.setText(text)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    def set_finished(self, text):
        self.status_label.setText(text)
        maximum = self.progress_bar.maximum()
        if maximum <= 0:
            self.progress_bar.setRange(0, 1)
            maximum = 1
        self.progress_bar.setValue(maximum)

    def closeEvent(self, event):
        self.dismissed.emit()
        super().closeEvent(event)

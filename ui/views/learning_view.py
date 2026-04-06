from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt


class LearningView(QWidget):
    """学情视图占位页。"""

    def __init__(self, crawler, status_callback, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.status_callback = status_callback
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(20)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #2d2f33;
                border-radius: 10px;
                padding: 20px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        title = QLabel("学情")
        title.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")

        desc = QLabel("学情页面已接入课程菜单，后续可以在这里承接学习进度、完成率、访问情况等功能。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #bfc7d5; font-size: 13px; line-height: 1.6;")

        card_layout.addWidget(title)
        card_layout.addWidget(desc)
        layout.addWidget(card)

    def on_show(self):
        self.status_callback("学情页面已加载")

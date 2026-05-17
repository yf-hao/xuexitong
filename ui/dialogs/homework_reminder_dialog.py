"""作业一键提醒设置弹窗。"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)
from ui.theme import apply_theme_stylesheet


DEFAULT_HOMEWORK_REMINDER_TEMPLATE = (
    "作业总数为:{total_count}，未提交为:{unsubmitted_count}，"
    "期末时超过1/2的作业未提交将取消考试资格，请注意。"
)
DEFAULT_ABSENCE_REMINDER_TEMPLATE = (
    "总签到次数为:{total_count}，缺勤为:{absent_count}，"
    "缺勤超过1/3将取消期末考试资格，请注意。"
)


class HomeworkReminderDialog(QDialog):
    """设置批量提醒阈值和消息模板。"""

    def __init__(
        self,
        threshold: int = 1,
        message_template: str = "",
        parent=None,
        *,
        title: str = "一键提醒",
        threshold_label: str = "未提交阈值（未提交数大于等于该值时发送）",
        template_placeholder: str = DEFAULT_HOMEWORK_REMINDER_TEMPLATE,
        placeholders_tip: str = (
            "支持占位：{student_name}、{student_id}、{total_count}、"
            "{submitted_count}、{pending_count}、{unsubmitted_count}"
        ),
    ):
        super().__init__(parent)
        self.threshold_input = None
        self.template_input = None
        self._title = str(title or "一键提醒")
        self._threshold_label = str(threshold_label or "").strip() or "提醒阈值"
        self._template_placeholder = str(template_placeholder or "").strip() or DEFAULT_HOMEWORK_REMINDER_TEMPLATE
        self._placeholders_tip = str(placeholders_tip or "").strip()
        self._default_template = str(message_template or "").strip() or self._template_placeholder
        self._setup_ui(max(0, int(threshold or 0)))

    def _setup_ui(self, threshold: int):
        self.setWindowTitle(self._title)
        self.resize(620, 420)
        self.setModal(True)
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e6e6e6;
            }
            QTextEdit, QSpinBox {
                background-color: #252526;
                color: #e6e6e6;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        threshold_label = QLabel(self._threshold_label)
        layout.addWidget(threshold_label)

        self.threshold_input = QSpinBox()
        self.threshold_input.setMinimum(0)
        self.threshold_input.setMaximum(999)
        self.threshold_input.setValue(threshold)
        layout.addWidget(self.threshold_input)

        template_label = QLabel("提醒消息模板")
        layout.addWidget(template_label)

        self.template_input = QTextEdit()
        self.template_input.setAcceptRichText(False)
        self.template_input.setPlaceholderText(self._template_placeholder)
        self.template_input.setPlainText(self._default_template)
        layout.addWidget(self.template_input, stretch=1)

        tips_label = QLabel(self._placeholders_tip)
        apply_theme_stylesheet(tips_label, "color: #9cdcfe; font-size: 12px;")
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(send_btn)

        layout.addLayout(btn_layout)

    def _on_send_clicked(self):
        if not self.message_template:
            self.template_input.setFocus()
            return
        self.accept()

    @property
    def threshold(self) -> int:
        return int(self.threshold_input.value()) if self.threshold_input else 0

    @property
    def message_template(self) -> str:
        return self.template_input.toPlainText().strip() if self.template_input else ""

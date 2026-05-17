"""可复用的学生消息发送弹窗。"""
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout
from ui.theme import apply_theme_stylesheet


class StudentMessageDialog(QDialog):
    """给单个学生发送消息的可复用弹窗。"""

    def __init__(self, crawler, student: dict, on_send_success=None, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.student = dict(student or {})
        self.on_send_success = on_send_success
        self.send_btn = None
        self.message_input = None
        self.status_label = None
        self._setup_ui()

    def _setup_ui(self):
        student_name = str(self.student.get("name") or "未知学生")
        self.setWindowTitle(f"发送消息 - {student_name}")
        self.resize(520, 360)
        self.setModal(True)
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e6e6e6;
            }
            QTextEdit {
                background-color: #252526;
                color: #e6e6e6;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 8px;
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
            QPushButton:disabled {
                background-color: #3d3d3d;
                color: #9a9a9a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info_lines = self._build_info_lines(self.student)
        info_label = QLabel("\n".join(info_lines))
        info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        apply_theme_stylesheet(info_label, "color: #dcdcdc; font-size: 14px;")
        layout.addWidget(info_label)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("请输入要发送的消息...")
        self.message_input.setAcceptRichText(False)
        layout.addWidget(self.message_input, stretch=1)

        self.status_label = QLabel("")
        apply_theme_stylesheet(self.status_label, "color: #888888; font-size: 12px;")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("关闭")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(self.send_btn)

        layout.addLayout(btn_layout)

    @staticmethod
    def _build_info_lines(student: dict) -> list[str]:
        student = dict(student or {})
        student_name = str(student.get("name") or "未知学生")
        student_id = str(student.get("student_id") or "")
        puid = str(student.get("puid") or "")
        info_lines = [f"发送对象：{student_name}"]
        if student_id:
            info_lines.append(f"学号：{student_id}")
        if puid:
            info_lines.append(f"PUID：{puid}")
        return info_lines

    @staticmethod
    def _get_crawler(dialog_or_crawler):
        if hasattr(dialog_or_crawler, "crawler"):
            return getattr(dialog_or_crawler, "crawler")
        return dialog_or_crawler

    @classmethod
    def _ensure_connected(cls, dialog_or_crawler, timeout: float = 5.0, interval: float = 0.1):
        crawler = cls._get_crawler(dialog_or_crawler)
        if not hasattr(crawler, "is_msync_connected"):
            return False
        try:
            if crawler.is_msync_connected():
                return True
            if hasattr(crawler, "connect_msync"):
                crawler.connect_msync()
            deadline = time.monotonic() + max(0.1, float(timeout or 0))
            while time.monotonic() < deadline:
                if crawler.is_msync_connected():
                    return True
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
                time.sleep(max(0.01, float(interval or 0.05)))
        except Exception:
            return False
        return False

    @classmethod
    def send_student_message(cls, crawler, student: dict, content: str):
        content = str(content or "").strip()
        if not content:
            return {"status": "fail", "msg": "请输入要发送的消息"}

        if not hasattr(crawler, "send_message"):
            return {"status": "fail", "msg": "当前环境不支持发送消息"}

        if not cls._ensure_connected(crawler):
            return {"status": "fail", "msg": "实时消息连接未建立，请先打开消息模块后重试"}

        student = dict(student or {})
        target_id = str(student.get("tuid") or student.get("person_id") or "")
        target_name = str(student.get("name") or "")
        if not target_id:
            return {"status": "fail", "msg": "无法识别发送对象"}

        return crawler.send_message(
            target_user_id=target_id,
            content=content,
            target_name=target_name,
            history_chat_id=target_id,
        )

    def _on_send_clicked(self):
        content = self.message_input.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "消息为空", "请输入要发送的消息")
            return

        self.send_btn.setEnabled(False)
        self.status_label.setText("正在建立实时连接...")
        try:
            result = self.send_student_message(self.crawler, self.student, content)
        finally:
            self.send_btn.setEnabled(True)

        if isinstance(result, dict) and result.get("status") == "success":
            self.status_label.setText("发送成功")
            self.message_input.clear()
            if callable(self.on_send_success):
                try:
                    self.on_send_success(dict(self.student))
                except Exception:
                    pass
            return

        error_message = result.get("msg") if isinstance(result, dict) else str(result or "")
        self.status_label.setText("发送失败")
        QMessageBox.warning(self, "发送失败", error_message or "消息发送失败")

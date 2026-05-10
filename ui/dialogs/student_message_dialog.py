"""可复用的学生消息发送弹窗。"""
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout


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
        self.setStyleSheet("""
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
        info_label.setStyleSheet("color: #dcdcdc; font-size: 14px;")
        layout.addWidget(info_label)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("请输入要发送的消息...")
        self.message_input.setAcceptRichText(False)
        layout.addWidget(self.message_input, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-size: 12px;")
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

    def _ensure_connected(self, timeout: float = 5.0, interval: float = 0.1):
        if not hasattr(self.crawler, "is_msync_connected"):
            return False
        try:
            if self.crawler.is_msync_connected():
                return True
            if hasattr(self.crawler, "connect_msync"):
                self.crawler.connect_msync()
            deadline = time.monotonic() + max(0.1, float(timeout or 0))
            while time.monotonic() < deadline:
                if self.crawler.is_msync_connected():
                    return True
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
                time.sleep(max(0.01, float(interval or 0.05)))
        except Exception:
            return False
        return False

    def _on_send_clicked(self):
        content = self.message_input.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "消息为空", "请输入要发送的消息")
            return

        if not hasattr(self.crawler, "send_message"):
            QMessageBox.warning(self, "发送失败", "当前环境不支持发送消息")
            return
        
        self.status_label.setText("正在建立实时连接...")
        if not self._ensure_connected():
            self.status_label.setText("发送失败")
            QMessageBox.warning(self, "发送失败", "实时消息连接未建立，请先打开消息模块后重试")
            return

        target_id = str(self.student.get("tuid") or self.student.get("person_id") or "")
        target_name = str(self.student.get("name") or "")
        if not target_id:
            QMessageBox.warning(self, "发送失败", "无法识别发送对象")
            return

        self.send_btn.setEnabled(False)
        self.status_label.setText("正在发送...")
        try:
            result = self.crawler.send_message(
                target_user_id=target_id,
                content=content,
                target_name=target_name,
                history_chat_id=target_id,
            )
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

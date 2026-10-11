import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QCheckBox, QWidget,
)
from PyQt6.QtCore import QThread, Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from core.config import APP_TITLE
from ui.theme import (
    apply_theme_stylesheet,
    get_theme_palette,
    refresh_theme_styles,
    theme_manager,
)


class LoginWorker(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, crawler, phone, password, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.phone = phone
        self.password = password

    def run(self):
        try:
            success = self.crawler.login_by_password(self.phone, self.password)
            error = "" if success else getattr(
                self.crawler, "last_login_error", ""
            )
            self.completed.emit(success, error)
        except Exception as exc:
            self.completed.emit(False, str(exc))


class QRCodeLoginWorker(QThread):
    qr_ready = pyqtSignal(bytes)
    status_changed = pyqtSignal(str)
    completed = pyqtSignal(bool, str)

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.stop_event = threading.Event()

    def run(self):
        try:
            self.crawler.login_by_qrcode(
                status_callback=self.status_changed.emit,
                qr_callback=self.qr_ready.emit,
                stop_event=self.stop_event,
            )
            self.completed.emit(True, "")
        except Exception as exc:
            if not self.stop_event.is_set():
                self.completed.emit(False, str(exc))

    def stop(self):
        self.stop_event.set()


class LoginWindow(QDialog):
    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self._login_worker = None
        self._qr_worker = None
        self._password_login_success = False
        self._qrcode_login_success = False
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(380, 420)
        
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
                font-size: 13px;
                background: transparent;
            }
            QLineEdit {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #1a8ad4;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #888888;
            }
            #title_label {
                font-size: 20px;
                font-weight: bold;
                color: #007acc;
                margin-bottom: 20px;
            }
            QCheckBox {
                color: #aaaaaa;
                font-size: 13px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #333333;
                border: 1px solid #444444;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border: 1px solid #007acc;
                image: url(data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PScwIDAgMjQgMjQnIHhtbG5zPSdodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2Zyc+PHBhdGggZD0nTTkgMTYuMTdMNC44MyAxMmwtMS40MiAxLjQxTDkgMTkgMjEgN2wtMS40MS0xLjQxeicgZmlsbD0nd2hpdGUnLz48L3N2Zz4=);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(8) # 缩小间距，使标签和输入框成对出现

        self.theme_toggle_btn = QPushButton("☀️")
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.clicked.connect(self._toggle_theme)
        self.mode_switch_btn = QPushButton("扫码登录")
        self.mode_switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_switch_btn.setFlat(True)
        self.mode_switch_btn.clicked.connect(self._show_qrcode_login)
        control_row = QHBoxLayout()
        control_row.addWidget(self.mode_switch_btn)
        control_row.addStretch()
        control_row.addWidget(self.theme_toggle_btn)
        layout.addLayout(control_row)

        self.password_panel = QWidget()
        password_layout = QVBoxLayout(self.password_panel)
        password_layout.setContentsMargins(0, 0, 0, 0)
        
        phone_label = QLabel("手机号：")
        password_layout.addWidget(phone_label)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("请输入手机号")
        password_layout.addWidget(self.phone_input)
        
        password_label = QLabel("密码：")
        password_layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(self.password_input)

        self.remember_cb = QCheckBox("记住手机号和密码")
        self.remember_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        password_layout.addWidget(self.remember_cb)
        layout.addWidget(self.password_panel)

        self.qrcode_panel = QWidget()
        qrcode_layout = QVBoxLayout(self.qrcode_panel)
        qrcode_layout.setContentsMargins(0, 0, 0, 0)
        self.qr_label = QLabel("正在获取二维码...")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumSize(220, 220)
        qrcode_layout.addWidget(self.qr_label)
        self.qr_status_label = QLabel("请使用学习通 App 扫码登录")
        self.qr_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qrcode_layout.addWidget(self.qr_status_label)
        self.qr_refresh_btn = QPushButton("刷新二维码")
        self.qr_refresh_btn.setFlat(True)
        self.qr_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qr_refresh_btn.clicked.connect(self._start_qrcode_login)
        qrcode_layout.addWidget(self.qr_refresh_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.qrcode_panel.hide()
        layout.addWidget(self.qrcode_panel)
        
        # Load saved settings
        self.settings = QSettings("HaoSoft", "XuexitongManager")
        self.load_settings()
        
        self.status_label = QLabel("")
        apply_theme_stylesheet(self.status_label, "color: #ff5252; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.login_btn = QPushButton("立即登录")
        self.login_btn.setObjectName("login_btn")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_theme_stylesheet(self.login_btn, lambda palette: f"""
            QPushButton#login_btn {{
                background-color: {palette.accent};
                color: #ffffff;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                margin-top: 10px;
            }}
            QPushButton#login_btn:hover {{
                background-color: {palette.accent_hover};
                color: #ffffff;
            }}
            QPushButton#login_btn:disabled {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
            }}
        """)
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)
        
        self.setLayout(layout)
        # 用 adjustSize 让布局根据真实字体/DPI 计算需要的高度，
        # 再锁成固定大小——避免 Windows 下中文字体偏高导致按钮被截断。
        self.adjustSize()
        self.setFixedSize(self.size())
        theme_manager().theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager().mode)
        self._apply_mode_button_style()

    def _toggle_theme(self):
        mode = theme_manager().mode
        theme_manager().set_mode("dark" if mode == "light" else "light")

    def _apply_theme(self, mode):
        if mode == "light":
            self.theme_toggle_btn.setText("🌙")
            self.theme_toggle_btn.setToolTip("切换到暗色主题")
        else:
            self.theme_toggle_btn.setText("☀️")
            self.theme_toggle_btn.setToolTip("切换到亮色主题")
        refresh_theme_styles(self, mode)
        self._apply_mode_button_style()

    def _apply_mode_button_style(self):
        palette = get_theme_palette(theme_manager().mode)
        apply_theme_stylesheet(self.theme_toggle_btn, f"""
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text_muted};
                border: 1px solid {palette.border_strong};
                border-radius: 16px;
                padding: 0;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
                font-size: 15px;
                font-weight: normal;
                margin-top: 0;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                color: {palette.text};
                border: 1px solid {palette.accent};
            }}
        """)
        for button in (self.mode_switch_btn, self.qr_refresh_btn):
            apply_theme_stylesheet(button, f"""
                QPushButton {{
                    background: transparent;
                    color: {palette.accent};
                    border: none;
                    padding: 2px 0;
                    font-size: 12px;
                    font-weight: normal;
                }}
                QPushButton:hover {{
                    color: {palette.accent_hover};
                    text-decoration: underline;
                }}
            """)

    def _show_qrcode_login(self):
        if self._login_worker is not None and self._login_worker.isRunning():
            return
        self.password_panel.hide()
        self.login_btn.hide()
        self.mode_switch_btn.setText("账号密码登录")
        self.mode_switch_btn.clicked.disconnect()
        self.mode_switch_btn.clicked.connect(self._show_password_login)
        self.qrcode_panel.show()
        self.adjustSize()
        self._start_qrcode_login()

    def _show_password_login(self):
        self._stop_qrcode_worker()
        self.qrcode_panel.hide()
        self.password_panel.show()
        self.login_btn.show()
        self.mode_switch_btn.setText("扫码登录")
        self.mode_switch_btn.clicked.disconnect()
        self.mode_switch_btn.clicked.connect(self._show_qrcode_login)
        self.status_label.clear()
        self.adjustSize()

    def _start_qrcode_login(self):
        self._stop_qrcode_worker()
        self.qr_label.setPixmap(QPixmap())
        self.qr_label.setText("正在获取二维码...")
        self.qr_status_label.setText("请使用学习通 App 扫码登录")
        self.qr_refresh_btn.setEnabled(False)
        self._qr_worker = QRCodeLoginWorker(self.crawler, self)
        self._qr_worker.qr_ready.connect(self._set_qr_image)
        self._qr_worker.status_changed.connect(self.qr_status_label.setText)
        self._qr_worker.completed.connect(self._on_qrcode_completed)
        self._qr_worker.finished.connect(self._on_qrcode_worker_finished)
        self._qr_worker.start()

    def _set_qr_image(self, image_data):
        image = QImage.fromData(image_data)
        if image.isNull():
            self.qr_status_label.setText("二维码加载失败，请刷新重试")
            return
        pixmap = QPixmap.fromImage(image)
        self.qr_label.setText("")
        self.qr_label.setPixmap(
            pixmap.scaled(
                220, 220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.qr_refresh_btn.setEnabled(False)

    def _on_qrcode_completed(self, success, error):
        self._qrcode_login_success = success
        if success:
            self.qr_status_label.setText("登录成功，正在进入系统...")
        elif self._qr_worker is not None and not self._qr_worker.stop_event.is_set():
            self.qr_status_label.setText(error or "二维码登录失败，请刷新重试")
            self.qr_refresh_btn.setEnabled(True)

    def _on_qrcode_worker_finished(self):
        worker = self._qr_worker
        self._qr_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._qrcode_login_success:
            self.accept()

    def _stop_qrcode_worker(self):
        if self._qr_worker is not None and self._qr_worker.isRunning():
            self._qr_worker.stop()
            self._qr_worker.wait(5000)
        self._qrcode_login_success = False

    def handle_login(self):
        if self._login_worker is not None and self._login_worker.isRunning():
            return

        phone = self.phone_input.text().strip()
        password = self.password_input.text().strip()
        
        if not phone or not password:
            self.status_label.setText("请输入完整的信息")
            return
            
        self._set_login_controls_enabled(False)
        self.status_label.setText("正在连接学习通，请稍候...")
        self._password_login_success = False

        self._login_worker = LoginWorker(self.crawler, phone, password, self)
        self._login_worker.completed.connect(self._on_login_completed)
        self._login_worker.finished.connect(self._on_login_worker_finished)
        self._login_worker.start()

    def _on_login_completed(self, success, error):
        if success:
            self._password_login_success = True
            self.status_label.setText("登录成功，正在进入系统...")
        else:
            self.status_label.setText(error or "身份验证失败，请重试")
            self._set_login_controls_enabled(True)

    def _on_login_worker_finished(self):
        worker = self._login_worker
        self._login_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._password_login_success:
            self.save_settings()
            self.accept()

    def _set_login_controls_enabled(self, enabled):
        self.phone_input.setEnabled(enabled)
        self.password_input.setEnabled(enabled)
        self.remember_cb.setEnabled(enabled)
        self.login_btn.setEnabled(enabled)

    def reject(self):
        if self._login_worker is not None and self._login_worker.isRunning():
            self.status_label.setText("登录请求仍在进行，请稍候...")
            return
        self._stop_qrcode_worker()
        super().reject()

    def closeEvent(self, event):
        if self._login_worker is not None and self._login_worker.isRunning():
            event.ignore()
            self.status_label.setText("登录请求仍在进行，请稍候...")
            return
        self._stop_qrcode_worker()
        super().closeEvent(event)

    def load_settings(self):
        """Load phone and password from QSettings."""
        phone = self.settings.value("phone", "")
        password = self.settings.value("password", "")
        remember = self.settings.value("remember", "false") == "true"
        
        if remember:
            self.phone_input.setText(phone)
            self.password_input.setText(password)
            self.remember_cb.setChecked(True)

    def save_settings(self):
        """Save or clear settings based on checkbox."""
        if self.remember_cb.isChecked():
            self.settings.setValue("phone", self.phone_input.text())
            self.settings.setValue("password", self.password_input.text())
            self.settings.setValue("remember", "true")
        else:
            self.settings.remove("phone")
            self.settings.remove("password")
            self.settings.setValue("remember", "false")

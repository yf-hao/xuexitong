import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QCheckBox, QWidget, QSizePolicy,
)
from PyQt6.QtCore import QByteArray, QCoreApplication, QSize, QThread, Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
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
    WINDOW_SIZE = (380, 380)

    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self._login_worker = None
        self._qr_worker = None
        self._password_login_success = False
        self._qrcode_login_success = False
        self._is_qrcode_mode = False
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(380, 360)
        
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
                font-size: 13px;
                background: transparent;
            }
            QLabel#form_label {
                font-size: 14px;
                font-weight: 500;
            }
            QLineEdit {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 10px;
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
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(6)

        self.theme_toggle_btn = QPushButton("☀️")
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.clicked.connect(self._toggle_theme)
        self.mode_switch_btn = QPushButton()
        self.mode_switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_switch_btn.clicked.connect(self._show_qrcode_login)
        self.mode_switch_btn.setFixedSize(32, 32)
        self.mode_switch_btn.setIconSize(QSize(24, 24))
        theme_row = QHBoxLayout()
        theme_row.addStretch()
        theme_row.addWidget(self.mode_switch_btn)
        theme_row.addWidget(self.theme_toggle_btn)
        layout.addLayout(theme_row)
        layout.addStretch()

        content_panel = QWidget()
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        self.password_panel = QWidget()
        password_layout = QVBoxLayout(self.password_panel)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(8)
        
        phone_label = QLabel("手机号：")
        phone_label.setObjectName("form_label")
        password_layout.addWidget(phone_label)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("请输入手机号")
        password_layout.addWidget(self.phone_input)
        
        password_label = QLabel("密码：")
        password_label.setObjectName("form_label")
        password_layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(self.password_input)

        password_layout.addSpacing(4)
        self.remember_cb = QCheckBox("记住手机号和密码")
        self.remember_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        password_layout.addWidget(self.remember_cb)
        content_layout.addWidget(self.password_panel)

        self.qrcode_panel = QWidget()
        qrcode_layout = QVBoxLayout(self.qrcode_panel)
        qrcode_layout.setContentsMargins(0, 0, 0, 0)
        qrcode_layout.setSpacing(10)
        self.qrcode_panel.setMinimumHeight(260)
        self.qr_label = QLabel("正在获取二维码...")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(220, 220)
        qrcode_layout.addWidget(
            self.qr_label, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self.qr_status_label = QLabel("请使用学习通 App 扫码登录")
        self.qr_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_status_label.setMinimumHeight(20)
        qrcode_layout.addWidget(self.qr_status_label)
        self.qr_refresh_btn = QPushButton("刷新二维码")
        self.qr_refresh_btn.setFlat(True)
        self.qr_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qr_refresh_btn.clicked.connect(self._start_qrcode_login)
        self.qr_refresh_btn.hide()
        qrcode_layout.addWidget(self.qr_refresh_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.qrcode_panel.hide()
        content_layout.addWidget(self.qrcode_panel)
        
        # Load saved settings
        self.settings = QSettings("HaoSoft", "XuexitongManager")
        self.load_settings()
        
        self.status_label = QLabel("")
        apply_theme_stylesheet(self.status_label, "color: #ff5252; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.status_label.setFixedHeight(20)
        self.status_label.hide()
        content_layout.addWidget(self.status_label)
        
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
        content_layout.addWidget(self.login_btn)
        layout.addWidget(content_panel)
        layout.addStretch()
        
        self.setLayout(layout)
        # 根据内容计算初始尺寸并锁定，模式切换时会重新计算。
        self.setFixedSize(*self.WINDOW_SIZE)
        theme_manager().theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager().mode)
        self._apply_mode_button_style()

    def _toggle_theme(self):
        mode = theme_manager().mode
        theme_manager().set_mode("dark" if mode == "light" else "light")

    def _apply_theme(self, mode):
        if mode == "light":
            svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
                <path d="M9.72 4.09A9 9 0 1 0 19.91 14.28A7.4 7.4 0 0 1 9.72 4.09z" fill="#d19a00" stroke="#d19a00" stroke-width="0.6" stroke-linejoin="round"/>
            </svg>"""
            self.theme_toggle_btn.setToolTip("切换到暗色主题")
        else:
            svg = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="4.2" fill="#f5b301"/>
                <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" stroke="#f5b301" stroke-width="2" stroke-linecap="round"/>
            </svg>"""
            self.theme_toggle_btn.setToolTip("切换到亮色主题")
        self.theme_toggle_btn.setText("")
        self.theme_toggle_btn.setIconSize(QSize(24, 24))
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.theme_toggle_btn.setIcon(QIcon(pixmap))
        refresh_theme_styles(self, mode)
        self._update_mode_switch_icon()
        self._apply_mode_button_style()

    def _update_mode_switch_icon(self):
        palette = get_theme_palette(theme_manager().mode)
        icon_color = "#d19a00" if theme_manager().mode == "light" else "#f5b301"
        if self._is_qrcode_mode:
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="8" r="3.5" stroke="{icon_color}" stroke-width="2.1"/>
                <path d="M5 20c.7-3.6 3.2-5.5 7-5.5s6.3 1.9 7 5.5" stroke="{icon_color}" stroke-width="2.1" stroke-linecap="round"/>
            </svg>"""
            self.mode_switch_btn.setToolTip("切换到账号密码登录")
        else:
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">
                <g stroke="{icon_color}" stroke-width="1.8" stroke-linejoin="round">
                    <rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1.2"/>
                    <rect x="14" y="3.5" width="6.5" height="6.5" rx="1.2"/>
                    <rect x="3.5" y="14" width="6.5" height="6.5" rx="1.2"/>
                </g>
                <g fill="{icon_color}">
                    <rect x="5.7" y="5.7" width="2.1" height="2.1"/>
                    <rect x="16.2" y="5.7" width="2.1" height="2.1"/>
                    <rect x="5.7" y="16.2" width="2.1" height="2.1"/>
                    <rect x="14" y="14" width="2.6" height="2.6"/>
                    <rect x="18" y="14" width="2.5" height="2.6"/>
                    <rect x="16" y="18" width="2.6" height="2.5"/>
                    <rect x="14" y="19" width="1.5" height="1.5"/>
                    <rect x="18.5" y="18.5" width="2" height="2"/>
                </g>
            </svg>"""
            self.mode_switch_btn.setToolTip("切换到扫码登录")
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.mode_switch_btn.setIcon(QIcon(pixmap))

    def _apply_mode_button_style(self):
        palette = get_theme_palette(theme_manager().mode)
        icon_button_style = f"""
            QPushButton {{
                background-color: transparent;
                color: {palette.text_muted};
                border: none;
                border-radius: 16px;
                padding: 0;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
                font-size: 18px;
                font-weight: normal;
                margin-top: 0;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                color: {palette.text};
                border: none;
            }}
        """
        for button in (self.theme_toggle_btn, self.mode_switch_btn):
            apply_theme_stylesheet(button, icon_button_style)
        apply_theme_stylesheet(self.qr_refresh_btn, f"""
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
        self.status_label.hide()
        self._is_qrcode_mode = True
        self._update_mode_switch_icon()
        self.mode_switch_btn.clicked.disconnect()
        self.mode_switch_btn.clicked.connect(self._show_password_login)
        self.qrcode_panel.show()
        self._adjust_to_content()
        self._start_qrcode_login()

    def _show_password_login(self):
        self._stop_qrcode_worker()
        self.qrcode_panel.hide()
        self.password_panel.show()
        self.login_btn.show()
        self.status_label.setVisible(bool(self.status_label.text()))
        self._is_qrcode_mode = False
        self._update_mode_switch_icon()
        self.mode_switch_btn.clicked.disconnect()
        self.mode_switch_btn.clicked.connect(self._show_qrcode_login)
        self.status_label.clear()
        self._adjust_to_content()

    def _adjust_to_content(self):
        self.setFixedSize(*self.WINDOW_SIZE)

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
        self.qr_refresh_btn.setEnabled(True)

    def _on_qrcode_completed(self, success, error):
        self._qrcode_login_success = success
        if success:
            self.qr_status_label.setText("登录成功，正在进入系统...")
        elif self._qr_worker is not None and not self._qr_worker.stop_event.is_set():
            self.qr_status_label.setText(error or "二维码登录失败，请刷新重试")
            self.qr_refresh_btn.setEnabled(True)

    def _on_qrcode_worker_finished(self):
        worker = self.sender()
        is_current_worker = worker is self._qr_worker
        if is_current_worker:
            self._qr_worker = None
        if worker is not None:
            worker.deleteLater()
        if is_current_worker and self._qrcode_login_success:
            self.accept()

    def _stop_qrcode_worker(self):
        if self._qr_worker is not None and self._qr_worker.isRunning():
            worker = self._qr_worker
            worker.stop()
            worker.wait(5000)
            QCoreApplication.processEvents()
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
        self.status_label.show()
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
            self.status_label.show()
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

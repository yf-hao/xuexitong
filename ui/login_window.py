from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox
from PyQt6.QtCore import Qt, QSettings
from core.config import APP_TITLE
from ui.theme import apply_theme_stylesheet, refresh_theme_styles, theme_manager

class LoginWindow(QDialog):
    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
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

        theme_row = QHBoxLayout()
        theme_row.addStretch()
        self.theme_toggle_btn = QPushButton("☀️")
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.clicked.connect(self._toggle_theme)
        apply_theme_stylesheet(self.theme_toggle_btn, """
            QPushButton {
                background-color: #252526;
                color: #aaaaaa;
                border: 1px solid #3d3d3d;
                border-radius: 16px;
                padding: 0;
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
                font-size: 15px;
                font-weight: normal;
                margin-top: 0;
            }
            QPushButton:hover {
                background-color: #2a2d2e;
                color: #ffffff;
                border: 1px solid #007acc;
            }
        """)
        theme_row.addWidget(self.theme_toggle_btn)
        layout.addLayout(theme_row)
        
        title_label = QLabel("学习通登录")
        title_label.setObjectName("title_label")
        apply_theme_stylesheet(title_label, "margin-bottom: 15px;") # 标题离下方远一点
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        phone_label = QLabel("手机号：")
        layout.addWidget(phone_label)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("请输入手机号")
        layout.addWidget(self.phone_input)
        
        password_label = QLabel("密码：")
        layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        self.remember_cb = QCheckBox("记住手机号和密码")
        self.remember_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.remember_cb)
        
        # Load saved settings
        self.settings = QSettings("HaoSoft", "XuexitongManager")
        self.load_settings()
        
        self.status_label = QLabel("")
        apply_theme_stylesheet(self.status_label, "color: #ff5252; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.login_btn = QPushButton("立即登录")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)
        
        self.setLayout(layout)
        # 用 adjustSize 让布局根据真实字体/DPI 计算需要的高度，
        # 再锁成固定大小——避免 Windows 下中文字体偏高导致按钮被截断。
        self.adjustSize()
        self.setFixedSize(self.size())
        theme_manager().theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager().mode)

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

    def handle_login(self):
        phone = self.phone_input.text().strip()
        password = self.password_input.text().strip()
        
        if not phone or not password:
            self.status_label.setText("请输入完整的信息")
            return
            
        self.login_btn.setEnabled(False)
        self.status_label.setText("正在建立安全连接...")
        
        if self.crawler.login_by_password(phone, password):
            self.save_settings()
            self.accept()
        else:
            self.status_label.setText("身份验证失败，请重试")
            self.login_btn.setEnabled(True)

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

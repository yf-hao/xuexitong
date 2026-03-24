from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QCheckBox
from PyQt6.QtCore import Qt, QSettings
from core.config import APP_TITLE

class LoginWindow(QDialog):
    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(380, 420)
        
        # Dark Theme QSS for Login
        self.setStyleSheet("""
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
        
        title_label = QLabel("学习通登录")
        title_label.setObjectName("title_label")
        title_label.setStyleSheet("margin-bottom: 15px;") # 标题离下方远一点
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
        self.status_label.setStyleSheet("color: #ff5252; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        self.login_btn = QPushButton("立即登录")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)
        
        self.setLayout(layout)

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

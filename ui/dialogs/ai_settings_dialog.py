"""大模型 AI 配置设置弹窗"""
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QTextEdit, QPushButton, QMessageBox, QFormLayout, QFrame, QComboBox
)
from ui.theme import apply_theme_stylesheet
from core.apis.ai_service import DiscreteMathAIService

class AITestWorker(QThread):
    """用于异步测试 AI API 连接的后台线程"""
    finished = pyqtSignal(bool, str)

    def __init__(self, service, api_key, base_url, model, endpoint_type):
        super().__init__()
        self.service = service
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.endpoint_type = endpoint_type

    def run(self):
        # 临时将当前填写的配置应用到测试中，不影响真正的磁盘保存
        orig_key = self.service.api_key
        orig_url = self.service.base_url
        orig_model = self.service.model
        orig_endpoint_type = self.service.endpoint_type
        
        self.service.api_key = self.api_key
        self.service.base_url = self.base_url
        self.service.model = self.model
        self.service.endpoint_type = self.endpoint_type
        
        try:
            success, msg = self.service.test_connection()
            self.finished.emit(success, msg)
        finally:
            # 还原原有内存配置
            self.service.api_key = orig_key
            self.service.base_url = orig_url
            self.service.model = orig_model
            self.service.endpoint_type = orig_endpoint_type

class AISettingsDialog(QDialog):
    """AI 大模型助手配置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = DiscreteMathAIService()
        self.test_worker = None
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        self.setWindowTitle("生成式 AI 助手设置")
        self.resize(580, 480)
        self.setModal(True)
        
        # 使用统一暗色系样式
        apply_theme_stylesheet(self, """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e6e6e6;
                font-size: 13px;
            }
            QLineEdit, QTextEdit {
                background-color: #252526;
                color: #e6e6e6;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px;
                font-family: Consolas, "Courier New", monospace;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton#save_btn {
                background-color: #007acc;
            }
            QPushButton#save_btn:hover {
                background-color: #005c99;
            }
            QPushButton#test_btn {
                background-color: #2d7d46;
            }
            QPushButton#test_btn:hover {
                background-color: #225e35;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #777777;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_label = QLabel("配置大模型 AI 接口（支持 DeepSeek / OpenAI / 聚合接口）")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #007acc;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Base URL
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("例如: https://api.deepseek.com/v1")
        form_layout.addRow("接口地址 (Base URL):", self.url_input)

        # API Key
        key_layout = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("请输入 API Key (例如 sk-...)")
        key_layout.addWidget(self.key_input, stretch=1)
        
        self.show_key_btn = QPushButton("👁️")
        self.show_key_btn.setFixedSize(30, 28)
        self.show_key_btn.setStyleSheet("padding: 2px; font-size: 14px;")
        self.show_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show_key_btn.clicked.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.show_key_btn)
        form_layout.addRow("接口密钥 (API Key):", key_layout)

        # Model
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("例如: deepseek-chat")
        form_layout.addRow("大模型名称 (Model):", self.model_input)

        self.endpoint_combo = QComboBox()
        self.endpoint_combo.addItem("/v1/chat/completions", "chat_completions")
        self.endpoint_combo.addItem("/v1/responses", "responses")
        form_layout.addRow("接口类型:", self.endpoint_combo)

        # Prompt
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("请输入系统提示词，规范 AI 的解题行为与回复风格。")
        form_layout.addRow("系统提示词 (Prompt):", self.prompt_input)

        layout.addLayout(form_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3d3d3d;")
        layout.addWidget(line)

        # 底部按钮栏
        btn_layout = QHBoxLayout()
        
        # 左侧测试按钮
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("test_btn")
        self.test_btn.clicked.connect(self._on_test_clicked)
        btn_layout.addWidget(self.test_btn)
        
        btn_layout.addStretch()

        # 右侧取消与保存按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = QPushButton("保存配置")
        self.save_btn.setObjectName("save_btn")
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _load_current_settings(self):
        """填充当前配置"""
        self.url_input.setText(self.service.base_url)
        self.key_input.setText(self.service.api_key)
        self.model_input.setText(self.service.model)
        index = self.endpoint_combo.findData(self.service.endpoint_type)
        self.endpoint_combo.setCurrentIndex(index if index >= 0 else 0)
        self.prompt_input.setPlainText(self.service.system_prompt)

    def _toggle_key_visibility(self):
        """显示/隐藏 API Key"""
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_key_btn.setText("🔒")
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key_btn.setText("👁️")

    def _on_test_clicked(self):
        """异步测试网络连接"""
        api_key = self.key_input.text().strip()
        base_url = self.url_input.text().strip()
        model = self.model_input.text().strip()
        endpoint_type = self.endpoint_combo.currentData()

        if not api_key:
            QMessageBox.warning(self, "校验失败", "进行测试前请输入 API Key！")
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")

        self.test_worker = AITestWorker(self.service, api_key, base_url, model, endpoint_type)
        self.test_worker.finished.connect(self._on_test_finished)
        self.test_worker.start()

    def _on_test_finished(self, success, msg):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        
        if success:
            QMessageBox.information(self, "测试成功", msg)
        else:
            QMessageBox.critical(self, "连接失败", msg)

    def _on_save_clicked(self):
        """保存配置并关闭"""
        self.service.base_url = self.url_input.text().strip()
        self.service.api_key = self.key_input.text().strip()
        self.service.model = self.model_input.text().strip()
        self.service.endpoint_type = self.endpoint_combo.currentData()
        self.service.system_prompt = self.prompt_input.toPlainText().strip()

        if self.service.save_config():
            QMessageBox.information(self, "成功", "AI 配置参数保存成功！")
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "保存配置文件失败，请检查写入权限。")

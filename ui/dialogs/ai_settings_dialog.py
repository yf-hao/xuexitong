"""大模型 AI 配置设置弹窗"""
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QTextEdit, QPushButton, QMessageBox, QFormLayout, QFrame, QComboBox
)
from ui.theme import apply_theme_stylesheet, bind_theme_tree
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
        
        apply_theme_stylesheet(self, lambda palette: f"""
            QDialog {{
                background-color: {palette.window_bg};
            }}
            QLabel {{
                color: {palette.text};
                font-size: 13px;
            }}
            QLineEdit, QTextEdit {{
                background-color: {palette.input_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 6px;
                font-family: Consolas, "Courier New", monospace;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {palette.accent_focus};
            }}
            QComboBox {{
                background-color: {palette.input_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 5px 8px;
            }}
            QComboBox:hover {{
                border: 1px solid {palette.border_strong};
            }}
            QComboBox:focus {{
                border: 1px solid {palette.accent_focus};
            }}
            QComboBox QAbstractItemView {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                border: 1px solid {palette.border_strong};
            }}
            QPushButton#save_btn {{
                background-color: {palette.accent};
                color: #ffffff;
                border: 1px solid {palette.accent};
            }}
            QPushButton#save_btn:hover {{
                background-color: {palette.accent_hover};
                border: 1px solid {palette.accent_hover};
            }}
            QPushButton#test_btn {{
                background-color: {palette.success};
                color: #ffffff;
                border: 1px solid {palette.success};
            }}
            QPushButton#test_btn:hover {{
                background-color: {palette.success_hover};
                border: 1px solid {palette.success_hover};
            }}
            QPushButton#show_key_btn {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text_muted};
                border: 1px solid {palette.border};
                min-width: 0;
                padding: 2px;
            }}
            QPushButton#show_key_btn:hover {{
                background-color: {palette.hover_bg};
                color: {palette.text};
            }}
            QPushButton:disabled {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
                border: 1px solid {palette.border};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_label = QLabel("配置大模型 AI 接口（支持 DeepSeek / OpenAI / 聚合接口）")
        apply_theme_stylesheet(
            title_label,
            lambda palette: f"font-weight: bold; font-size: 14px; color: {palette.accent};",
        )
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
        self.show_key_btn.setObjectName("show_key_btn")
        self.show_key_btn.setFixedSize(30, 28)
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
        apply_theme_stylesheet(line, lambda palette: f"background-color: {palette.border};")
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
        bind_theme_tree(self)

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

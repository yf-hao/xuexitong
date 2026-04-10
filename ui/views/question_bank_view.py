"""
题库管理视图 - 支持文件夹管理和 Markdown 文件上传
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFrame, QFileDialog, QMenu, QDialog,
    QLineEdit, QDialogButtonBox, QMessageBox, QSplitter, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QIcon, QAction


# 示例文件夹数据
SAMPLE_FOLDERS = [
    {
        "id": "1",
        "name": "全部题目",
        "count": 128,
        "children": [
            {
                "id": "1-1",
                "name": "第一章 绪论",
                "count": 25,
                "children": [
                    {"id": "1-1-1", "name": "1.1 概念", "count": 10, "children": []},
                    {"id": "1-1-2", "name": "1.2 历史", "count": 8, "children": []},
                    {"id": "1-1-3", "name": "1.3 发展", "count": 7, "children": []},
                ]
            },
            {
                "id": "1-2",
                "name": "第二章 基础",
                "count": 35,
                "children": [
                    {"id": "1-2-1", "name": "2.1 变量", "count": 12, "children": []},
                    {"id": "1-2-2", "name": "2.2 数据类型", "count": 15, "children": []},
                    {"id": "1-2-3", "name": "2.3 运算符", "count": 8, "children": []},
                ]
            },
            {
                "id": "1-3",
                "name": "第三章 进阶",
                "count": 40,
                "children": [
                    {"id": "1-3-1", "name": "3.1 函数", "count": 20, "children": []},
                    {"id": "1-3-2", "name": "3.2 类与对象", "count": 20, "children": []},
                ]
            },
            {
                "id": "1-4",
                "name": "第四章 高级",
                "count": 28,
                "children": []
            },
        ]
    }
]


class CreateFolderDialog(QDialog):
    """新建文件夹对话框"""
    
    def __init__(self, parent_folder: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建文件夹")
        self.setFixedWidth(400)
        self.setup_ui(parent_folder)
    
    def setup_ui(self, parent_folder: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 父级文件夹（只读显示）
        parent_label = QLabel("父级文件夹:")
        self.parent_display = QLineEdit(parent_folder)
        self.parent_display.setReadOnly(True)
        self.parent_display.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d30;
                color: #888888;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(parent_label)
        layout.addWidget(self.parent_display)
        
        # 文件夹名称
        name_label = QLabel("文件夹名称:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("请输入文件夹名称")
        self.name_input.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3a3f44;
                border-radius: 4px;
                padding: 8px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
            QPushButton[text="Cancel"] {
                background-color: #3e3e42;
            }
        """)
        layout.addWidget(button_box)
    
    def get_folder_name(self) -> str:
        return self.name_input.text().strip()


class QuestionBankView(QWidget):
    """题库管理视图"""
    
    # 信号：上传完成
    upload_finished = pyqtSignal(bool, str)  # success, message
    status_update = pyqtSignal(str)  # status message
    
    def __init__(self, crawler=None, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.current_folder_id = None
        self.current_folder_path = ""
        self._folder_items = {}  # 存储 id -> QTreeWidgetItem 的映射
        self._folder_data = {}   # 存储完整的文件夹数据
        self.setup_ui()
        # 不自动加载示例数据，等待 on_show 调用
    
    def setup_ui(self):
        """设置界面布局"""
        self.setStyleSheet("background-color: #1e1e1e;")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 使用 Splitter 分割左右区域
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：文件夹树
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)

        # 右侧：题目列表展示区（预留接口）
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)

        # 设置分割比例
        splitter.setSizes([350, 650])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
    
    def create_left_panel(self) -> QWidget:
        """创建左侧文件夹面板"""
        panel = QFrame()
        panel.setMinimumWidth(150)  # 最小宽度，允许拖拽调整
        panel.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-right: 1px solid #3e3e42;
            }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 0, 10)  # 右边距0，滚动条贴边
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("📚 文件夹")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
                margin-right: 10px;
            }
        """)
        layout.addWidget(title)
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索文件夹...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px 10px;
                margin-right: 10px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """)
        self.search_input.textChanged.connect(self.filter_folders)
        layout.addWidget(self.search_input)
        
        # 文件夹树
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setStyleSheet("""
            QTreeWidget {
                background-color: transparent;
                color: #cccccc;
                border: none;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 5px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
        """)
        self.folder_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self.show_folder_menu)
        self.folder_tree.itemClicked.connect(self.on_folder_selected)
        layout.addWidget(self.folder_tree)

        return panel

    def create_right_panel(self) -> QWidget:
        """创建右侧题目列表展示面板（预留接口）"""
        panel = QFrame()
        panel.setStyleSheet("background-color: #1e1e1e;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 标题
        self.question_title = QLabel("📝 题目列表")
        self.question_title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.question_title)

        # 开发中提示
        self.dev_hint = QLabel("🚧 开发中...")
        self.dev_hint.setStyleSheet("""
            QLabel {
                color: #ff9800;
                font-size: 24px;
                font-weight: bold;
                padding: 50px;
            }
        """)
        self.dev_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.dev_hint)

        # 题目列表占位区域（未来用于展示题目）
        self.question_list = QTreeWidget()
        self.question_list.setHeaderLabels(["题号", "题目内容", "类型", "难度"])
        self.question_list.setColumnWidth(0, 60)
        self.question_list.setColumnWidth(1, 400)
        self.question_list.setColumnWidth(2, 80)
        self.question_list.setColumnWidth(3, 80)
        self.question_list.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #ffffff;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
            }
        """)
        # 连接点击事件
        self.question_list.itemClicked.connect(self._on_question_clicked)
        layout.addWidget(self.question_list)

        # 提示标签
        self.hint_label = QLabel("💡 选择左侧文件夹后，题目将显示在此处")
        self.hint_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 13px;
                padding: 20px;
            }
        """)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

        # 操作按钮区域（预留）
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_questions)
        btn_layout.addWidget(self.btn_refresh)

        layout.addLayout(btn_layout)

        return panel

    def _on_refresh_questions(self):
        """刷新题目列表（预留接口）"""
        self.status_update.emit("刷新题目列表...")
        # TODO: 实现题目加载逻辑
    
    def display_questions(self, questions: list, folder_path: str = ""):
        """显示题目列表"""
        self.question_list.clear()
        
        # 更新标题
        self.question_title.setText(f"📝 题目列表 - {folder_path}")
        self.dev_hint.setVisible(False)
        
        # 添加题目
        for i, q in enumerate(questions, start=1):
            # 格式化正确率显示
            accuracy_text = f"{q['accuracy']:.1f}%" if q.get('accuracy') is not None else "-"
            
            # 格式化难度显示
            difficulty_text = f"{q.get('difficulty', 0.5)} ({'易' if q.get('difficulty', 0.5) >= 0.8 else '中' if q.get('difficulty', 0.5) >= 0.2 else '难'})"
            
            # 创建树节点
            item = QTreeWidgetItem([
                str(i),  # 序号
                q.get('content', '')[:100] + "..." if len(q.get('content', '')) > 100 else q.get('content', ''),
                q.get('question_type', '未知'),  # 题型
                difficulty_text,  # 难度
                str(q.get('usage_count', 0)),  # 使用量
                accuracy_text,  # 正确率
                q.get('author', ''),  # 作者
                q.get('create_time', '')  # 创建时间
            ])
            
            # 存储题目数据
            item.setData(0, Qt.ItemDataRole.UserRole, q.get('id'))
            item.setData(1, Qt.ItemDataRole.UserRole, q)  # 完整题目数据
            
            self.question_list.addTopLevelItem(item)
        
        # 更新提示标签
        if questions:
            self.hint_label.setText(f"💡 共找到 {len(questions)} 道题目")
        else:
            self.hint_label.setText("💡 当前文件夹暂无题目")

    def load_sample_folders(self):
        """加载示例文件夹数据（用于测试）"""
        self.folder_tree.clear()
        self._folder_items = {}
        self._folder_data = {}

        for folder in SAMPLE_FOLDERS:
            self._add_folder_item(None, folder)

    def load_folders(self):
        """从服务器加载真实文件夹数据"""
        if not self.crawler:
            self.status_update.emit("未初始化爬虫，加载示例数据")
            self.load_sample_folders()
            return

        self.status_update.emit("正在加载题库文件夹...")
        self.folder_tree.clear()
        self._folder_items = {}
        self._folder_data = {}

        # 添加根节点"全部题目"
        root_item = QTreeWidgetItem(["📁 全部题目"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, "root")
        self.folder_tree.addTopLevelItem(root_item)
        self._folder_items["root"] = root_item
        
        try:
            folders = self.crawler.get_question_folders()
            
            if not folders:
                self.status_update.emit("未找到题库文件夹")
                return
            
            # 检查是否有重复 ID
            seen_ids = set()
            unique_folders = []
            for folder in folders:
                fid = folder.get("id", "")
                if fid and fid not in seen_ids:
                    seen_ids.add(fid)
                    unique_folders.append(folder)
                else:
                    print(f"DEBUG: 发现重复文件夹 ID: {fid}")
            
            print(f"DEBUG: 原始文件夹数: {len(folders)}, 去重后: {len(unique_folders)}")
            
            for folder in unique_folders:
                self._add_folder_item_from_data(root_item, folder)
            
            root_item.setExpanded(True)
            self.status_update.emit(f"已加载 {len(unique_folders)} 个题库文件夹")
            
        except Exception as e:
            self.status_update.emit(f"加载文件夹失败: {e}")
            print(f"加载题库文件夹错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _add_folder_item_from_data(self, parent: QTreeWidgetItem, folder_data: dict):
        """从服务器数据添加文件夹项"""
        folder_id = folder_data.get("id", "")
        name = folder_data.get("name", "未命名")
        count = folder_data.get("count", 0)

        item = QTreeWidgetItem([f"📁 {name} ({count})"])
        item.setData(0, Qt.ItemDataRole.UserRole, folder_id)

        # 存储映射
        self._folder_items[folder_id] = item
        self._folder_data[folder_id] = folder_data

        if parent:
            parent.addChild(item)
        else:
            self.folder_tree.addTopLevelItem(item)

        item.setExpanded(True)

    def on_show(self):
        """视图显示时调用"""
        self.load_folders()

    def _add_folder_item(self, parent: QTreeWidgetItem, folder_data: dict):
        """递归添加文件夹项"""
        item = QTreeWidgetItem([f"📁 {folder_data['name']} ({folder_data['count']})"])
        item.setData(0, Qt.ItemDataRole.UserRole, folder_data['id'])

        # 存储映射
        self._folder_items[folder_data['id']] = item

        if parent:
            parent.addChild(item)
        else:
            self.folder_tree.addTopLevelItem(item)

        # 递归添加子文件夹
        for child in folder_data.get('children', []):
            self._add_folder_item(item, child)

        item.setExpanded(True)
    
    def _get_folder_path(self, item: QTreeWidgetItem) -> str:
        """获取文件夹路径"""
        if not item:
            return ""
        path_parts = []
        current = item
        while current:
            text = current.text(0)
            # 移除图标和数量
            name = text.replace("📁 ", "").rsplit(" (", 1)[0]
            path_parts.insert(0, name)
            current = current.parent()
        return " > ".join(path_parts) + " > "
    
    def show_folder_menu(self, position):
        """显示文件夹右键菜单"""
        item = self.folder_tree.itemAt(position)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
        """)
        
        if item:
            # 右键点击文件夹
            add_action = menu.addAction("📁 新建子文件夹")
            menu.addSeparator()
            rename_action = menu.addAction("✏️ 重命名")
            delete_action = menu.addAction("🗑️ 删除文件夹")
            menu.addSeparator()
            upload_action = menu.addAction("📤 上传题目到此文件夹")
            
            add_action.triggered.connect(lambda: self.create_subfolder(item))
            rename_action.triggered.connect(lambda: self.rename_folder(item))
            delete_action.triggered.connect(lambda: self.delete_folder(item))
            upload_action.triggered.connect(lambda: self.upload_to_folder(item))
        else:
            # 右键点击空白区域
            add_action = menu.addAction("📁 新建根文件夹")
            refresh_action = menu.addAction("🔄 刷新文件夹列表")
            
            add_action.triggered.connect(self.create_root_folder)
            refresh_action.triggered.connect(self.load_sample_folders)
        
        menu.exec(self.folder_tree.mapToGlobal(position))
    
    def on_folder_selected(self, item: QTreeWidgetItem):
        """选中文件夹时的处理"""
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.current_folder_id = folder_id
        self.current_folder_path = self._get_folder_path(item).rstrip(" > ")

        # 更新状态
        self.status_update.emit(f"已选择文件夹: {self.current_folder_path}")

        # 加载子文件夹（如果尚未加载）
        self._load_subfolders(item)

    def _load_subfolders(self, item: QTreeWidgetItem):
        """加载子文件夹和题目"""
        # 检查是否已经加载过子文件夹
        if item.data(0, Qt.ItemDataRole.UserRole + 1):  # 使用 UserRole+1 存储加载状态
            return

        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_id or folder_id.startswith("new-"):
            # 新建的文件夹，标记为已加载
            item.setData(0, Qt.ItemDataRole.UserRole + 1, True)
            return

        # 标记为正在加载
        item.setData(0, Qt.ItemDataRole.UserRole + 1, True)

        # 获取子文件夹和题目
        try:
            # 特殊处理：root 节点
            # - 不需要再加载子文件夹（已由 load_folders 加载）
            # - 但需要加载根目录下的题目
            if folder_id == "root":
                # 使用 "0" 作为根目录 ID 来获取题目
                result = self.crawler.get_question_subfolders("0")
                if result:
                    questions = result.get("questions", [])
                    self.display_questions(questions, self.current_folder_path)
                return

            result = self.crawler.get_question_subfolders(folder_id)
            
            if not result:
                return
            
            # 处理子文件夹
            subfolders = result.get("folders", [])
            if subfolders:
                # 检查是否已存在相同 ID 的文件夹
                existing_ids = set()
                for i in range(item.childCount()):
                    child_item = item.child(i)
                    existing_ids.add(child_item.data(0, Qt.ItemDataRole.UserRole))

                for sf in subfolders:
                    if sf['id'] not in existing_ids:
                        child = QTreeWidgetItem([f"📁 {sf['name']} ({sf['count']})"])
                        child.setData(0, Qt.ItemDataRole.UserRole, sf['id'])
                        child.setData(0, Qt.ItemDataRole.UserRole + 1, False)  # 子文件夹未加载
                        item.addChild(child)

                        # 存储映射
                        self._folder_items[sf['id']] = child

                item.setExpanded(True)
                self.status_update.emit(f"已加载 {len(subfolders)} 个子文件夹")
            
            # 处理题目列表（无论有无题目都更新显示，避免显示旧数据）
            questions = result.get("questions", [])
            self.display_questions(questions, self.current_folder_path)

        except Exception as e:
            print(f"加载子文件夹和题目失败: {e}")
            # 加载失败，重置状态以便下次重试
            item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
    
    def create_root_folder(self):
        """创建根文件夹"""
        dialog = CreateFolderDialog("根目录", self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_folder_name()
            if name:
                if not self.crawler:
                    self.status_update.emit("未初始化爬虫，无法创建文件夹")
                    return
                
                # 调用 API 创建 (pid="0" 表示根目录)
                result = self.crawler.create_question_folder(name, parent_id="0")
                
                if result.get("success"):
                    folder_id = result.get("id", "")
                    # 在 "全部题目" 下添加新文件夹
                    root_item = self._folder_items.get("root")
                    if root_item:
                        item = QTreeWidgetItem([f"📁 {name} (0)"])
                        item.setData(0, Qt.ItemDataRole.UserRole, folder_id)
                        item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # 已加载（无子文件夹）
                        root_item.addChild(item)
                        root_item.setExpanded(True)

                        # 存储映射
                        self._folder_items[folder_id] = item

                    self.status_update.emit(f"已创建文件夹: {name}")
                else:
                    QMessageBox.warning(self, "创建失败", result.get("msg", "无法创建文件夹"))
                    self.status_update.emit(f"创建文件夹失败: {name}")

    def create_subfolder(self, parent_item: QTreeWidgetItem):
        """创建子文件夹"""
        parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
        parent_path = self._get_folder_path(parent_item).rstrip(" > ")

        # 确定父文件夹 ID
        # "root" 节点下创建的文件夹，pid 应该是 "0"（根目录）
        if parent_id == "root":
            api_parent_id = "0"
        elif not parent_id or parent_id.startswith("new-"):
            QMessageBox.warning(self, "提示", "请先选择一个有效的父文件夹")
            return
        else:
            api_parent_id = parent_id

        dialog = CreateFolderDialog(parent_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.get_folder_name()
            if name:
                if not self.crawler:
                    self.status_update.emit("未初始化爬虫，无法创建文件夹")
                    return

                # 调用 API 创建
                result = self.crawler.create_question_folder(name, parent_id=api_parent_id)

                if result.get("success"):
                    folder_id = result.get("id", "")
                    # 创建新项
                    item = QTreeWidgetItem([f"📁 {name} (0)"])
                    item.setData(0, Qt.ItemDataRole.UserRole, folder_id)
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # 已加载（无子文件夹）
                    parent_item.addChild(item)
                    parent_item.setExpanded(True)

                    # 存储映射
                    self._folder_items[folder_id] = item

                    full_path = parent_path + " > " + name
                    self.status_update.emit(f"已创建子文件夹: {full_path}")
                else:
                    QMessageBox.warning(self, "创建失败", result.get("msg", "无法创建文件夹"))
                    self.status_update.emit(f"创建子文件夹失败: {name}")
    
    def rename_folder(self, item: QTreeWidgetItem):
        """重命名文件夹"""
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # 检查是否是新建的本地文件夹
        if not folder_id or folder_id.startswith("new-"):
            QMessageBox.warning(self, "提示", "此文件夹尚未同步到服务器")
            return
        
        # 检查是否是 root 节点
        if folder_id == "root":
            QMessageBox.warning(self, "提示", "不能重命名根节点")
            return
        
        current_text = item.text(0)
        current_name = current_text.replace("📁 ", "").rsplit(" (", 1)[0]
        
        new_name, ok = QInputDialog.getText(
            self, "重命名文件夹", "请输入新的文件夹名称:", text=current_name
        )
        
        if ok and new_name and new_name != current_name:
            if not self.crawler:
                self.status_update.emit("未初始化爬虫，无法重命名")
                return
            
            # 获取父文件夹 ID
            parent_item = item.parent()
            if parent_item:
                parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
                if parent_id == "root":
                    parent_id = "0"
            else:
                parent_id = "0"
            
            # 调用 API 重命名
            success = self.crawler.rename_question_folder(folder_id, new_name, parent_id)
            
            if success:
                # 更新 UI
                count = current_text.rsplit("(", 1)[-1].rstrip(")")
                item.setText(0, f"📁 {new_name} ({count})")
                self.status_update.emit(f"已重命名为: {new_name}")
                
                # 刷新当前层级的目录
                self._refresh_current_level(parent_item)
            else:
                QMessageBox.warning(self, "重命名失败", "无法重命名文件夹，请稍后重试")
                self.status_update.emit(f"重命名失败: {new_name}")
    
    def _refresh_current_level(self, parent_item: QTreeWidgetItem = None):
        """刷新当前层级的目录"""
        if parent_item is None:
            # 刷新根目录
            self.load_folders()
            return
        
        # 重置加载状态，下次点击时会重新加载
        parent_item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
        
        # 清空子节点
        while parent_item.childCount() > 0:
            parent_item.removeChild(parent_item.child(0))
        
        # 重新加载子文件夹
        self._load_subfolders(parent_item)
    
    def delete_folder(self, item: QTreeWidgetItem):
        """删除文件夹"""
        name = item.text(0).replace("📁 ", "")
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # 检查是否是新建的本地文件夹（未同步到服务器）
        if folder_id and folder_id.startswith("new-"):
            # 本地文件夹，直接删除 UI
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除文件夹 '{name}' 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    index = self.folder_tree.indexOfTopLevelItem(item)
                    self.folder_tree.takeTopLevelItem(index)
                self.status_update.emit(f"已删除文件夹: {name}")
            return
        
        # 服务器文件夹，需要调用 API
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除文件夹 '{name}' 吗？\n子文件夹和其中的题目也将被删除！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if not self.crawler:
                self.status_update.emit("未初始化爬虫，无法删除")
                return
            
            # 调用 API 删除
            success = self.crawler.delete_question_folder(folder_id)
            
            if success:
                # 从 UI 中移除
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    index = self.folder_tree.indexOfTopLevelItem(item)
                    self.folder_tree.takeTopLevelItem(index)
                
                # 从映射中移除
                if folder_id in self._folder_items:
                    del self._folder_items[folder_id]
                if folder_id in self._folder_data:
                    del self._folder_data[folder_id]
                
                self.status_update.emit(f"已删除文件夹: {name}")
            else:
                QMessageBox.warning(self, "删除失败", "无法删除文件夹，请稍后重试")
                self.status_update.emit(f"删除文件夹失败: {name}")
    
    def upload_to_folder(self, item: QTreeWidgetItem):
        """上传题目到此文件夹"""
        # 先选中文件夹
        self.on_folder_selected(item)
        
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # 检查文件夹有效性
        if not folder_id or folder_id == "root":
            QMessageBox.warning(self, "提示", "请选择一个有效的文件夹")
            return
        
        # 选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择题目文件",
            "",
            "题目文件 (*.md *.txt);;Markdown 文件 (*.md);;文本文件 (*.txt);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        self.selected_file = file_path
        
        # 解析文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            questions = self._parse_questions(content)
            
            if not questions:
                QMessageBox.warning(self, "提示", "未能解析到任何题目，请检查文件格式")
                return
            
            # 显示预览并确认
            preview_text = f"📁 目标文件夹: {self.current_folder_path}\n"
            preview_text += f"📄 文件: {file_path}\n"
            preview_text += f"📊 共解析到 {len(questions)} 道题目\n\n"
            
            for i, q in enumerate(questions[:3]):
                preview_text += f"{i+1}. {q['content'][:40]}{'...' if len(q['content']) > 40 else ''}\n"
                type_names = {0: '单选', 1: '多选', 2: '填空', 3: '判断'}
                display_answer = q.get('original_answer', q['answer'])
                preview_text += f"   类型: {type_names.get(q['q_type'], '未知')}  答案: {display_answer}\n\n"
            
            if len(questions) > 3:
                preview_text += f"... 还有 {len(questions) - 3} 道题目\n\n"
            
            preview_text += "确定上传吗？"
            
            reply = QMessageBox.question(
                self, "上传确认",
                preview_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # 开始上传
            if not self.crawler:
                QMessageBox.warning(self, "提示", "未初始化爬虫")
                return
            
            success_count = 0
            duplicate_count = 0
            fail_count = 0
            total = len(questions)
            
            # 获取文件所在目录作为图片基准目录
            import os
            base_dir = os.path.dirname(self.selected_file) if hasattr(self, 'selected_file') and self.selected_file else None
            
            for i, q in enumerate(questions):
                self.status_update.emit(f"正在上传第 {i+1}/{total} 道题目...")
                
                # 更新 UI（避免卡死）
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                result = self.crawler.add_question(folder_id, q, base_dir=base_dir)
                
                if result.get("success"):
                    success_count += 1
                    print(f"题目 {i+1} 上传成功")
                else:
                    # 检查是否是"题目已存在"
                    result_msg = result.get("msg", "")
                    if "已存在相同题目" in result_msg or "重复添加" in result_msg:
                        duplicate_count += 1
                        print(f"题目 {i+1} 已存在，跳过")
                    else:
                        fail_count += 1
                        print(f"题目 {i+1} 上传失败: {result_msg}")
            
            # 显示结果
            msg = f"上传完成！\n总共: {total} 道\n成功添加: {success_count} 道\n重复: {duplicate_count} 道\n失败: {fail_count} 道"
            self.status_update.emit(msg)
            QMessageBox.information(self, "上传完成", msg)
            
            # 刷新文件夹（更新题目数量）
            if success_count > 0:
                parent_item = item.parent()
                self._refresh_current_level(parent_item)
            
        except Exception as e:
            QMessageBox.warning(self, "上传失败", f"上传过程中出错: {e}")
            import traceback
            traceback.print_exc()

    def filter_folders(self, text: str):
        """过滤文件夹"""
        # 简单实现：隐藏不匹配的项
        text = text.lower()
        self._filter_items(self.folder_tree.invisibleRootItem(), text)
    
    def _filter_items(self, parent, text: str) -> bool:
        """递归过滤"""
        any_visible = False
        for i in range(parent.childCount()):
            item = parent.child(i)
            item_text = item.text(0).lower()
            
            # 检查子项
            children_visible = self._filter_items(item, text)
            
            # 当前项或子项匹配则显示
            visible = text in item_text or children_visible
            item.setHidden(not visible)
            
            if visible:
                any_visible = True
        
        return any_visible

    def _parse_questions(self, content: str) -> list:
        """解析题目内容：更稳健的题号切分，避免解析中的 1. 2. 被误识别"""
        import re

        if not content:
            return []

        lines = content.splitlines()
        num_pattern = re.compile(r'^\s*(\d+)\s*[、.．]\s*(.*)$')
        option_pattern = re.compile(r'^\s*([A-Ha-h])\s*[、.．:：]\s+.+$')
        answer_pattern = re.compile(r'^\s*(?:答案|正确答案)\s*[：:]\s*.+$')

        blocks = []
        current = []

        def flush():
            if current:
                block = "\n".join(current).strip()
                if block:
                    blocks.append(block)
            current.clear()

        total_lines = len(lines)
        for idx, line in enumerate(lines):
            m = num_pattern.match(line)
            if m:
                # look ahead 判断是否存在选项/答案，且在下一个题号前出现
                has_option_or_answer = False
                for la in lines[idx + 1:]:
                    if num_pattern.match(la):
                        break
                    la_strip = la.strip()
                    if option_pattern.match(la_strip) or answer_pattern.match(la_strip):
                        has_option_or_answer = True
                        break
                if has_option_or_answer:
                    flush()
                    current.append(line)
                    continue
            current.append(line)

        flush()

        questions = []
        for block in blocks:
            q = self._parse_single_question(block)
            if q:
                questions.append(q)
        return questions
    
    def _parse_single_question(self, text: str) -> dict:
        """解析单个题目"""
        import re

        def strip_md_emphasis(value: str) -> str:
            # 保留反引号，用于着重号标记（`text` -> <span style="text-emphasis: dot;">text</span>）
            if not value:
                return ""
            return value
        
        lines = text.splitlines()
        
        # 去掉首行题号前缀，如 "1."、"1、" 等
        if lines:
            num_prefix = re.compile(r'^\s*\d+\s*[、.．]\s*')
            lines[0] = num_prefix.sub('', lines[0], count=1)
        
        # 提取题目内容（第一个选项之前的内容）
        content_lines = []
        options = []
        answer = ""
        analysis_lines = []  # 保留多行解析原格式
        difficulty = 0.5  # 默认中等难度
        easy = 1  # 默认中等难度 (0=易, 1=中, 2=难)
        question_type_hint = ""  # 题型提示
        
        option_pattern = r'^\s*([A-Ha-h])\s*[、.．:：]\s*(.*)$'  # 改为 .* 支持选项后无内容（图片在下一行）
        answer_pattern = r'^\s*(?:答案|正确答案)\s*[：:]\s*(.+)$'  # 改为匹配任意答案
        analysis_pattern = r'^\s*(?:答案解析|解析|分析)\s*[：:]\s*(.+)$'
        difficulty_pattern = r'^\s*(?:难易程度|难度)\s*[：:]\s*(易|中|难|简单|较难|困难)'
        difficulty_value_pattern = r'^\s*难度系数\s*[：:]\s*([\d.]+)'  # 新增：匹配"难度系数：X.X"
        type_pattern = r'^\s*题型\s*[：:]\s*(.+)$'
        
        current_section = "content"
        in_code_block = False  # 跟踪是否在代码块内

        for line in lines:
            raw_line = line.rstrip('\r')

            # 检测代码块开始/结束
            if re.match(r"^\s*```", raw_line):
                in_code_block = not in_code_block
                # 保留代码块围栏标记，不做任何处理
                raw_line_clean = raw_line
            elif in_code_block:
                # 代码块内部：保留原始内容，不处理 Markdown 标记
                raw_line_clean = raw_line
            else:
                # 普通文本：处理 Markdown 标记
                raw_line_clean = strip_md_emphasis(raw_line)

            # 跳过分隔线行，如 ---
            if not in_code_block and raw_line_clean.strip() == "---":
                continue

            stripped = raw_line_clean.strip()

            # 跳过所有空行
            if not stripped:
                continue
            
            # 检查是否是题型
            type_match = re.match(type_pattern, stripped)
            if type_match:
                question_type_hint = type_match.group(1).strip()
                continue
            
            # 检查是否是选项（支持多行选项内容）
            opt_match = re.match(option_pattern, stripped)
            if opt_match:
                current_section = "options"
                opt_key = opt_match.group(1).upper()
                opt_value = strip_md_emphasis(opt_match.group(2)).strip()
                options.append({"key": opt_key, "value": opt_value})
                continue
            
            # 检查是否是答案
            ans_match = re.match(answer_pattern, stripped, re.IGNORECASE)
            if ans_match:
                current_section = "answer"
                answer = strip_md_emphasis(ans_match.group(1)).strip()  # 保留原始答案格式
                continue
            
            # 检查是否是解析
            ana_match = re.match(analysis_pattern, stripped)
            if ana_match:
                current_section = "analysis"
                analysis_lines.append(strip_md_emphasis(ana_match.group(1)).strip())
                continue
            
            # 检查是否是难度系数（优先级最高）
            diff_value_match = re.match(difficulty_value_pattern, stripped)
            if diff_value_match:
                difficulty = float(diff_value_match.group(1))
                # 根据 difficulty 值反推 easy
                if difficulty >= 0.8:
                    easy = 0  # 易
                elif difficulty <= 0.2:
                    easy = 2  # 难
                else:
                    easy = 1  # 中
                continue
            
            # 检查是否是难易程度
            diff_match = re.match(difficulty_pattern, stripped)
            if diff_match:
                diff_text = diff_match.group(1)
                if diff_text in ["易", "简单"]:
                    difficulty = 0.9
                    easy = 0
                elif diff_text in ["难", "较难", "困难"]:
                    difficulty = 0.2
                    easy = 2
                else:  # 中
                    difficulty = 0.5
                    easy = 1
                continue
            
            # 根据当前区域添加内容
            if current_section == "content":
                content_lines.append(raw_line_clean)
            elif current_section == "analysis":
                analysis_lines.append(raw_line_clean)
            elif current_section == "options" and options:
                # 追加多行选项内容，保留原始缩进
                prev = options[-1]["value"]
                options[-1]["value"] = (prev + "\n" + raw_line_clean) if prev else raw_line_clean
        
        # 构建题目数据
        content = "\n".join(content_lines)
        analysis = "\n".join(analysis_lines)
        
        if not content:
            return None
        
        # 判断题目类型
        # qType: 0=单选, 1=多选, 2=填空, 3=判断
        q_type = 0  # 默认单选
        
        # 先检查题型标记
        if "判断" in question_type_hint:
            q_type = 3  # 判断题
        elif "填空" in question_type_hint:
            q_type = 2  # 填空题
        elif "多选" in question_type_hint:
            q_type = 1  # 多选题
        elif "单选" in question_type_hint:
            q_type = 0  # 单选题
        elif not options:
            # 没有选项，通过答案判断是判断题还是填空题
            # 判断题答案通常是：对/错、正确/错误、是/否、T/F、True/False
            answer_lower = answer.lower().strip()
            true_keywords = ["对", "正确", "是", "true", "t", "√", "✓"]
            false_keywords = ["错", "错误", "否", "false", "f", "×", "✗"]
            
            is_true = any(kw in answer_lower for kw in true_keywords)
            is_false = any(kw in answer_lower for kw in false_keywords)
            
            if is_true or is_false:
                q_type = 3  # 判断题
            else:
                q_type = 2  # 填空题
        elif ',' in answer or '，' in answer:
            q_type = 1  # 多选
        
        # 如果是判断题，设置默认选项并标准化答案
        original_answer = answer  # 保留原始答案用于显示
        if q_type == 3:
            if not options:
                options = [{"key": "A", "value": "正确"}, {"key": "B", "value": "错误"}]
            # 标准化答案用于API提交
            answer_lower = answer.lower().strip()
            true_keywords = ["对", "正确", "是", "true", "t", "√", "✓"]
            if any(kw in answer_lower for kw in true_keywords):
                answer = "A"
                original_answer = "对"
            else:
                answer = "B"
                original_answer = "错"
        
        return {
            "content": content,
            "q_type": q_type,
            "options": options,
            "answer": answer,
            "original_answer": original_answer,  # 原始答案用于显示
            "analysis": analysis,
            "difficulty": difficulty,
            "easy": easy  # 难度等级 (0=易, 1=中, 2=难)
        }
    
    def _on_question_clicked(self, item: QTreeWidgetItem):
        """点击题目时的处理"""
        # 获取题目 ID
        question_id = item.data(0, Qt.ItemDataRole.UserRole)
        question_data = item.data(1, Qt.ItemDataRole.UserRole)
        
        if not question_id or not self.crawler:
            return
        
        # 获取当前文件夹 ID
        folder_id = self.current_folder_id
        if folder_id == "root":
            folder_id = "0"
        
        # 显示状态
        self.status_update.emit(f"正在加载题目详情...")
        
        try:
            # 调用 API 获取题目详情
            result = self.crawler.get_question_detail(question_id, folder_id)
            
            if result.get("success"):
                # 显示题目详情对话框
                dialog = QuestionDetailDialog(result, self)
                dialog.exec()
                self.status_update.emit("题目详情已加载")
            else:
                self.status_update.emit(f"加载题目详情失败: {result.get('msg', '未知错误')}")
                QMessageBox.warning(self, "加载失败", f"无法加载题目详情:\n{result.get('msg', '未知错误')}")
                
        except Exception as e:
            print(f"加载题目详情错误: {e}")
            self.status_update.emit(f"加载题目详情失败: {e}")


class QuestionDetailDialog(QDialog):
    """题目详情对话框 - 使用 QWebEngineView + 内置 KaTeX 渲染"""
    
    # KaTeX 资源路径
    _KATEX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "katex")
    
    def __init__(self, question_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("题目详情")
        self.setMinimumSize(850, 650)
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setup_ui(question_data)
    
    def setup_ui(self, question_data: dict):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #1e1e1e; border: none;")
        
        # 预处理：下载远程图片转为 base64 data URL
        processed_data = self._process_images(question_data)
        
        # 构建完整 HTML（包含内联 KaTeX）
        html = self._build_html(processed_data)
        self.web_view.setHtml(html, QUrl.fromLocalFile(self._KATEX_DIR + "/"))
        
        layout.addWidget(self.web_view)
        
        # 底部按钮栏
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background-color: #2d2d2d; border-top: 1px solid #3e3e42;")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(20, 8, 20, 8)
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addWidget(btn_bar)
    
    def _process_images(self, data: dict) -> dict:
        """下载 HTML 中的远程图片并转为 base64 data URL 嵌入"""
        import re
        import base64
        
        result = dict(data)
        
        def embed_images(html_content: str) -> str:
            if not html_content:
                return html_content
            img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
            for match in img_pattern.finditer(html_content):
                img_url = match.group(1)
                if img_url.startswith("data:") or not img_url.startswith("http"):
                    continue
                
                try:
                    import urllib.request
                    req = urllib.request.Request(img_url)
                    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
                    req.add_header("Referer", "https://mooc2-gray.chaoxing.com/")
                    resp = urllib.request.urlopen(req, timeout=15)
                    img_data = resp.read()
                    content_type = resp.info().get("Content-Type", "image/png").split(";")[0].strip()
                    b64_data = base64.b64encode(img_data).decode("utf-8")
                    new_src = f"data:{content_type};base64,{b64_data}"
                    html_content = html_content.replace(f'src="{img_url}"', f'src="{new_src}"')
                    print(f"  图片嵌入成功: {len(img_data)} bytes")  # debug
                except Exception as e:
                    print(f"  下载图片失败 {img_url[:60]}... : {e}")
            return html_content
        
        # 处理题干中的图片
        stem = result.get("stem", "")
        if stem:
            print(f"[DEBUG] 题干原始HTML长度: {len(stem)}")
            result["stem"] = embed_images(stem)
            print(f"[DEBUG] 题干处理后HTML长度: {len(result['stem'])}")
        
        # 处理解析中的图片
        analysis = result.get("analysis", "")
        if analysis:
            result["analysis"] = embed_images(analysis)
        
        # 处理选项中的图片
        options = result.get("options", [])
        new_options = []
        for opt in options:
            new_opt = dict(opt)
            if new_opt.get("content"):
                new_opt["content"] = embed_images(new_opt["content"])
            new_options.append(new_opt)
        result["options"] = new_options
        
        return result
    
    def _load_katex_js(self) -> str:
        """加载本地 KaTeX JS 文件"""
        katex_js_path = os.path.join(self._KATEX_DIR, "katex.min.js")
        auto_render_path = os.path.join(self._KATEX_DIR, "auto-render.min.js")
        
        katex_js = ""
        auto_render_js = ""
        
        try:
            with open(katex_js_path, "r", encoding="utf-8") as f:
                katex_js = f.read()
        except Exception as e:
            print(f"加载 katex.min.js 失败: {e}")
        
        try:
            with open(auto_render_path, "r", encoding="utf-8") as f:
                auto_render_js = f.read()
        except Exception as e:
            print(f"加载 auto-render.min.js 失败: {e}")
        
        return katex_js, auto_render_js
    
    def _load_katex_css(self) -> str:
        """加载本地 KaTeX CSS 文件"""
        katex_css_path = os.path.join(self._KATEX_DIR, "katex.min.css")
        
        try:
            with open(katex_css_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"加载 katex.min.css 失败: {e}")
            return ""
    
    def _build_html(self, data: dict) -> str:
        """构建完整的 HTML 页面，内联 KaTeX 资源"""
        import html as html_module
        
        stem = data.get("stem", "")
        options = data.get("options", [])
        answer = data.get("answer", "")
        analysis = data.get("analysis", "")
        difficulty = data.get("difficulty", "")
        question_type_info = data.get("question_type_info", "")
        
        # 加载本地 KaTeX
        katex_js, auto_render_js = self._load_katex_js()
        katex_css = self._load_katex_css()
        
        # 构建选项 HTML
        options_html = ""
        for opt in options:
            label = html_module.escape(opt.get("label", ""))
            content = opt.get("content", "")
            options_html += f"""
            <div class="option-item">
                <span class="option-label">{label}</span>
                <div class="option-content">{content}</div>
            </div>"""
        
        sections = ""
        
        # 题干
        if stem:
            type_info_html = f'<div class="type-info">{question_type_info}</div>' if question_type_info else ''
            sections += f"""
            <div class="section">
                <div class="section-title">📝 题干</div>
                <div class="stem-content">
                    {type_info_html}
                    {stem}
                </div>
            </div>"""
        
        # 选项
        if options:
            sections += f"""
            <div class="section">
                <div class="section-title">📋 选项</div>
                {options_html}
            </div>"""
        
        # 答案
        if answer:
            sections += f"""
            <div class="section">
                <div class="section-title">✅ 答案</div>
                <div class="answer-box">{answer}</div>
            </div>"""
        
        # 解析
        if analysis:
            sections += f"""
            <div class="section">
                <div class="section-title">📖 答案解析</div>
                <div class="analysis-content">{analysis}</div>
            </div>"""
        
        # 难度
        if difficulty:
            sections += f"""
            <div class="section">
                <div class="section-title">📊 难度</div>
                <div class="difficulty-text">{difficulty}</div>
            </div>"""
        
        # 构建完整 HTML（KaTeX JS/CSS 内联，字体用本地文件）
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>{katex_css}</style>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            background-color: #1e1e1e;
            color: #cccccc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            line-height: 1.8;
            padding: 24px;
        }}
        .section {{
            margin-bottom: 24px;
        }}
        .section-title {{
            color: #569cd6;
            font-size: 16px;
            font-weight: bold;
            margin-bottom: 12px;
            padding-bottom: 6px;
            border-bottom: 1px solid #3e3e42;
        }}
        .stem-content {{
            background-color: #252526;
            border: 1px solid #3e3e42;
            border-radius: 6px;
            padding: 16px;
        }}
        .stem-content p {{
            margin: 6px 0;
        }}
        .stem-content img {{
            max-width: 100%;
            vertical-align: middle;
        }}
        .type-info {{
            color: #9cdcfe;
            font-size: 13px;
            margin-bottom: 8px;
        }}
        .option-item {{
            display: flex;
            align-items: flex-start;
            background-color: #252526;
            border: 1px solid #3e3e42;
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 8px;
        }}
        .option-label {{
            font-weight: bold;
            color: #dcdcaa;
            min-width: 28px;
            margin-right: 8px;
        }}
        .option-content {{
            flex: 1;
        }}
        .option-content img {{
            max-width: 100%;
            vertical-align: middle;
        }}
        .option-content p {{
            margin: 2px 0;
        }}
        .answer-box {{
            background-color: #1e4620;
            border: 2px solid #4caf50;
            border-radius: 6px;
            padding: 12px 16px;
            font-size: 16px;
            font-weight: bold;
            color: #4caf50;
        }}
        .analysis-content {{
            background-color: #252526;
            border: 1px solid #3e3e42;
            border-radius: 6px;
            padding: 16px;
        }}
        .analysis-content p {{
            margin: 6px 0;
        }}
        .analysis-content img {{
            max-width: 100%;
            vertical-align: middle;
        }}
        .difficulty-text {{
            color: #cccccc;
            font-size: 14px;
        }}
        .katex-display {{
            margin: 10px 0;
            overflow-x: auto;
        }}
        /* KaTeX 公式在深色主题下的颜色 */
        .katex {{
            color: #cccccc;
            font-size: 1.1em;
        }}
    </style>
</head>
<body>
    {sections}

    <script>{katex_js}</script>
    <script>{auto_render_js}</script>
    <script>
        window.onload = function() {{
            try {{
                console.log("KaTeX: 开始渲染数学公式...");
                
                // 预处理：修复多行 $$ 块
                // 超星的 HTML 中 $$ 与 LaTeX 内容之间可能有换行、<p> 标签等
                // 策略：找到所有 $$...$$ 块，剥离中间的 HTML 标签和空白，只保留纯文本内容
                var html = document.body.innerHTML;
                var fixedCount = 0;
                
                // 匹配 $$ 开头，中间有任意内容（含HTML标签），以 $$ 结尾的块
                html = html.replace(/\$\$([\s\S]*?)\$\$/g, function(match, inner) {{
                    // 剥离所有HTML标签，只保留文本内容
                    var tempDiv = document.createElement('div');
                    tempDiv.innerHTML = inner;
                    var text = tempDiv.textContent || tempDiv.innerText || '';
                    var trimmed = text.trim();
                    if (!trimmed) return match;  // 内容为空则不修改
                    
                    fixedCount++;
                    return '$$' + trimmed + '$$';
                }});
                if (fixedCount > 0) {{
                    document.body.innerHTML = html;
                    console.log("KaTeX: 修复了 " + fixedCount + " 个多行 $$ 公式块");
                }}
                
                var count = 0;
                renderMathInElement(document.body, {{
                    delimiters: [
                        {{left: "$$", right: "$$", display: true}},
                        {{left: "$", right: "$", display: false}},
                        {{left: "\\\\(", right: "\\\\)", display: false}},
                        {{left: "\\\\[", right: "\\\\]", display: true}}
                    ],
                    throwOnError: false,
                    preProcess: function(data) {{ count++; return data; }}
                }});
                console.log("KaTeX: 渲染完成, 处理了 " + count + " 个节点");
            }} catch(e) {{
                console.error("KaTeX 渲染错误:", e);
                document.body.innerHTML += '<div style="color:red;border:1px solid red;padding:10px;margin-top:20px;">KaTeX 渲染出错: ' + e.message + '</div>';
            }}
        }};
    </script>
</body>
</html>"""

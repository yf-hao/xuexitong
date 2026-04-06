"""
题库管理视图 - 支持文件夹管理和 Markdown 文件上传
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFrame, QFileDialog, QMenu, QDialog,
    QLineEdit, QDialogButtonBox, QMessageBox, QSplitter, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
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
        """加载子文件夹"""
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

        # 获取子文件夹
        try:
            # 特殊处理：root 节点不需要再加载子文件夹（已由 load_folders 加载）
            if folder_id == "root":
                return

            subfolders = self.crawler.get_question_subfolders(folder_id)

            if subfolders:
                for sf in subfolders:
                    # 避免重复添加：检查是否已存在相同 ID 的文件夹
                    existing_ids = set()
                    for i in range(item.childCount()):
                        child_item = item.child(i)
                        existing_ids.add(child_item.data(0, Qt.ItemDataRole.UserRole))

                    if sf['id'] not in existing_ids:
                        child = QTreeWidgetItem([f"📁 {sf['name']} ({sf['count']})"])
                        child.setData(0, Qt.ItemDataRole.UserRole, sf['id'])
                        child.setData(0, Qt.ItemDataRole.UserRole + 1, False)  # 子文件夹未加载
                        item.addChild(child)

                        # 存储映射
                        self._folder_items[sf['id']] = child

                item.setExpanded(True)
                self.status_update.emit(f"已加载 {len(subfolders)} 个子文件夹")
            else:
                # 没有子文件夹
                pass

        except Exception as e:
            print(f"加载子文件夹失败: {e}")
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
            
            for i, q in enumerate(questions):
                self.status_update.emit(f"正在上传第 {i+1}/{total} 道题目...")
                
                # 更新 UI（避免卡死）
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                result = self.crawler.add_question(folder_id, q)
                
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
            # 移除行内 Markdown 强调符号（如 `code` -> code）
            if not value:
                return ""
            return re.sub(r"`([^`]*)`", r"\1", value)
        
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
        
        option_pattern = r'^\s*([A-Ha-h])\s*[、.．:：]\s*(.+)$'
        answer_pattern = r'^\s*(?:答案|正确答案)\s*[：:]\s*(.+)$'  # 改为匹配任意答案
        analysis_pattern = r'^\s*(?:答案解析|解析|分析)\s*[：:]\s*(.+)$'
        difficulty_pattern = r'^\s*(?:难易程度|难度)\s*[：:]\s*(易|中|难|简单|较难|困难)'
        difficulty_value_pattern = r'^\s*难度系数\s*[：:]\s*([\d.]+)'  # 新增：匹配"难度系数：X.X"
        type_pattern = r'^\s*题型\s*[：:]\s*(.+)$'
        
        current_section = "content"
        
        for line in lines:
            raw_line = line.rstrip('\r')

            # 优先跳过整行代码块围栏，如 ```java / ```
            if re.match(r"^\s*```", raw_line):
                continue

            raw_line_clean = strip_md_emphasis(raw_line)

            # 处理行内/残留代码块标记：去掉 ```、语言标识，保留内部内容
            if "```" in raw_line_clean:
                raw_line_clean = re.sub(r"```\s*\w*", "", raw_line_clean)
                raw_line_clean = raw_line_clean.replace("```", "")

            # 跳过分隔线行，如 ---
            if raw_line_clean.strip() == "---":
                continue

            stripped = raw_line_clean.strip()

            if not stripped:
                if current_section == "content":
                    content_lines.append(raw_line_clean)
                elif current_section == "analysis":
                    analysis_lines.append(raw_line_clean)
                elif current_section == "options" and options:
                    prev = options[-1]["value"]
                    options[-1]["value"] = (prev + "\n" + raw_line_clean) if prev else raw_line_clean
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

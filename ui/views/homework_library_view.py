"""
作业库视图 - 展示作业库列表
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFrame, QMessageBox, QMenu, QDialog, QLineEdit,
    QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction


class FolderSelectDialog(QDialog):
    """文件夹选择对话框"""

    def __init__(self, folders: list, crawler=None, course_id: str = "", parent=None):
        super().__init__(parent)
        self.folders = folders
        self.crawler = crawler
        self.course_id = course_id
        self.selected_folder_id = 0  # 默认选择根目录
        self.loaded_folders = set()  # 已加载子文件夹的ID集合
        self.setup_ui()

    def setup_ui(self):
        """设置界面"""
        self.setWindowTitle("移动到 (选择目标目录)")
        self.setFixedSize(400, 450)
        self.setStyleSheet("background-color: #2d2d30;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 文件夹树
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 6px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
        """)

        # 添加根目录
        root_item = QTreeWidgetItem(self.folder_tree, ["📁 根目录"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, 0)
        root_item.setExpanded(True)

        # 添加文件夹
        for folder in self.folders:
            item = QTreeWidgetItem(root_item, [f"📁 {folder['name']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, folder['id'])
            # 如果有子文件夹，添加占位项使其可展开
            if folder.get('children'):
                placeholder = QTreeWidgetItem(item, ["加载中..."])
                item.setData(0, Qt.ItemDataRole.UserRole + 1, 'has_children')

        self.folder_tree.itemClicked.connect(self.on_folder_clicked)
        self.folder_tree.itemExpanded.connect(self.on_item_expanded)
        layout.addWidget(self.folder_tree)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def on_folder_clicked(self, item: QTreeWidgetItem, column: int):
        """点击文件夹"""
        self.selected_folder_id = item.data(0, Qt.ItemDataRole.UserRole)

    def on_item_expanded(self, item: QTreeWidgetItem):
        """展开文件夹时动态加载子文件夹"""
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)

        # 如果已经加载过，跳过
        if folder_id in self.loaded_folders:
            return

        # 检查是否有子文件夹标记
        has_children = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if not has_children:
            return

        # 移除占位项
        for i in range(item.childCount()):
            child = item.child(i)
            if child.text(0) == "加载中...":
                item.removeChild(child)
                break

        # 加载子文件夹
        if self.crawler and self.course_id:
            sub_folders = self.crawler.get_folder_list(self.course_id, parent_id=folder_id)

            for folder in sub_folders:
                sub_item = QTreeWidgetItem(item, [f"📁 {folder['name']}"])
                sub_item.setData(0, Qt.ItemDataRole.UserRole, folder['id'])
                # 如果有子文件夹，添加占位项
                if folder.get('children'):
                    placeholder = QTreeWidgetItem(sub_item, ["加载中..."])
                    sub_item.setData(0, Qt.ItemDataRole.UserRole + 1, 'has_children')

            self.loaded_folders.add(folder_id)

    def get_selected_folder(self) -> int:
        """获取选中的文件夹ID"""
        return self.selected_folder_id


class HomeworkLibraryView(QWidget):
    """作业库视图"""
    
    status_update = pyqtSignal(str)
    create_homework_requested = pyqtSignal(int)  # 请求创建作业信号，参数为文件夹ID
    
    def __init__(self, crawler=None, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.current_course_id = None  # 当前课程ID
        self.current_class_id = None  # 当前班级ID
        self.current_directory_id = 0  # 当前文件夹ID（0表示根目录）
        self.directory_path = []  # 文件夹路径栈 [{id, name}, ...]
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面布局"""
        self.setStyleSheet("background-color: #1e1e1e;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # ====== 顶部标题栏 ======
        header_layout = QHBoxLayout()
        
        # 新建文件夹按钮
        new_folder_btn = QPushButton("📁 新建文件夹")
        new_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
                margin-right: 10px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        new_folder_btn.clicked.connect(self.create_folder)
        header_layout.addWidget(new_folder_btn)
        
        # 当前路径标签
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #888888; font-size: 12px;")
        header_layout.addWidget(self.path_label)
        
        header_layout.addStretch()
        
        # 在此创建作业按钮（进入文件夹后显示）
        self.create_in_folder_btn = QPushButton("在此创建作业")
        self.create_in_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_in_folder_btn.setMinimumHeight(28)
        self.create_in_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 13px;
                font-weight: bold;
                margin-right: 10px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.create_in_folder_btn.clicked.connect(self.on_create_in_current_folder)
        self.create_in_folder_btn.setVisible(False)
        header_layout.addWidget(self.create_in_folder_btn)
        
        # 返回上级按钮
        self.back_btn = QPushButton("⬅ 返回上级")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
                margin-right: 10px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.setVisible(False)
        header_layout.addWidget(self.back_btn)
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        refresh_btn.clicked.connect(self.load_library)
        header_layout.addWidget(refresh_btn)
        
        main_layout.addLayout(header_layout)
        
        # ====== 中部：作业列表 ======
        self.library_tree = QTreeWidget()
        self.library_tree.setHeaderLabels(["名称", "题量", "分值", "创建者", "创建时间"])
        self.library_tree.setColumnWidth(0, 400)
        self.library_tree.setColumnWidth(1, 80)
        self.library_tree.setColumnWidth(2, 80)
        self.library_tree.setColumnWidth(3, 120)
        self.library_tree.setColumnWidth(4, 120)
        self.library_tree.setRootIsDecorated(False)
        self.library_tree.setUniformRowHeights(True)
        self.library_tree.setItemsExpandable(False)
        
        self.library_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 8px;
                border: none;
                border-bottom: 1px solid #3e3e42;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
                border: none;
                border-bottom: 1px solid #3e3e42;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #ffffff;
                padding: 8px 12px;
                border: none;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
            }
        """)
        
        # 启用右键菜单
        self.library_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.library_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # 启用双击事件
        self.library_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        main_layout.addWidget(self.library_tree, 1)
        
        # ====== 底部：统计信息 ======
        footer_layout = QHBoxLayout()
        
        self.stats_label = QLabel("共 0 个文件夹，0 份作业")
        self.stats_label.setStyleSheet("color: #888888; font-size: 12px;")
        footer_layout.addWidget(self.stats_label)
        
        footer_layout.addStretch()
        
        main_layout.addLayout(footer_layout)
    
    def load_library(self):
        """加载作业库"""
        if not self.crawler or not self.current_course_id or not self.current_class_id:
            self.status_update.emit("❌ 请先选择课程和班级")
            return
        
        self.status_update.emit("正在加载作业库...")
        self.library_tree.clear()
        
        try:
            result = self.crawler.get_homework_library(
                self.current_course_id,
                self.current_class_id,
                self.current_directory_id
            )
            
            if result.get('error'):
                self.status_update.emit(f"❌ 加载失败: {result['error']}")
                return
            
            folders = result.get('folders', [])
            works = result.get('works', [])
            
            # 添加文件夹
            for folder in folders:
                item = QTreeWidgetItem([
                    f"📁 {folder['name']} ({folder['count']}份)",
                    "---",
                    "---",
                    folder['author'],
                    folder['time']
                ])
                
                item.setForeground(0, Qt.GlobalColor.white)
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'folder',
                    'id': folder['id'],
                    'name': folder['name']
                })
                
                self.library_tree.addTopLevelItem(item)
            
            # 添加作业
            for work in works:
                item = QTreeWidgetItem([
                    f"📝 {work['title']}",
                    str(work['question_num']),
                    str(work['score']),
                    work['author'],
                    work['time']
                ])
                
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    'type': 'work',
                    'id': work['id'],
                    'title': work['title']
                })
                
                self.library_tree.addTopLevelItem(item)
            
            # 更新统计信息
            self.stats_label.setText(f"共 {len(folders)} 个文件夹，{len(works)} 份作业")
            self.status_update.emit(f"✅ 已加载 {len(folders)} 个文件夹，{len(works)} 份作业")
            
        except Exception as e:
            self.status_update.emit(f"❌ 加载失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def on_show(self):
        """视图显示时调用"""
        self.status_update.emit("进入作业库")
        
        # 获取当前课程和班级信息
        from ui.main_window import MainWindow
        main_window = self.window()
        if not isinstance(main_window, MainWindow):
            self.status_update.emit("❌ 无法获取课程信息")
            return
        
        course = main_window.course_box.currentData()
        class_id = main_window.clazz_box.currentData()
        
        if not course or not class_id:
            self.status_update.emit("❌ 请先选择课程和班级")
            return
        
        self.current_course_id = str(course.id)
        self.current_class_id = str(class_id)
        
        # 重置文件夹导航状态
        self.current_directory_id = 0
        self.directory_path = []
        self.back_btn.setVisible(False)
        self.update_path_label()
        
        # 加载作业库
        self.load_library()
    
    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项目"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        if data.get('type') == 'folder':
            # 进入文件夹
            folder_id = data.get('id')
            folder_name = data.get('name')
            self.enter_directory(folder_id, folder_name)
    
    def enter_directory(self, directory_id: int, directory_name: str):
        """进入文件夹"""
        # 保存当前文件夹到路径栈
        self.directory_path.append({
            'id': self.current_directory_id,
            'name': directory_name
        })
        
        # 更新当前文件夹ID
        self.current_directory_id = directory_id
        
        # 显示返回按钮
        self.back_btn.setVisible(True)
        self.create_in_folder_btn.setVisible(True)
        
        # 更新路径标签
        self.update_path_label()
        
        # 重新加载
        self.load_library()
        
        # 调试输出
        print(f"\n=== 进入文件夹 ===")
        print(f"directory_id: {directory_id}")
        print(f"directory_name: {directory_name}")
    
    def go_back(self):
        """返回上一级"""
        if not self.directory_path:
            return
        
        # 从路径栈弹出上一级
        prev_directory = self.directory_path.pop()
        self.current_directory_id = prev_directory['id']
        
        # 如果已经回到根目录，隐藏返回按钮
        if not self.directory_path:
            self.back_btn.setVisible(False)
            self.create_in_folder_btn.setVisible(False)
        
        # 更新路径标签
        self.update_path_label()
        
        # 重新加载
        self.load_library()
    
    def enter_folder_by_id(self, folder_id: int):
        """
        通过文件夹ID直接进入文件夹(用于从外部跳转)
        
        Args:
            folder_id: 文件夹ID
        """
        # 清空路径栈,只保存根目录作为返回目标
        self.directory_path = [{
            'id': 0,  # 根目录ID
            'name': '根目录'
        }]
        
        # 设置当前文件夹ID
        self.current_directory_id = folder_id
        
        # 显示返回按钮
        self.back_btn.setVisible(True)
        self.create_in_folder_btn.setVisible(True)
        
        # 更新路径标签
        self.path_label.setText(f" / 目标文件夹")
        
        # 加载作业库
        self.load_library()
        
        print(f"\n=== 通过ID进入文件夹 ===")
        print(f"folder_id: {folder_id}")
    
    def on_create_in_current_folder(self):
        """
        在当前文件夹创建作业
        点击"在此创建作业"按钮时调用
        """
        # 获取当前文件夹ID
        current_folder_id = self.current_directory_id
        
        # 转换为整数
        try:
            folder_id_int = int(current_folder_id) if current_folder_id else 0
        except (ValueError, TypeError):
            folder_id_int = 0
        
        print(f"\n=== 在当前文件夹创建作业 ===")
        print(f"current_directory_id: {current_folder_id}")
        print(f"folder_id_int: {folder_id_int}")
        
        # 触发创建作业信号
        if folder_id_int > 0:
            self.create_homework_requested.emit(folder_id_int)
    
    def update_path_label(self):
        """更新路径标签"""
        if not self.directory_path:
            self.path_label.setText("")
        else:
            path_names = [d['name'] for d in self.directory_path]
            self.path_label.setText(f" / {' / '.join(path_names)}")
    
    def rename_work(self, work_data: dict):
        """重命名作业"""
        work_id = work_data.get('id')
        old_title = work_data.get('title')
        
        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return
        
        # 弹出输入对话框
        new_title, ok = QInputDialog.getText(
            self,
            "重命名作业",
            "请输入新的作业名称:",
            QLineEdit.EchoMode.Normal,
            old_title
        )
        
        if not ok or not new_title:
            return
        
        if new_title == old_title:
            QMessageBox.information(self, "提示", "作业名称未改变", QMessageBox.StandardButton.Ok)
            return
        
        self.status_update.emit(f"正在重命名作业...")
        
        # 调用API重命名作业
        result = self.crawler.rename_work(
            work_id,
            new_title,
            self.current_course_id,
            self.current_class_id,
            self.current_directory_id
        )
        
        if result.get('status'):
            QMessageBox.information(
                self,
                "重命名成功",
                f"✅ 作业已重命名为「{new_title}」",
                QMessageBox.StandardButton.Ok
            )
            self.load_library()  # 刷新列表
        else:
            QMessageBox.warning(
                self,
                "重命名失败",
                f"❌ 重命名失败: {result.get('msg', '未知错误')}",
                QMessageBox.StandardButton.Ok
            )
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        # 获取当前选中的项
        item = self.library_tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_type = data.get('type')
        
        # 创建菜单
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #094771;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3e3e42;
                margin: 5px 10px;
            }
        """)
        
        if item_type == 'folder':
            # 文件夹菜单
            rename_action = QAction("✏️ 重命名", self)
            rename_action.triggered.connect(lambda: self.rename_folder(data))
            menu.addAction(rename_action)
            
            menu.addSeparator()
            
            # 新建作业
            create_homework_action = QAction("📝 新建作业", self)
            create_homework_action.triggered.connect(lambda: self.create_homework_in_folder(data))
            menu.addAction(create_homework_action)
            
            move_action = QAction("📁 移动到", self)
            move_action.triggered.connect(lambda: self.move_folder(data))
            menu.addAction(move_action)
            
            delete_action = QAction("🗑️ 删除", self)
            delete_action.triggered.connect(lambda: self.delete_folder(data))
            menu.addAction(delete_action)
            
        elif item_type == 'work':
            # 作业菜单
            rename_action = QAction("✏️ 重命名", self)
            rename_action.triggered.connect(lambda: self.rename_work(data))
            menu.addAction(rename_action)
            
            menu.addSeparator()
            
            move_action = QAction("📁 移动到", self)
            move_action.triggered.connect(lambda: self.move_work(data))
            menu.addAction(move_action)
            
            copy_action = QAction("📋 复制", self)
            copy_action.triggered.connect(lambda: self.copy_work(data))
            menu.addAction(copy_action)
            
            delete_action = QAction("🗑️ 删除", self)
            delete_action.triggered.connect(lambda: self.delete_work(data))
            menu.addAction(delete_action)
            
            menu.addSeparator()
            
            publish_action = QAction("📤 发布", self)
            publish_action.triggered.connect(lambda: self.publish_work(data))
            menu.addAction(publish_action)
        
        # 显示菜单
        menu.exec(self.library_tree.viewport().mapToGlobal(position))
    
    def move_work(self, work_data: dict):
        """移动作业"""
        work_id = work_data.get('id')
        title = work_data.get('title')
        
        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return
        
        # 获取文件夹列表
        folders = self.crawler.get_folder_list(self.current_course_id, parent_id=0)
        
        if not folders:
            QMessageBox.information(
                self,
                "移动作业",
                "当前没有可用的文件夹，将移动到根目录",
                QMessageBox.StandardButton.Ok
            )
            target_folder_id = 0
        else:
            # 显示文件夹选择对话框
            dialog = FolderSelectDialog(folders, self.crawler, self.current_course_id, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            target_folder_id = dialog.get_selected_folder()

        # 调用API移动作业
        self.status_update.emit(f"正在移动作业「{title}」...")
        
        result = self.crawler.move_work_to_folder(
            work_id,
            target_folder_id,
            self.current_course_id,
            self.current_class_id
        )
        
        if result.get('status'):
            folder_name = "根目录" if target_folder_id == 0 else next((f['name'] for f in folders if f['id'] == target_folder_id), "未知")
            QMessageBox.information(
                self,
                "移动成功",
                f"✅ 作业「{title}」已移动到「{folder_name}」",
                QMessageBox.StandardButton.Ok
            )
            self.load_library()  # 刷新列表
        else:
            QMessageBox.warning(
                self,
                "移动失败",
                f"❌ 移动失败: {result.get('msg', '未知错误')}",
                QMessageBox.StandardButton.Ok
            )
    
    def copy_work(self, work_data: dict):
        """复制作业"""
        work_id = work_data.get('id')
        title = work_data.get('title')
        
        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return
        
        reply = QMessageBox.question(
            self,
            "确认复制",
            f"确定要复制作业「{title}」吗？\n\n作业将被复制到当前目录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_update.emit(f"正在复制作业「{title}」...")
            
            # 调用API复制作业
            result = self.crawler.copy_work(
                work_id,
                self.current_directory_id,
                self.current_course_id
            )
            
            if result.get('status'):
                QMessageBox.information(
                    self,
                    "复制成功",
                    f"✅ 作业「{title}」复制成功！",
                    QMessageBox.StandardButton.Ok
                )
                self.load_library()  # 刷新列表
            else:
                QMessageBox.warning(
                    self,
                    "复制失败",
                    f"❌ 复制失败: {result.get('msg', '未知错误')}",
                    QMessageBox.StandardButton.Ok
                )
    
    def delete_work(self, work_data: dict):
        """删除作业"""
        work_id = work_data.get('id')
        title = work_data.get('title')
        
        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return
        
        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"⚠️ 确定要删除作业「{title}」吗？\n\n此操作将把作业移到回收站！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_update.emit(f"正在删除作业「{title}」...")
            
            # 调用API删除作业
            result = self.crawler.delete_work(
                work_id,
                self.current_course_id
            )
            
            if result.get('status'):
                QMessageBox.information(
                    self,
                    "删除成功",
                    f"✅ 作业「{title}」已移到回收站！",
                    QMessageBox.StandardButton.Ok
                )
                self.load_library()  # 刷新列表
            else:
                QMessageBox.warning(
                    self,
                    "删除失败",
                    f"❌ 删除失败: {result.get('msg', '未知错误')}",
                    QMessageBox.StandardButton.Ok
                )
    
    def publish_work(self, work_data: dict):
        """发布作业"""
        work_id = work_data.get('id')
        title = work_data.get('title')
        
        reply = QMessageBox.question(
            self,
            "确认发布",
            f"确定要发布作业「{title}」吗？\n\n发布后学生将可以看到此作业。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_update.emit(f"正在发布作业「{title}」...")
            # TODO: 调用API发布作业
            # result = self.crawler.publish_work(work_id)
            # if result.get('status'):
            #     QMessageBox.information(self, "成功", "作业发布成功！", QMessageBox.StandardButton.Ok)
            #     self.load_library()  # 刷新列表
            # else:
            #     QMessageBox.warning(self, "失败", f"发布失败: {result.get('msg', '未知错误')}", QMessageBox.StandardButton.Ok)
            QMessageBox.information(self, "提示", "发布功能开发中...", QMessageBox.StandardButton.Ok)

    def create_folder(self):
        """创建文件夹"""
        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return

        # 弹出输入对话框
        folder_name, ok = QInputDialog.getText(
            self,
            "新建文件夹",
            "请输入文件夹名称:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if not ok or not folder_name:
            return

        self.status_update.emit(f"正在创建文件夹「{folder_name}」...")

        # 调用API创建文件夹
        result = self.crawler.create_folder(
            folder_name,
            self.current_course_id,
            self.current_directory_id
        )

        if result.get('status'):
            QMessageBox.information(
                self,
                "创建成功",
                f"✅ 文件夹「{folder_name}」创建成功！",
                QMessageBox.StandardButton.Ok
            )
            self.load_library()  # 刷新列表
        else:
            QMessageBox.warning(
                self,
                "创建失败",
                f"❌ 创建失败: {result.get('msg', '未知错误')}",
                QMessageBox.StandardButton.Ok
            )

    def rename_folder(self, folder_data: dict):
        """重命名文件夹"""
        folder_id = folder_data.get('id')
        old_name = folder_data.get('name')

        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return

        # 弹出输入对话框
        new_name, ok = QInputDialog.getText(
            self,
            "重命名文件夹",
            "请输入新的文件夹名称:",
            QLineEdit.EchoMode.Normal,
            old_name
        )

        if not ok or not new_name:
            return

        if new_name == old_name:
            QMessageBox.information(self, "提示", "文件夹名称未改变", QMessageBox.StandardButton.Ok)
            return

        self.status_update.emit(f"正在重命名文件夹...")

        result = self.crawler.rename_folder(folder_id, new_name, self.current_course_id)

        if result.get('status'):
            QMessageBox.information(
                self,
                "重命名成功",
                f"✅ 文件夹已重命名为「{new_name}」",
                QMessageBox.StandardButton.Ok
            )
            self.load_library()
        else:
            QMessageBox.warning(
                self,
                "重命名失败",
                f"❌ 重命名失败: {result.get('msg', '未知错误')}",
                QMessageBox.StandardButton.Ok
            )

    def move_folder(self, folder_data: dict):
        """移动文件夹"""
        folder_id = folder_data.get('id')
        folder_name = folder_data.get('name')

        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return

        # 获取文件夹列表
        folders = self.crawler.get_folder_list(self.current_course_id, parent_id=0)

        if not folders:
            QMessageBox.information(
                self,
                "移动文件夹",
                "当前没有可用的文件夹，将移动到根目录",
                QMessageBox.StandardButton.Ok
            )
            target_folder_id = 0
        else:
            # 显示文件夹选择对话框
            dialog = FolderSelectDialog(folders, self.crawler, self.current_course_id, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            target_folder_id = dialog.get_selected_folder()

        self.status_update.emit(f"正在移动文件夹「{folder_name}」...")

        result = self.crawler.move_folder(folder_id, target_folder_id, self.current_course_id)

        if result.get('status'):
            folder_name_text = "根目录" if target_folder_id == 0 else next((f['name'] for f in folders if f['id'] == target_folder_id), "未知")
            QMessageBox.information(
                self,
                "移动成功",
                f"✅ 文件夹「{folder_name}」已移动到「{folder_name_text}」",
                QMessageBox.StandardButton.Ok
            )
            self.load_library()
        else:
            QMessageBox.warning(
                self,
                "移动失败",
                f"❌ 移动失败: {result.get('msg', '未知错误')}",
                QMessageBox.StandardButton.Ok
            )

    def delete_folder(self, folder_data: dict):
        """删除文件夹"""
        folder_id = folder_data.get('id')
        folder_name = folder_data.get('name')

        if not self.crawler or not self.current_course_id:
            QMessageBox.warning(self, "错误", "无法获取课程信息", QMessageBox.StandardButton.Ok)
            return

        reply = QMessageBox.warning(
            self,
            "确认删除",
            f"⚠️ 确定要删除文件夹「{folder_name}」吗？\n\n文件夹内的所有作业也将被删除！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.status_update.emit(f"正在删除文件夹「{folder_name}」...")

            result = self.crawler.delete_folder(folder_id, self.current_course_id)

            if result.get('status'):
                QMessageBox.information(
                    self,
                    "删除成功",
                    f"✅ 文件夹「{folder_name}」已删除！",
                    QMessageBox.StandardButton.Ok
                )
                self.load_library()
            else:
                QMessageBox.warning(
                    self,
                    "删除失败",
                    f"❌ 删除失败: {result.get('msg', '未知错误')}",
                    QMessageBox.StandardButton.Ok
                )
    
    def create_homework_in_folder(self, folder_data: dict):
        """在文件夹中新建作业"""
        folder_id = folder_data.get('id')
        folder_name = folder_data.get('name')
        
        # 转换为整数（文件夹ID可能是字符串）
        try:
            folder_id_int = int(folder_id) if folder_id else 0
        except (ValueError, TypeError):
            folder_id_int = 0
        
        print(f"\n=== 在文件夹中新建作业 ===")
        print(f"folder_id: {folder_id} (type: {type(folder_id)})")
        print(f"folder_id_int: {folder_id_int}")
        print(f"folder_name: {folder_name}")
        
        # 发送信号，请求跳转到创建作业tab
        self.create_homework_requested.emit(folder_id_int)
        
        self.status_update.emit(f"正在跳转到创建作业...")

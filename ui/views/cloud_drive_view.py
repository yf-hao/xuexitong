"""
云盘视图
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QFrame, QMenu, QFileDialog, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QAction


class DownloadThread(QThread):
    """下载线程"""
    
    finished_signal = pyqtSignal(dict)  # 下载完成信号
    
    def __init__(self, crawler, download_type, **kwargs):
        super().__init__()
        self.crawler = crawler
        self.download_type = download_type  # 'file' or 'folder'
        self.kwargs = kwargs
    
    def run(self):
        """执行下载"""
        try:
            if self.download_type == 'file':
                result = self.crawler.download_file(**self.kwargs)
            else:
                result = self.crawler.download_folder(**self.kwargs)
            
            self.finished_signal.emit(result)
        except Exception as e:
            self.finished_signal.emit({
                "success": False,
                "error": str(e)
            })


class CloudDriveView(QWidget):
    """云盘视图"""
    
    status_update = pyqtSignal(str)
    
    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.cloud_info = None
        self.current_folder_id = None  # 当前文件夹ID
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(10)
        
        # 标题栏
        header_layout = QHBoxLayout()
        
        title = QLabel("云盘")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(title)
        
        # 用户信息标签
        self.user_info_label = QLabel("")
        self.user_info_label.setStyleSheet("color: #888888; font-size: 14px;")
        header_layout.addWidget(self.user_info_label)
        
        header_layout.addStretch()
        
        # 文件计数标签
        self.file_count_label = QLabel("共 0 项")
        self.file_count_label.setStyleSheet("color: #888888; font-size: 14px;")
        header_layout.addWidget(self.file_count_label)
        
        layout.addLayout(header_layout)
        
        # 路径导航栏
        self.path_layout = QHBoxLayout()
        self.path_layout.setSpacing(5)
        
        self.path_home_btn = QLabel("根目录")
        self.path_home_btn.setStyleSheet("""
            QLabel {
                color: #007acc;
                font-size: 13px;
                padding: 5px 10px;
                background-color: #1e1e1e;
                border-radius: 4px;
            }
            QLabel:hover {
                background-color: #2a2d2e;
                text-decoration: underline;
            }
        """)
        self.path_home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.path_home_btn.mousePressEvent = lambda e: self.navigate_to_root()
        
        self.path_layout.addWidget(self.path_home_btn)
        self.path_layout.addStretch()
        
        # 上传文件按钮
        from PyQt6.QtWidgets import QPushButton
        self.upload_btn = QPushButton("📤 上传文件")
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
        """)
        self.upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_btn.clicked.connect(self.upload_file)
        self.path_layout.addWidget(self.upload_btn)
        
        # 新建文件夹按钮
        self.new_folder_btn = QPushButton("📁 新建文件夹")
        self.new_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2d2e;
                color: #e1e1e1;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border: 1px solid #007acc;
            }
            QPushButton:pressed {
                background-color: #1e1e1e;
            }
        """)
        self.new_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_folder_btn.clicked.connect(self.create_folder)
        self.path_layout.addWidget(self.new_folder_btn)
        
        layout.addLayout(self.path_layout)
        
        # 文件列表容器
        self.file_container = QFrame()
        self.file_container.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(self.file_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # 文件列表表格
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["名称", "类型", "大小", "修改时间"])
        
        # 设置表格样式 - 深色主题
        self.file_table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: none;
                border-radius: 12px;
                gridline-color: transparent;
                color: #e1e1e1;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 15px 10px;
                border-bottom: 1px solid #252526;
            }
            QTableWidget::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
            QTableWidget::item:selected:!active {
                background-color: #007acc;
                color: #ffffff;
            }
            QTableWidget::item:hover:!selected {
                background-color: #2a2d2e;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #bbbbbb;
                padding: 12px 10px;
                border: none;
                border-bottom: 2px solid #333333;
                font-weight: bold;
                font-size: 14px;
            }
            QTableWidget QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
                border-radius: 6px;
            }
            QTableWidget QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 6px;
                min-height: 20px;
            }
            QTableWidget QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }
            QTableWidget QScrollBar::add-line:vertical,
            QTableWidget QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # 设置列宽
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 名称列自动伸展
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # 类型列
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # 大小列
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # 时间列
        
        # 其他表格设置
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_table.setAlternatingRowColors(False)  # 不使用交替行颜色，使用自定义样式
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setShowGrid(False)
        self.file_table.verticalHeader().setDefaultSectionSize(50)  # 设置行高为50像素
        self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # 启用自定义右键菜单
        self.file_table.customContextMenuRequested.connect(self.show_context_menu)  # 连接右键菜单事件
        
        # 双击事件
        self.file_table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        
        container_layout.addWidget(self.file_table)
        layout.addWidget(self.file_container)
        
        # 加载提示标签
        self.loading_label = QLabel("正在加载云盘文件...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #007acc;
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 12px;
                padding: 40px;
                font-size: 16px;
            }
        """)
        layout.addWidget(self.loading_label)
        self.loading_label.hide()
    
    def refresh_info(self):
        """刷新云盘信息"""
        self.status_update.emit("正在获取云盘信息...")
        self.file_container.hide()
        self.loading_label.show()
        self.loading_label.setText("正在加载云盘文件...")
        
        try:
            # 调用云盘 API
            result = self.crawler.get_cloud_drive_base_info()
            
            if result.get("success"):
                # 保存云盘信息
                self.cloud_info = result.get("cloud_info", {})
                # 添加token信息到cloud_info
                if "token" in result:
                    self.cloud_info["token"] = result["token"]
                
                # 保存根目录ID
                if "rootdir" in self.cloud_info:
                    self.current_folder_id = self.cloud_info["rootdir"]
                
                # 更新用户信息标签
                if "realname" in self.cloud_info:
                    self.user_info_label.setText(f"用户: {self.cloud_info['realname']}")
                
                # 显示文件列表
                if "file_list" in result:
                    self.display_file_list(result["file_list"])
                    self.file_count_label.setText(f"共 {result.get('file_count', len(result['file_list']))} 项")
                else:
                    self.file_count_label.setText("共 0 项")
                    self.file_table.setRowCount(0)
                
                # 重置路径导航
                self.reset_path_navigation()
                
                self.loading_label.hide()
                self.file_container.show()
                self.status_update.emit("云盘信息获取成功")
            else:
                self.loading_label.setText(f"加载失败: {result.get('error', '未知错误')}")
                self.status_update.emit("云盘信息获取失败")
                
        except Exception as e:
            self.loading_label.setText(f"加载出错: {str(e)}")
            self.status_update.emit(f"获取云盘信息出错: {str(e)}")
    
    def reset_path_navigation(self):
        """重置路径导航栏"""
        # 找到 stretch 的位置
        stretch_index = -1
        for i in range(self.path_layout.count()):
            item = self.path_layout.itemAt(i)
            if item and item.spacerItem():
                stretch_index = i
                break
        
        # 如果找到 stretch，删除根目录按钮和 stretch 之间的所有元素
        if stretch_index > 1:
            for i in range(stretch_index - 1, 0, -1):
                item = self.path_layout.takeAt(i)
                if item.widget():
                    item.widget().deleteLater()
    
    def get_file_icon(self, item):
        """根据文件类型获取图标"""
        if not item.get("isfile"):
            return "📁"
        
        suffix = item.get("suffix", "").lower()
        
        # 压缩文件
        if suffix in ["zip", "rar", "7z", "tar", "gz", "bz2"]:
            return "📦"
        
        # 文档文件
        if suffix in ["doc", "docx", "pdf", "txt", "md"]:
            return "📝"
        
        # 表格文件
        if suffix in ["xls", "xlsx", "csv"]:
            return "📊"
        
        # 演示文件
        if suffix in ["ppt", "pptx"]:
            return "📽️"
        
        # 图片文件
        if suffix in ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"]:
            return "🖼️"
        
        # 视频文件
        if suffix in ["mp4", "avi", "mkv", "mov", "wmv", "flv"]:
            return "🎬"
        
        # 音频文件
        if suffix in ["mp3", "wav", "flac", "aac", "ogg"]:
            return "🎵"
        
        # 代码文件
        if suffix in ["py", "js", "java", "cpp", "c", "h", "html", "css", "json", "xml"]:
            return "💻"
        
        # 默认文件图标
        return "📄"
    
    def display_file_list(self, file_list):
        """显示文件列表"""
        self.file_table.setRowCount(len(file_list))
        
        for row, item in enumerate(file_list):
            # 名称列
            name = item.get("name", "未知")
            icon = self.get_file_icon(item)
            name_item = QTableWidgetItem(f"{icon} {name}")
            name_item.setData(Qt.ItemDataRole.UserRole, item)  # 存储原始数据
            name_item.setForeground(QColor("#e1e1e1"))
            self.file_table.setItem(row, 0, name_item)
            
            # 类型列
            if item.get("isfile"):
                file_type = item.get("suffix", "文件").upper()
                type_text = f"{file_type} 文件"
            else:
                type_text = "文件夹"
            type_item = QTableWidgetItem(type_text)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setForeground(QColor("#888888"))
            self.file_table.setItem(row, 1, type_item)
            
            # 大小列
            if item.get("isfile") and item.get("filesize", 0) > 0:
                size_text = self.format_file_size(item["filesize"])
            else:
                size_text = "-"
            size_item = QTableWidgetItem(size_text)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            size_item.setForeground(QColor("#888888"))
            self.file_table.setItem(row, 2, size_item)
            
            # 修改时间列
            modify_date = item.get("modifyDate", 0)
            if modify_date:
                from datetime import datetime
                try:
                    dt = datetime.fromtimestamp(modify_date / 1000)
                    time_text = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_text = "-"
            else:
                time_text = "-"
            time_item = QTableWidgetItem(time_text)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            time_item.setForeground(QColor("#888888"))
            self.file_table.setItem(row, 3, time_item)
    
    def format_file_size(self, size):
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size/1024/1024:.1f} MB"
        else:
            return f"{size/1024/1024/1024:.1f} GB"
    
    def on_cell_double_clicked(self, row, column):
        """双击单元格事件"""
        item = self.file_table.item(row, 0)
        if not item:
            return
        
        file_data = item.data(Qt.ItemDataRole.UserRole)
        if not file_data:
            return
        
        # 如果是文件夹，进入该文件夹
        if not file_data.get("isfile"):
            folder_id = file_data.get("id")
            folder_name = file_data.get("name", "未知文件夹")
            self.navigate_to_folder(folder_id, folder_name)
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        # 获取当前选中的行
        current_row = self.file_table.currentRow()
        if current_row < 0:
            return
        
        # 获取当前项的数据
        item = self.file_table.item(current_row, 0)
        if not item:
            return
        
        file_data = item.data(Qt.ItemDataRole.UserRole)
        if not file_data:
            return
        
        # 创建右键菜单
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2d2e;
                color: #e1e1e1;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3e3e42;
                margin: 5px 10px;
            }
        """)
        
        # 添加菜单项
        download_action = QAction("⬇️ 下载", self)
        rename_action = QAction("✏️ 重命名", self)
        move_action = QAction("📁 移动到", self)
        delete_action = QAction("🗑️ 删除", self)
        
        # 设置菜单项样式
        for action in [download_action, rename_action, move_action, delete_action]:
            action.setFont(self.font())
        
        # 连接下载动作
        download_action.triggered.connect(lambda: self.download_file(file_data))
        
        # 连接重命名动作
        rename_action.triggered.connect(lambda: self.rename_item(file_data))
        
        # 连接移动动作
        move_action.triggered.connect(lambda: self.move_item(file_data))
        
        # 连接删除动作
        delete_action.triggered.connect(lambda: self.delete_item(file_data))
        
        menu.addAction(download_action)
        menu.addSeparator()
        menu.addAction(rename_action)
        menu.addAction(move_action)
        menu.addSeparator()
        menu.addAction(delete_action)
        
        # 在鼠标位置显示菜单
        menu.exec(self.file_table.viewport().mapToGlobal(position))
    
    def download_file(self, file_data):
        """下载文件或文件夹"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        is_file = file_data.get("isfile", False)
        item_name = file_data.get("name", "未知")
        
        if is_file:
            # 下载文件：选择保存位置
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存文件",
                item_name,
                "所有文件 (*.*)"
            )
            
            if not save_path:
                return
            
            self.status_update.emit(f"正在下载 {item_name}...")
            
            # 创建下载线程
            self.download_thread = DownloadThread(
                self.crawler,
                'file',
                file_id=file_data.get("id"),
                encrypted_id=file_data.get("encryptedId"),
                puid=self.cloud_info.get("currentPuid"),
                current_folder_id=self.current_folder_id,
                token=self.cloud_info.get("token"),
                save_path=save_path
            )
            
            def on_download_finished(result):
                if result.get("success"):
                    self.status_update.emit(f"下载成功: {result.get('filename')}")
                    QMessageBox.information(
                        self,
                        "下载成功",
                        f"已保存到:\n{result.get('file_path')}"
                    )
                else:
                    self.status_update.emit(f"下载失败: {result.get('error')}")
                    QMessageBox.critical(
                        self,
                        "下载失败",
                        f"错误: {result.get('error')}"
                    )
            
            self.download_thread.finished_signal.connect(on_download_finished)
            self.download_thread.start()
                
        else:
            # 下载文件夹：选择目录
            save_path = QFileDialog.getExistingDirectory(
                self,
                "选择保存位置",
                "",
                QFileDialog.Option.ShowDirsOnly
            )
            
            if not save_path:
                return
            
            self.status_update.emit(f"正在打包下载 {item_name}...")
            
            # 创建下载线程
            self.download_thread = DownloadThread(
                self.crawler,
                'folder',
                folder_id=file_data.get("id"),
                encrypted_id=file_data.get("encryptedId"),
                puid=self.cloud_info.get("currentPuid"),
                token=self.cloud_info.get("token"),
                save_path=save_path
            )
            
            def on_download_finished(result):
                if result.get("success"):
                    self.status_update.emit(f"下载成功: {result.get('filename')}")
                    QMessageBox.information(
                        self,
                        "下载成功",
                        f"文件夹已打包为 ZIP 保存到:\n{result.get('file_path')}"
                    )
                else:
                    self.status_update.emit(f"下载失败: {result.get('error')}")
                    QMessageBox.critical(
                        self,
                        "下载失败",
                        f"错误: {result.get('error')}"
                    )
            
            self.download_thread.finished_signal.connect(on_download_finished)
            self.download_thread.start()
    
    def rename_item(self, file_data):
        """重命名文件或文件夹"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        current_name = file_data.get("name", "")
        
        # 弹出输入对话框
        new_name, ok = QInputDialog.getText(
            self,
            "重命名",
            "请输入新名称:",
            text=current_name
        )
        
        if not ok or not new_name or new_name == current_name:
            return
        
        self.status_update.emit(f"正在重命名...")
        
        try:
            # 调用重命名API
            result = self.crawler.rename_cloud_drive_item(
                item_id=file_data.get("id"),
                parent_id=self.current_folder_id,
                new_name=new_name,
                token=self.cloud_info.get("token")
            )
            
            if result.get("success"):
                self.status_update.emit(f"重命名成功")
                QMessageBox.information(
                    self,
                    "重命名成功",
                    f"已重命名为: {new_name}"
                )
                # 刷新当前文件夹列表
                if self.current_folder_id == self.cloud_info.get("rootdir"):
                    # 在根目录，刷新整个页面
                    self.refresh_info()
                else:
                    # 在子文件夹中，重新加载当前文件夹
                    self.navigate_to_folder(self.current_folder_id, "当前文件夹")
            else:
                self.status_update.emit(f"重命名失败: {result.get('error')}")
                QMessageBox.critical(
                    self,
                    "重命名失败",
                    f"错误: {result.get('error')}"
                )
                
        except Exception as e:
            self.status_update.emit(f"重命名出错: {str(e)}")
            QMessageBox.critical(
                self,
                "重命名出错",
                f"错误: {str(e)}"
            )
    
    def delete_item(self, file_data):
        """删除文件或文件夹"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        item_name = file_data.get("name", "未知")
        is_file = file_data.get("isfile", False)
        
        # 确认对话框
        msg_type = "文件" if is_file else "文件夹"
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除{msg_type} '{item_name}' 吗？\n\n删除后可在回收站中恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.status_update.emit(f"正在删除 {item_name}...")
        
        try:
            # 调用删除API
            result = self.crawler.delete_cloud_drive_item(
                item_id=file_data.get("id"),
                encrypted_id=file_data.get("encryptedId"),
                puid=self.cloud_info.get("currentPuid"),
                token=self.cloud_info.get("token")
            )
            
            if result.get("success"):
                self.status_update.emit(f"删除成功")
                QMessageBox.information(
                    self,
                    "删除成功",
                    f"已删除: {item_name}"
                )
                # 刷新当前文件夹列表
                if self.current_folder_id == self.cloud_info.get("rootdir"):
                    self.refresh_info()
                else:
                    self.navigate_to_folder(self.current_folder_id, "当前文件夹")
            else:
                self.status_update.emit(f"删除失败: {result.get('error')}")
                QMessageBox.critical(
                    self,
                    "删除失败",
                    f"错误: {result.get('error')}"
                )
                
        except Exception as e:
            self.status_update.emit(f"删除出错: {str(e)}")
            QMessageBox.critical(
                self,
                "删除出错",
                f"错误: {str(e)}"
            )
    
    def move_item(self, file_data):
        """移动文件或文件夹"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        item_name = file_data.get("name", "未知")
        item_id = file_data.get("id")  # 要移动的项目ID
        
        self.status_update.emit(f"正在获取文件夹列表...")
        
        try:
            # 获取根目录下的文件夹列表
            result = self.crawler.get_folder_list_for_move(
                parent_id=self.cloud_info.get("rootdir"),
                token=self.cloud_info.get("token")
            )
            
            if not result.get("success"):
                QMessageBox.critical(
                    self,
                    "获取文件夹列表失败",
                    f"错误: {result.get('error')}"
                )
                return
            
            folders = result.get("folders", [])
            
            # 创建对话框
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"移动 '{item_name}' 到")
            dialog.setMinimumSize(450, 550)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                }
                QLabel {
                    color: #e1e1e1;
                }
                QTreeWidget {
                    background-color: #252526;
                    color: #e1e1e1;
                    border: 1px solid #3e3e42;
                    border-radius: 6px;
                    padding: 5px;
                    font-size: 14px;
                }
                QTreeWidget::item {
                    padding: 4px 2px;
                    border-radius: 4px;
                    height: 24px;
                }
                QTreeWidget::item:selected {
                    background-color: #007acc;
                    color: #ffffff;
                }
                QTreeWidget::item:hover:!selected {
                    background-color: #2a2d2e;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            
            # 创建树形控件
            folder_tree = QTreeWidget()
            folder_tree.setHeaderLabel("选择目标文件夹")
            
            # 存储已加载的文件夹ID，避免重复加载
            loaded_folders = set()
            
            def load_subfolders(parent_item, parent_id):
                """加载子文件夹"""
                if parent_id in loaded_folders:
                    return
                loaded_folders.add(parent_id)
                
                # 移除占位项
                while parent_item.childCount() > 0:
                    child = parent_item.child(0)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole) or {}
                    if child_data.get("is_placeholder"):
                        parent_item.removeChild(child)
                    else:
                        break
                
                result = self.crawler.get_folder_list_for_move(
                    parent_id=parent_id,
                    token=self.cloud_info.get("token")
                )
                
                if result.get("success"):
                    subfolders = result.get("folders", [])
                    for folder in subfolders:
                        # 跳过正在移动的项目本身
                        if folder.get("id") == item_id:
                            continue
                        
                        child_item = QTreeWidgetItem(parent_item)
                        child_item.setText(0, f"📁 {folder.get('name')}")
                        child_item.setData(0, Qt.ItemDataRole.UserRole, folder)
                        
                        # 如果有子文件夹，添加占位项以显示展开箭头
                        has_child = folder.get("hasChild") in (True, 1, "true", "1")
                        if has_child:
                            placeholder = QTreeWidgetItem(child_item)
                            placeholder.setText(0, "加载中...")
                            placeholder.setData(0, Qt.ItemDataRole.UserRole, {"is_placeholder": True})
            
            # 添加根目录选项
            root_item = QTreeWidgetItem(folder_tree)
            root_item.setText(0, "📁 根目录")
            root_item.setData(0, Qt.ItemDataRole.UserRole, {"id": self.cloud_info.get("rootdir"), "name": "根目录"})
            
            # 添加根目录下的文件夹
            for folder in folders:
                # 跳过正在移动的项目本身
                if folder.get("id") == item_id:
                    continue
                
                folder_item = QTreeWidgetItem(root_item)
                folder_item.setText(0, f"📁 {folder.get('name')}")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, folder)
                
                # 如果有子文件夹，添加一个占位子项以显示展开箭头
                has_child = folder.get("hasChild") in (True, 1, "true", "1")
                if has_child:
                    placeholder = QTreeWidgetItem(folder_item)
                    placeholder.setText(0, "加载中...")
                    placeholder.setData(0, Qt.ItemDataRole.UserRole, {"is_placeholder": True})
            
            # 展开根目录
            root_item.setExpanded(True)
            loaded_folders.add(self.cloud_info.get("rootdir"))
            
            # 监听展开事件，动态加载子文件夹
            def on_item_expanded(item):
                folder_data = item.data(0, Qt.ItemDataRole.UserRole)
                if folder_data:
                    folder_id = folder_data.get("id")
                    # 检查是否有占位项（需要加载）
                    if item.childCount() > 0:
                        first_child = item.child(0)
                        child_data = first_child.data(0, Qt.ItemDataRole.UserRole) or {}
                        if child_data.get("is_placeholder"):
                            load_subfolders(item, folder_id)
            
            folder_tree.itemExpanded.connect(on_item_expanded)
            
            layout.addWidget(folder_tree)
            
            # 添加按钮
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.setStyleSheet("""
                QPushButton {
                    background-color: #007acc;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 20px;
                    font-size: 13px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #005a9e;
                }
                QPushButton:pressed {
                    background-color: #004578;
                }
            """)
            
            def on_accept():
                selected_items = folder_tree.selectedItems()
                if not selected_items:
                    QMessageBox.warning(dialog, "提示", "请选择目标文件夹")
                    return
                
                selected_folder = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
                target_folder_id = selected_folder.get("id")
                target_folder_name = selected_folder.get("name")
                
                # 确认移动
                reply = QMessageBox.question(
                    dialog,
                    "确认移动",
                    f"确定将 '{item_name}' 移动到 '{target_folder_name}' 吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    return
                
                dialog.accept()
                
                # 执行移动
                self.status_update.emit(f"正在移动 {item_name}...")
                
                try:
                    result = self.crawler.move_cloud_drive_item(
                        item_id=item_id,
                        target_folder_id=target_folder_id,
                        puid=self.cloud_info.get("currentPuid"),
                        token=self.cloud_info.get("token")
                    )
                    
                    if result.get("success"):
                        self.status_update.emit(f"移动成功")
                        QMessageBox.information(
                            self,
                            "移动成功",
                            f"'{item_name}' 已移动到 '{target_folder_name}'"
                        )
                        # 刷新当前文件夹列表
                        if self.current_folder_id == self.cloud_info.get("rootdir"):
                            self.refresh_info()
                        else:
                            self.navigate_to_folder(self.current_folder_id, "当前文件夹")
                    else:
                        self.status_update.emit(f"移动失败: {result.get('error')}")
                        QMessageBox.critical(
                            self,
                            "移动失败",
                            f"错误: {result.get('error')}"
                        )
                        
                except Exception as e:
                    self.status_update.emit(f"移动出错: {str(e)}")
                    QMessageBox.critical(
                        self,
                        "移动出错",
                        f"错误: {str(e)}"
                    )
            
            button_box.accepted.connect(on_accept)
            button_box.rejected.connect(dialog.reject)
            
            layout.addWidget(button_box)
            
            self.status_update.emit("请选择目标文件夹")
            dialog.exec()
            
        except Exception as e:
            self.status_update.emit(f"获取文件夹列表出错: {str(e)}")
            QMessageBox.critical(
                self,
                "获取文件夹列表出错",
                f"错误: {str(e)}"
            )
    
    def navigate_to_folder(self, folder_id, folder_name):
        """导航到指定文件夹"""
        if not self.cloud_info:
            return
        
        self.status_update.emit(f"正在打开 {folder_name}...")
        self.file_container.hide()
        self.loading_label.show()
        self.loading_label.setText(f"正在加载 {folder_name}...")
        
        try:
            # 获取文件夹内容
            result = self.crawler.get_file_list(
                puid=self.cloud_info.get("currentPuid"),
                enc=self.cloud_info.get("encstr"),
                parent_id=folder_id,
                token=self.cloud_info.get("token")
            )
            
            if result.get("success"):
                # 更新当前文件夹ID
                self.current_folder_id = folder_id
                
                # 更新路径导航
                self.update_path_navigation(folder_id, folder_name)
                
                # 显示文件列表
                self.display_file_list(result["list"])
                self.file_count_label.setText(f"共 {result.get('totalCount', len(result['list']))} 项")
                
                self.loading_label.hide()
                self.file_container.show()
                self.status_update.emit(f"已打开 {folder_name}")
            else:
                self.loading_label.setText(f"加载失败: {result.get('error', '未知错误')}")
                self.status_update.emit(f"打开文件夹失败")
                
        except Exception as e:
            self.loading_label.setText(f"加载出错: {str(e)}")
            self.status_update.emit(f"打开文件夹出错: {str(e)}")
    
    def navigate_to_root(self):
        """返回根目录"""
        if not self.cloud_info:
            return
        
        self.refresh_info()
    
    def update_path_navigation(self, folder_id, folder_name):
        """更新路径导航栏"""
        # 清空当前路径（保留根目录按钮、stretch和右侧按钮）
        # 布局顺序：根目录按钮 | 路径元素... | stretch | 上传按钮 | 新建文件夹按钮
        
        # 找到 stretch 的位置
        stretch_index = -1
        for i in range(self.path_layout.count()):
            item = self.path_layout.itemAt(i)
            if item and item.spacerItem():
                stretch_index = i
                break
        
        # 如果找到 stretch，删除根目录按钮和 stretch 之间的所有元素
        if stretch_index > 1:  # 位置0是根目录按钮，位置1+是路径元素
            for i in range(stretch_index - 1, 0, -1):
                item = self.path_layout.takeAt(i)
                if item.widget():
                    item.widget().deleteLater()
        
        # 在根目录按钮后添加分隔符
        separator = QLabel(">")
        separator.setStyleSheet("color: #888888; font-size: 13px;")
        self.path_layout.insertWidget(1, separator)
        
        # 添加当前文件夹
        current_folder = QLabel(folder_name)
        current_folder.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                padding: 5px 10px;
                background-color: #2a2d2e;
                border-radius: 4px;
            }
        """)
        self.path_layout.insertWidget(2, current_folder)
    
    def on_show(self):
        """视图显示时调用"""
        self.status_update.emit("进入云盘")
        # 自动刷新一次
        self.refresh_info()
    
    def upload_file(self):
        """上传文件"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        # 选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要上传的文件",
            "",
            "所有文件 (*.*)"
        )
        
        if not file_path:
            return
        
        import os
        filename = os.path.basename(file_path)
        
        self.status_update.emit(f"正在上传 {filename}...")
        
        try:
            # 第一步：生成上传URL
            url_result = self.crawler.generate_upload_url(
                puid=self.cloud_info.get("currentPuid"),
                folder_id=self.current_folder_id,
                _token=self.cloud_info.get("_token"),  # URL参数token（短的）
                p_auth_token=self.cloud_info.get("token")  # 认证token（长的）
            )
            
            if not url_result.get("success"):
                self.status_update.emit(f"生成上传URL失败: {url_result.get('error')}")
                QMessageBox.critical(
                    self,
                    "上传失败",
                    f"错误: {url_result.get('error')}"
                )
                return
            
            # 第二步：上传文件
            upload_result = self.crawler.upload_file_to_cloud(
                upload_url=url_result.get("upload_url"),
                file_path=file_path,
                token=self.cloud_info.get("token")
            )
            
            if upload_result.get("success"):
                self.status_update.emit(f"上传成功")
                QMessageBox.information(
                    self,
                    "上传成功",
                    f"文件 {filename} 已成功上传"
                )
                # 刷新当前文件夹列表
                if self.current_folder_id == self.cloud_info.get("rootdir"):
                    self.refresh_info()
                else:
                    self.navigate_to_folder(self.current_folder_id, "当前文件夹")
            else:
                self.status_update.emit(f"上传失败: {upload_result.get('error')}")
                QMessageBox.critical(
                    self,
                    "上传失败",
                    f"错误: {upload_result.get('error')}"
                )
                
        except Exception as e:
            self.status_update.emit(f"上传出错: {str(e)}")
            QMessageBox.critical(
                self,
                "上传出错",
                f"错误: {str(e)}"
            )
    
    def create_folder(self):
        """新建文件夹"""
        if not self.cloud_info:
            QMessageBox.warning(self, "错误", "云盘信息未加载")
            return
        
        # 弹出输入对话框
        folder_name, ok = QInputDialog.getText(
            self,
            "新建文件夹",
            "请输入文件夹名称:",
            text="新建文件夹"
        )
        
        if not ok or not folder_name:
            return
        
        self.status_update.emit(f"正在创建文件夹 {folder_name}...")
        
        try:
            # 调用创建文件夹API
            result = self.crawler.create_cloud_drive_folder(
                parent_id=self.current_folder_id,
                folder_name=folder_name,
                token=self.cloud_info.get("token")
            )
            
            if result.get("success"):
                self.status_update.emit(f"创建成功")
                QMessageBox.information(
                    self,
                    "创建成功",
                    f"文件夹 '{folder_name}' 已创建"
                )
                # 刷新当前文件夹列表
                if self.current_folder_id == self.cloud_info.get("rootdir"):
                    self.refresh_info()
                else:
                    self.navigate_to_folder(self.current_folder_id, "当前文件夹")
            else:
                self.status_update.emit(f"创建失败: {result.get('error')}")
                QMessageBox.critical(
                    self,
                    "创建失败",
                    f"错误: {result.get('error')}"
                )
                
        except Exception as e:
            self.status_update.emit(f"创建出错: {str(e)}")
            QMessageBox.critical(
                self,
                "创建出错",
                f"错误: {str(e)}"
            )

"""
作业创建视图 - 从题库选题创建作业
"""

import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QFrame, QComboBox, QCheckBox, QGroupBox,
    QScrollArea, QDialog, QTextEdit, QSplitter, QInputDialog, QLineEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.components.multi_select_combo import MultiSelectCombo


class QuestionPreviewDialog(QDialog):
    """题目预览对话框"""
    
    def __init__(self, question_data: dict, parent=None):
        super().__init__(parent)
        self.question_data = question_data
        self.setWindowTitle("📋 题目预览")
        self.setFixedSize(500, 400)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 题目信息
        info_layout = QHBoxLayout()
        info_label = QLabel(f"题型: {self.question_data.get('type', '未知')}    难度: {self.question_data.get('difficulty', '未知')}")
        info_label.setStyleSheet("color: #888888; font-size: 13px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        
        # 题目内容
        content_label = QLabel("题目:")
        content_label.setStyleSheet("color: #007acc; font-weight: bold;")
        layout.addWidget(content_label)
        
        content_text = QLabel(self.question_data.get("content", ""))
        content_text.setStyleSheet("color: #ffffff; font-size: 14px;")
        content_text.setWordWrap(True)
        layout.addWidget(content_text)
        
        # 模拟选项
        options_label = QLabel("选项:")
        options_label.setStyleSheet("color: #007acc; font-weight: bold;")
        layout.addWidget(options_label)
        
        options_text = QLabel("A. 选项A\nB. 选项B\nC. 选项C\nD. 选项D")
        options_text.setStyleSheet("color: #cccccc; font-size: 13px;")
        layout.addWidget(options_text)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        add_btn = QPushButton("加入选题")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        add_btn.clicked.connect(self.accept)
        btn_layout.addWidget(add_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
        """)
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)


class HomeworkCreateView(QWidget):
    """作业创建视图"""
    
    status_update = pyqtSignal(str)
    
    def __init__(self, crawler=None, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.selected_questions = set()  # 已选题目ID集合
        self.current_folder_id = "root"  # 当前文件夹ID
        self.folder_path = []  # 文件夹路径栈 [{id, name}, ...]
        self.current_course_id = None  # 当前课程ID（主课程）
        self.current_class_id = None  # 当前班级ID
        self.dir_course_id = ""  # 文件夹所属课程ID（用于搜索）
        self.q_bank_id = ""  # 题库ID
        self.courses_loaded = False  # 课程列表是否已加载
        # 分页状态
        self.current_page = 1  # 当前页码
        self.total_count = 0  # 总题目数
        self.page_size = 30  # 每页数量
        self.page_select_all_states = {}  # 每页的全选状态 {page: True/False}
        self.current_tab = "library"  # 当前选中的tab
        self.target_directory_id = 0  # 目标文件夹ID（用于在指定文件夹创建作业）
        self.setup_ui()
    
    def setup_ui(self):
        """设置界面布局"""
        self.setStyleSheet("background-color: #1e1e1e;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # ====== 顶部：Tab切换 ======
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(0)
        
        self.publish_tab_btn = QPushButton("📚 作业库")
        self.publish_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.publish_tab_btn.setStyleSheet(self._tab_style(active=True))
        self.publish_tab_btn.clicked.connect(lambda: self.switch_tab("library"))
        tab_layout.addWidget(self.publish_tab_btn)

        self.create_tab_btn = QPushButton("📝 创建作业")
        self.create_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_tab_btn.setStyleSheet(self._tab_style(active=False))
        self.create_tab_btn.clicked.connect(lambda: self.switch_tab("create"))
        tab_layout.addWidget(self.create_tab_btn)
        
        tab_layout.addStretch()
        main_layout.addLayout(tab_layout)
        
        # ====== 创建作业容器 ======
        self.create_container = QFrame()
        create_layout = QVBoxLayout(self.create_container)
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.setSpacing(10)
        
        # ====== 顶部：筛选条件 ======
        filter_group = self.create_filter_panel()
        create_layout.addWidget(filter_group)
        
        # ====== 中部：全选/反选栏 ======
        select_layout = QHBoxLayout()
        self.select_all_cb = QCheckBox("全选当前题目")
        self.select_all_cb.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self.select_all_cb.stateChanged.connect(self.on_select_all_changed)
        select_layout.addWidget(self.select_all_cb)
        
        self.question_count_label = QLabel("(共 0 题)")
        self.question_count_label.setStyleSheet("color: #888888; font-size: 12px;")
        select_layout.addWidget(self.question_count_label)
        
        select_layout.addStretch()
        
        select_layout.addSpacing(10)
        
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
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.setVisible(False)
        select_layout.addWidget(self.back_btn)
        
        # 反选按钮
        invert_btn = QPushButton("反选")
        invert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        invert_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        invert_btn.clicked.connect(self.invert_selection)
        select_layout.addWidget(invert_btn)
        
        create_layout.addLayout(select_layout)
        
        # ====== 中部：题目列表 ======
        content_layout = QVBoxLayout()
        
        # 题目/文件夹列表
        self.question_tree = QTreeWidget()
        self.question_tree.setHeaderLabels(["序号", "题干", "题型", "难易", "使用量", "正确率", "创建者", "创建时间"])
        self.question_tree.setColumnWidth(0, 50)
        self.question_tree.setColumnWidth(1, 320)
        self.question_tree.setColumnWidth(2, 80)
        self.question_tree.setColumnWidth(3, 100)
        self.question_tree.setColumnWidth(4, 70)
        self.question_tree.setColumnWidth(5, 80)
        self.question_tree.setColumnWidth(6, 100)
        self.question_tree.setColumnWidth(7, 80)
        # 去除竖线网格和选择样式
        self.question_tree.setRootIsDecorated(False)
        self.question_tree.setUniformRowHeights(True)
        self.question_tree.setItemsExpandable(False)
        self.question_tree.header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.question_tree.setStyleSheet("""
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
            QTreeWidget::item:selected:active {
                border: none;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #ffffff;
                padding: 8px 12px;
                border: none;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
            }
            QTreeWidget::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #555555;
                border-radius: 3px;
                background-color: #1e1e1e;
            }
            QTreeWidget::indicator:hover {
                border: 2px solid #007acc;
            }
            QTreeWidget::indicator:checked {
                background-color: #007acc;
                border: 2px solid #007acc;
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMiIgaGVpZ2h0PSIxMiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjMiPjxwYXRoIGQ9Ik0yMCA2TDkgMTdsLTUtNSIvPjwvc3ZnPg==);
            }
            QTreeWidget::indicator:checked:hover {
                background-color: #005c99;
                border: 2px solid #005c99;
            }
        """)
        self.question_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.question_tree.itemChanged.connect(self.on_item_changed)  # 添加复选框状态变化处理
        content_layout.addWidget(self.question_tree)
        
        create_layout.addLayout(content_layout, 1)
        
        # ====== 底部：分页和已选统计 ======
        bottom_layout = QHBoxLayout()
        
        # 已选统计
        self.selected_label = QLabel("📊 已选: 0 道题目")
        self.selected_label.setStyleSheet("color: #ff9800; font-size: 14px; font-weight: bold;")
        bottom_layout.addWidget(self.selected_label)
        
        bottom_layout.addStretch()
        
        # 分页控件
        self.prev_btn = QPushButton("⬅ 上一页")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setEnabled(False)
        self.prev_btn.setStyleSheet("""
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
            }
            QPushButton:disabled {
                background-color: #2d2d30;
                color: #666666;
                border: 1px solid #3e3e42;
            }
        """)
        self.prev_btn.clicked.connect(self.prev_page)
        bottom_layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("第 1 页")
        self.page_label.setStyleSheet("color: #cccccc; font-size: 13px; padding: 0 10px;")
        bottom_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("下一页 ➡")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setEnabled(False)
        self.next_btn.setStyleSheet("""
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
            }
            QPushButton:disabled {
                background-color: #2d2d30;
                color: #666666;
                border: 1px solid #3e3e42;
            }
        """)
        self.next_btn.clicked.connect(self.next_page)
        bottom_layout.addWidget(self.next_btn)
        
        bottom_layout.addStretch()
        
        # 创建作业按钮
        create_btn = QPushButton("创建作业")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        create_btn.clicked.connect(self.create_homework)
        bottom_layout.addWidget(create_btn)
        
        create_layout.addLayout(bottom_layout)
        
        # 将创建作业容器添加到主布局
        self.create_container.setVisible(False)  # 默认隐藏
        main_layout.addWidget(self.create_container)

        # ====== 作业库视图 ======
        from ui.views.homework_library_view import HomeworkLibraryView
        self.library_view = HomeworkLibraryView(self.crawler, self)
        self.library_view.status_update.connect(self.status_update.emit)
        self.library_view.create_homework_requested.connect(self.on_create_homework_requested)
        main_layout.addWidget(self.library_view)
    
    def create_filter_panel(self) -> QFrame:
        """创建筛选条件面板"""
        group = QFrame()
        group.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)
        
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("🔍 筛选条件")
        title.setStyleSheet("color: #007acc; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # 第一行
        row1 = QHBoxLayout()
        
        # 课程
        row1.addWidget(QLabel("课程:"))
        self.course_combo = QComboBox()
        self.course_combo.blockSignals(True)  # 阻止初始化时的信号
        self.course_combo.addItem("全部课程", "all")
        self.course_combo.addItem("高等数学", "math")
        self.course_combo.addItem("线性代数", "linear")
        self.course_combo.setMaxVisibleItems(15)  # 最多显示15项，超过显示滚动条
        self.course_combo.setStyleSheet(self._combo_style())
        self.course_combo.blockSignals(False)  # 恢复信号
        self.course_combo.currentIndexChanged.connect(self.on_course_changed)
        row1.addWidget(self.course_combo)
        
        row1.addSpacing(20)
        
        # 题型 - 多选下拉框
        row1.addWidget(QLabel("题型:"))
        self.type_combo = MultiSelectCombo(placeholder="请选择题型")
        self.type_combo.setMinimumWidth(180)
        
        # 添加题型选项（初始数量为0，后续从API更新）
        question_types = [
            ("0-0", "单选题"),
            ("1-0", "多选题"),
            ("2-0", "填空题"),
            ("3-0", "判断题"),
            ("4-0", "简答题"),
            ("4-104209994", "基本计算题"),
            ("5-0", "名词解释"),
            ("5-104209995", "简答题"),
            ("6-0", "论述题"),
            ("6-104209993", "证明题"),
            ("7-0", "计算题"),
            ("7-104209992", "综合计算题"),
            ("8-0", "其它"),
            ("9-0", "分录题"),
            ("10-0", "资料题"),
            ("11-0", "连线题"),
            ("13-0", "排序题"),
            ("14-0", "完形填空"),
            ("15-0", "阅读理解"),
            ("17-0", "程序题"),
            ("18-0", "口语题"),
            ("19-0", "听力题"),
            ("20-0", "共用选项题"),
            ("22-0", "口语测评题"),
            ("23-0", "钟表题"),
            ("26-0", "写作题"),
        ]
        for type_id, type_name in question_types:
            self.type_combo.add_item(type_id, type_name, count=0, checked=True)
        
        row1.addWidget(self.type_combo)
        
        row1.addSpacing(20)
        
        # 难度 - 多选下拉框
        row1.addWidget(QLabel("难度:"))
        self.difficulty_combo = MultiSelectCombo(placeholder="请选择难度")
        self.difficulty_combo.setMinimumWidth(120)
        
        # 添加难度选项
        difficulties = [
            ("0", "易"),
            ("1", "中"),
            ("2", "难"),
        ]
        for diff_id, diff_name in difficulties:
            self.difficulty_combo.add_item(diff_id, diff_name, count=0, checked=True)
        
        row1.addWidget(self.difficulty_combo)
        
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行
        row2 = QHBoxLayout()
        
        # 知识点 - 多选下拉框
        row2.addWidget(QLabel("知识点:"))
        self.topic_combo = MultiSelectCombo(placeholder="请选择知识点")
        self.topic_combo.setMinimumWidth(350)
        row2.addWidget(self.topic_combo)
        
        row2.addSpacing(20)
        
        # 每页显示
        row2.addWidget(QLabel("每页显示:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItem("30条", 30)
        self.page_size_combo.addItem("50条", 50)
        self.page_size_combo.addItem("100条", 100)
        self.page_size_combo.setCurrentIndex(0)  # 默认30条
        self.page_size_combo.setStyleSheet(self._combo_style())
        self.page_size_combo.setFixedWidth(80)
        row2.addWidget(self.page_size_combo)
        
        row2.addStretch()
        
        # 搜索和重置按钮
        search_btn = QPushButton("🔍 搜索")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        search_btn.clicked.connect(lambda: self.on_search())
        row2.addWidget(search_btn)
        
        reset_btn = QPushButton("重置")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
        """)
        reset_btn.clicked.connect(self.on_reset)
        row2.addWidget(reset_btn)
        
        layout.addLayout(row2)
        
        return group
    
    def _combo_style(self) -> str:
        """下拉框样式"""
        return """
            QComboBox {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 100px;
            }
            QComboBox:hover {
                border: 1px solid #007acc;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #ffffff;
                selection-background-color: #094771;
                border: 1px solid #3e3e42;
            }
            QComboBox QAbstractItemView::item {
                padding: 5px 10px;
                min-height: 25px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #094771;
            }
            QComboBox QAbstractItemView::scrollbar {
                background-color: #1e1e1e;
                width: 12px;
                margin: 0;
            }
            QComboBox QAbstractItemView::scrollbar:vertical {
                border: none;
                background-color: #1e1e1e;
                width: 12px;
                margin: 0;
            }
            QComboBox QAbstractItemView::scrollbar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 6px;
            }
            QComboBox QAbstractItemView::scrollbar::handle:vertical:hover {
                background-color: #666666;
            }
            QComboBox QAbstractItemView::scrollbar::add-line:vertical,
            QComboBox QAbstractItemView::scrollbar::sub-line:vertical {
                height: 0px;
            }
        """
    
    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        """处理项目变化（复选框状态改变）"""
        # 只处理第1列（题干列）的复选框
        if column != 1:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "question":
            return
        
        q_id = data.get("id")
        if not q_id:
            return
        
        # 获取复选框状态
        check_state = item.checkState(1)
        
        # 更新选中集合
        if check_state == Qt.CheckState.Checked:
            self.selected_questions.add(q_id)
        else:
            self.selected_questions.discard(q_id)
            # 如果取消选中，将当前页的全选状态设为 False
            self.page_select_all_states[self.current_page] = False
            # 更新全选复选框显示（阻止信号避免递归）
            self.select_all_cb.blockSignals(True)
            self.select_all_cb.setChecked(False)
            self.select_all_cb.blockSignals(False)
        
        # 更新已选数量显示
        self.update_selected_count()

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项目"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "folder":
            # 进入文件夹
            folder_id = data.get("id")
            folder_name = data.get("name")
            folder_course_id = data.get("course_id")
            self.enter_folder(folder_id, folder_name, folder_course_id)
        elif data and data.get("type") == "question":
            # 预览题目
            self.preview_question(data.get("data", {}))
    
    def preview_question(self, question_data: dict):
        """预览题目"""
        dialog = QuestionPreviewDialog(question_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 加入选题
            q_id = question_data.get('id')
            if q_id:
                self.selected_questions.add(q_id)
                self.update_selected_count()
    
    def on_select_all_changed(self, state: int):
        """全选状态改变"""
        check_state = Qt.CheckState.Checked if state == Qt.CheckState.Checked.value else Qt.CheckState.Unchecked
        
        # 保存当前页的全选状态
        self.page_select_all_states[self.current_page] = (state == Qt.CheckState.Checked.value)
        
        # 阻止信号触发
        self.question_tree.blockSignals(True)
        
        # 只选中题目，不选文件夹
        for i in range(self.question_tree.topLevelItemCount()):
            item = self.question_tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "question":
                item.setCheckState(1, check_state)  # 第1列（题干列）
                q_id = data.get("id")
                if check_state == Qt.CheckState.Checked:
                    self.selected_questions.add(q_id)
                else:
                    self.selected_questions.discard(q_id)
        
        # 恢复信号
        self.question_tree.blockSignals(False)
        
        self.update_selected_count()
    
    def invert_selection(self):
        """反选"""
        # 阻止信号触发
        self.question_tree.blockSignals(True)
        
        for i in range(self.question_tree.topLevelItemCount()):
            item = self.question_tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "question":
                current_state = item.checkState(1)  # 第1列（题干列）
                new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(1, new_state)  # 第1列（题干列）
                
                q_id = data.get("id")
                if new_state == Qt.CheckState.Checked:
                    self.selected_questions.add(q_id)
                else:
                    self.selected_questions.discard(q_id)
        
        # 恢复信号
        self.question_tree.blockSignals(False)
        
        self.update_selected_count()
    
    def update_selected_count(self):
        """更新已选数量"""
        self.selected_label.setText(f"📊 已选: {len(self.selected_questions)} 道题目")
    
    def enter_folder(self, folder_id: str, folder_name: str, folder_course_id: str = None):
        """进入文件夹"""
        # 保存当前文件夹到路径栈
        self.folder_path.append({
            "id": self.current_folder_id,
            "name": folder_name,
            "dir_course_id": self.dir_course_id  # 保存文件夹课程ID
        })
        
        # 更新当前文件夹
        self.current_folder_id = folder_id
        
        # 如果文件夹有课程ID，设置为 dir_course_id
        if folder_course_id:
            self.dir_course_id = folder_course_id
        
        # 显示返回按钮
        self.back_btn.setVisible(True)
        
        # 更新筛选条件统计数据（传入文件夹ID）
        self.load_check_list_data()
        
        # 重新搜索
        self.on_search(page=1)
        
        # 调试输出
        print(f"\n=== 进入文件夹 ===")
        print(f"folder_id: {folder_id}")
        print(f"folder_course_id: {folder_course_id}")
        print(f"current_folder_id: {self.current_folder_id}")
        print(f"dir_course_id: {self.dir_course_id}")
    
    def go_back(self):
        """返回上一级"""
        if not self.folder_path:
            return
        
        # 从路径栈弹出上一级
        prev_folder = self.folder_path.pop()
        self.current_folder_id = prev_folder["id"]
        self.dir_course_id = prev_folder["dir_course_id"]  # 恢复文件夹课程ID
        
        # 如果已经回到根目录，隐藏返回按钮
        if not self.folder_path:
            self.back_btn.setVisible(False)
        
        # 更新筛选条件统计数据
        self.load_check_list_data()
        
        # 重新搜索
        self.on_search(page=1)
    
    def on_search(self, page: int = 1):
        """搜索题目"""
        if not self.crawler or not self.current_course_id:
            self.status_update.emit("请先选择课程")
            return
        
        # 获取筛选条件
        selected_course = self.course_combo.currentData()
        course_ids = selected_course if selected_course != "all" else ""
        
        selected_types = self.type_combo.get_selected_values()
        selected_difficulties = self.difficulty_combo.get_selected_values()
        selected_topics = self.topic_combo.get_selected_values()
        keyword = ""  # TODO: 添加搜索框
        
        # 判断是否全选（全选时传空值）
        all_types = self.type_combo.items
        total_types = sum(1 for item in all_types.values() if not item.get("is_group", False))
        is_all_types_selected = len(selected_types) == total_types
        
        # 题型：全选时传None，否则传选中列表
        question_types = None if is_all_types_selected else selected_types
        
        # 难度：全选时传None，否则传选中列表
        all_difficulties = self.difficulty_combo.items
        total_difficulties = sum(1 for item in all_difficulties.values() if not item.get("is_group", False))
        is_all_difficulties_selected = len(selected_difficulties) == total_difficulties
        difficulties = None if is_all_difficulties_selected else selected_difficulties
        
        # 知识点：全选时传None，否则传选中列表
        all_topics = self.topic_combo.items
        total_topics = sum(1 for item in all_topics.values() if not item.get("is_group", False))
        is_all_topics_selected = len(selected_topics) == total_topics
        topic_ids = None if is_all_topics_selected else selected_topics
        
        # 获取每页显示数量
        self.page_size = self.page_size_combo.currentData()
        
        # 获取当前文件夹ID和文件夹课程ID
        dir_id = self.current_folder_id if self.current_folder_id != "root" else ""
        dir_course_id = self.dir_course_id if dir_id else ""
        
        self.status_update.emit(f"搜索中...")
        
        try:
            # 调用搜索API（HomeworkAPI是mixin，直接调用）
            result = self.crawler.search_questions(
                course_id=self.current_course_id,
                class_id=self.current_class_id,
                course_ids=course_ids,
                question_types=question_types,
                difficulties=difficulties,
                topic_ids=topic_ids,
                keyword=keyword,
                page=page,
                page_size=self.page_size,
                dir_id=dir_id,
                dir_course_id=dir_course_id
            )
            
            if result.get("error"):
                self.status_update.emit(f"搜索失败: {result['error']}")
            else:
                questions = result.get("questions", [])
                folders = result.get("folders", [])
                total = result.get("total", 0)
                q_bank_id = result.get("q_bank_id", "")
                
                # 保存题库ID
                if q_bank_id:
                    self.q_bank_id = q_bank_id
                
                # 更新分页状态
                self.current_page = page
                self.total_count = total
                
                self.status_update.emit(f"找到 {total} 道题目")
                
                # 显示搜索结果
                self.display_search_results(questions, total, folders)
                
                # 更新分页按钮状态
                self.update_pagination_buttons()
                
        except Exception as e:
            self.status_update.emit(f"搜索失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.on_search(self.current_page - 1)
    
    def next_page(self):
        """下一页"""
        total_pages = (self.total_count + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.on_search(self.current_page + 1)
    
    def update_pagination_buttons(self):
        """更新分页按钮状态"""
        # 计算总页数，至少为1
        total_pages = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        
        # 更新上一页按钮
        self.prev_btn.setEnabled(self.current_page > 1)
        
        # 更新下一页按钮
        self.next_btn.setEnabled(self.current_page < total_pages)
        
        # 更新页码显示
        if self.total_count > 0:
            self.page_label.setText(f"第 {self.current_page}/{total_pages} 页")
        else:
            self.page_label.setText("暂无数据")
    
    def display_search_results(self, questions: list, total: int, folders: list = None):
        """显示搜索结果"""
        # 阻止信号触发（避免在设置复选框时触发 itemChanged）
        self.question_tree.blockSignals(True)
        
        self.question_tree.clear()
        
        # 恢复当前页的全选状态（如果有保存的状态）
        is_select_all = self.page_select_all_states.get(self.current_page, False)
        self.select_all_cb.blockSignals(True)  # 阻止信号，避免触发 on_select_all_changed
        self.select_all_cb.setChecked(is_select_all)
        self.select_all_cb.blockSignals(False)
        
        # 更新题目数量标签
        self.question_count_label.setText(f"(共 {total} 题)")
        
        # 先添加文件夹
        if folders:
            for folder in folders:
                item = QTreeWidgetItem([
                    "",  # 序号（文件夹不显示）
                    f"📁 {folder['name']} ({folder['question_count']}题)",
                    "-",  # 题型
                    "-",  # 难度
                    "-",  # 使用量
                    "-",  # 正确率
                    folder.get('author', ''),
                    folder.get('create_time', '')
                ])
                
                # 存储文件夹数据
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    "type": "folder",
                    "id": folder['id'],
                    "name": folder['name'],
                    "course_id": folder.get('course_id', ''),
                    "data": folder
                })
                
                item.setForeground(1, Qt.GlobalColor.white)
                self.question_tree.addTopLevelItem(item)
        
        # 添加题目到树形列表
        for i, q in enumerate(questions, start=1):
            # 格式化正确率显示
            accuracy_text = f"{q.accuracy}%" if q.accuracy is not None else "-"
            
            # 创建树节点（第一列为序号）
            item = QTreeWidgetItem([
                str(i),  # 序号
                q.content[:80] + "..." if len(q.content) > 80 else q.content,
                q.question_type,
                q.difficulty,
                str(q.usage_count),
                accuracy_text,
                q.author,
                q.create_time
            ])
            
            # 存储题目数据
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "type": "question",
                "id": q.id,
                "data": q.to_dict()
            })
            
            # 设置复选框状态在第1列（题干列）
            item.setCheckState(1, Qt.CheckState.Checked if q.id in self.selected_questions else Qt.CheckState.Unchecked)
            
            self.question_tree.addTopLevelItem(item)
        
        # 恢复信号
        self.question_tree.blockSignals(False)
    
    def on_reset(self):
        """重置筛选条件"""
        self.course_combo.setCurrentIndex(0)
        # 重置题型 - 全选
        self.type_combo.select_all()
        # 重置难度 - 全选
        self.difficulty_combo.select_all()
        # 重置知识点 - 全选
        self.topic_combo.select_all()
        # 重置每页显示
        self.page_size_combo.setCurrentIndex(0)
        self.status_update.emit("已重置筛选条件")
    
    def create_homework(self):
        """创建作业"""
        if not self.selected_questions:
            self.status_update.emit("❌ 请先选择题目")
            return
        
        if not self.crawler:
            self.status_update.emit("❌ 系统未初始化")
            return
        
        # 收集选中题目的信息
        selected_question_data = []
        for i in range(self.question_tree.topLevelItemCount()):
            item = self.question_tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            
            if data and data.get("type") == "question":
                q_id = data.get("id")
                if q_id in self.selected_questions:
                    q_data = data.get("data", {})
                    selected_question_data.append({
                        "id": q_id,
                        "course_id": q_data.get("course_id"),
                        "origin_type": q_data.get("origin_type"),
                        "course_question_type_id": q_data.get("course_question_type_id")
                    })
        
        if not selected_question_data:
            self.status_update.emit("❌ 未找到题目数据")
            return
        
        # 调试输出第一道题的完整数据
        if selected_question_data:
            print(f"\n=== 第一道题目完整数据 ===")
            print(json.dumps(selected_question_data[0], ensure_ascii=False, indent=2))
        
        # 生成默认作业标题
        from datetime import datetime
        default_title = f"新建作业{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 弹出对话框让用户输入作业名称
        title, ok = QInputDialog.getText(
            self,
            "创建作业",
            f"请输入作业名称（已选 {len(selected_question_data)} 道题目）：",
            QLineEdit.EchoMode.Normal,
            default_title
        )
        
        if not ok or not title:
            # 用户取消或未输入
            self.status_update.emit("已取消创建作业")
            return
        
        self.status_update.emit(f"正在创建作业「{title}」...")
        
        try:
            # 第一步：创建作业
            # qBankId 使用文件夹所属课程ID（如果有）或当前课程ID
            q_bank_id = self.dir_course_id if self.dir_course_id else self.current_course_id
            
            result = self.crawler.create_homework(
                course_id=self.current_course_id,
                class_id=self.current_class_id,
                title=title,
                questions=selected_question_data,
                q_bank_id=q_bank_id,
                directory_id=self.target_directory_id  # 使用目标文件夹ID
            )
            
            if not result.get("status"):
                self.status_update.emit(f"❌ 创建作业失败: {result.get('msg', '未知错误')}")
                return
            
            work_id = result.get("workid")
            if not work_id:
                self.status_update.emit("❌ 创建作业失败：未返回作业ID")
                return
            
            self.status_update.emit(f"作业创建成功，正在保存...")
            
            # 第二步：保存作业(必须传递directory_id,否则会保存到根目录)
            save_result = self.crawler.save_work(
                course_id=self.current_course_id,
                class_id=self.current_class_id,
                work_id=work_id,
                title=title,
                directory_id=self.target_directory_id  # 传递目标文件夹ID
            )
            
            if save_result.get("status"):
                # 保存目标文件夹ID(在清空前保存)
                target_folder_id = self.target_directory_id
                
                # 显示成功对话框
                QMessageBox.information(
                    self,
                    "创建成功",
                    f"✅ 作业「{title}」创建成功！\n\n已选择 {len(selected_question_data)} 道题目",
                    QMessageBox.StandardButton.Ok
                )
                
                self.status_update.emit(f"✅ 作业「{title}」创建成功！")
                # 清空已选题目
                self.selected_questions.clear()
                # 清空页面全选状态
                self.page_select_all_states.clear()
                # 清空目标文件夹ID
                self.target_directory_id = 0
                self.update_selected_count()
                
                # 如果是在指定文件夹创建的作业,切换到作业库并进入该文件夹
                if target_folder_id > 0:
                    self.switch_tab("library")
                    # 延迟一点时间再进入文件夹,确保作业库已加载
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(300, lambda: self.library_view.enter_folder_by_id(target_folder_id))
                else:
                    # 在根目录创建,刷新列表
                    self.on_search(self.current_page)
            else:
                # 显示失败对话框
                error_msg = save_result.get('msg', '未知错误')
                QMessageBox.warning(
                    self,
                    "保存失败",
                    f"❌ 保存作业失败！\n\n错误信息: {error_msg}",
                    QMessageBox.StandardButton.Ok
                )
                self.status_update.emit(f"❌ 保存作业失败: {error_msg}")
            
        except Exception as e:
            # 显示异常对话框
            QMessageBox.critical(
                self,
                "创建失败",
                f"❌ 创建作业时发生错误！\n\n错误信息: {str(e)}",
                QMessageBox.StandardButton.Ok
            )
            self.status_update.emit(f"❌ 创建作业失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def set_target_directory(self, directory_id: int):
        """
        设置目标文件夹ID，用于在指定文件夹创建作业
        
        Args:
            directory_id: 文件夹ID（0表示根目录）
        """
        self.target_directory_id = directory_id
        print(f"设置目标文件夹ID: {directory_id}")
    
    def on_create_homework_requested(self, directory_id: int):
        """
        响应在文件夹中创建作业的请求
        
        Args:
            directory_id: 文件夹ID
        """
        print(f"\n=== 响应创建作业请求 ===")
        print(f"directory_id: {directory_id}")
        
        # 先切换到创建作业tab（会重置target_directory_id为0）
        self.switch_tab("create")
        
        # 再设置目标文件夹ID
        self.set_target_directory(directory_id)
        
        # 像手动切换一样，加载课程列表（如果未加载）
        if not self.courses_loaded:
            self.load_courses()
        
        self.status_update.emit(f"已切换到创建作业，目标文件夹ID: {directory_id}")
    
    def on_show(self):
        """视图显示时调用"""
        self.status_update.emit("进入作业管理")

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

        # 重置文件夹导航状态
        self.current_folder_id = "root"
        self.folder_path = []
        self.dir_course_id = ""
        self.back_btn.setVisible(False)

        self.current_course_id = str(course.id)
        self.current_class_id = str(class_id)

        # 如果当前是作业库tab，加载作业库
        if self.current_tab == "library":
            self.library_view.on_show()
        else:
            # 加载课程列表（仅加载一次）
            if not self.courses_loaded:
                self.load_courses()
    
    def load_courses(self):
        """从API加载课程列表"""
        if not self.crawler or not self.current_course_id or not self.current_class_id:
            return
        
        self.status_update.emit("正在加载课程列表...")
        
        try:
            courses = self.crawler.get_question_bank_courses(
                self.current_course_id,
                self.current_class_id
            )
            
            # 阻止信号触发
            self.course_combo.blockSignals(True)
            
            # 清空并重新填充下拉框
            self.course_combo.clear()
            self.course_combo.addItem("全部课程", "all")
            
            # 查找当前课程在下拉框中的索引
            current_course_index = -1
            
            for i, course in enumerate(courses):
                self.course_combo.addItem(course['name'], course['id'])
                # 如果是当前课程，记录索引（i+1 因为第一项是"全部课程"）
                if course['id'] == self.current_course_id:
                    current_course_index = i + 1
            
            # 默认选中当前课程
            if current_course_index > 0:
                self.course_combo.setCurrentIndex(current_course_index)
            
            # 恢复信号
            self.course_combo.blockSignals(False)
            
            self.courses_loaded = True
            
            # 加载筛选条件统计数据
            self.load_check_list_data()
            
            self.status_update.emit(f"已加载 {len(courses)} 门课程")
            
        except Exception as e:
            self.status_update.emit(f"❌ 加载课程失败: {str(e)}")
    
    def load_check_list_data(self):
        """加载筛选条件统计数据"""
        if not self.crawler:
            return
        
        try:
            # 获取当前选中的课程ID
            selected_course_id = self.course_combo.currentData()
            course_ids = "" if selected_course_id == "all" else selected_course_id
            
            # 获取当前文件夹ID
            dir_id = self.current_folder_id if self.current_folder_id != "root" else ""
            
            data = self.crawler.get_question_bank_check_list(
                self.current_course_id,
                self.current_class_id,
                course_ids,
                dir_id
            )
            
            if data:
                # 更新题型数量显示
                self.update_type_counts(data.get('typeNumArr', []))
                # 更新知识点列表
                self.update_topic_list(data.get('allTopicList', []), data.get('topicNumArr', []))
                # TODO: 更新难度等其他数据
            
        except Exception as e:
            print(f"加载筛选条件失败: {e}")
    
    def on_course_changed(self):
        """课程下拉框变化时"""
        # 重新加载题型统计数据
        self.load_check_list_data()
    
    def update_type_counts(self, type_num_arr: list):
        """更新题型复选框的数量显示"""
        # 构建题型数量映射 {type_id: count}
        type_counts = {}
        
        for item in type_num_arr:
            key = item.get('key', '')
            count = item.get('doc_count', 0)
            
            # 特殊处理：所有 0-xxxx 归到单选题 (0-0)
            if key.startswith('0-'):
                type_id = "0-0"
            else:
                type_id = key
            
            type_counts[type_id] = type_counts.get(type_id, 0) + count
        
        # 更新下拉框中的数量显示
        for type_id, count in type_counts.items():
            self.type_combo.update_item_count(type_id, count)
    
    def update_topic_list(self, all_topic_list: list, topic_num_arr: list):
        """更新知识点列表"""
        # 构建知识点数量映射 {topic_id: count}
        topic_counts = {}
        unclassified_count = 0  # 未关联知识点的数量
        
        for item in topic_num_arr:
            topic_id = str(item.get('key', ''))
            count = item.get('doc_count', 0)
            if topic_id == '0':  # 未分类
                unclassified_count = count
            else:
                topic_counts[topic_id] = count
        
        # 构建父子关系映射
        parent_map = {}  # {parent_id: [children]}
        topic_map = {}  # {id: topic_data}
        
        for topic in all_topic_list:
            topic_id = str(topic.get('id', ''))
            parent_id = str(topic.get('parentId', 0))
            topic_type = topic.get('type', 0)  # 0=叶子, 1=有子节点
            topic_name = topic.get('topic', '')
            
            topic_map[topic_id] = {
                'id': topic_id,
                'name': topic_name,
                'type': topic_type,
                'parentId': parent_id
            }
            
            if parent_id not in parent_map:
                parent_map[parent_id] = []
            parent_map[parent_id].append(topic_id)
        
        # 计算每个节点的总题目数（包括所有子节点）
        def calculate_total_count(topic_id: str) -> int:
            """递归计算节点及其所有子节点的总题目数"""
            topic = topic_map.get(topic_id)
            if not topic:
                return 0
            
            # 如果是叶子节点，直接返回数量
            if topic['type'] == 0:
                return topic_counts.get(topic_id, 0)
            
            # 如果是父节点，累加所有子节点的数量
            total = 0
            if topic_id in parent_map:
                for child_id in parent_map[topic_id]:
                    total += calculate_total_count(child_id)
            return total
        
        # 为所有节点计算总数量
        for topic_id in topic_map:
            if topic_id not in topic_counts:
                topic_counts[topic_id] = calculate_total_count(topic_id)
        
        # 清空并重新填充知识点下拉框
        self.topic_combo.blockSignals(True)
        self.topic_combo.clear()
        
        # 添加"未关联知识点"选项（最上方）
        if unclassified_count > 0:
            self.topic_combo.add_item(
                "0",  # 使用"0"作为ID
                "未关联知识点", 
                count=unclassified_count, 
                checked=True, 
                indent=0,
                is_parent=False
            )
        
        # 递归添加知识点
        def add_topics_recursive(parent_id: str, indent: int = 0, parent_visible: bool = True):
            if parent_id not in parent_map:
                return
            
            for topic_id in parent_map[parent_id]:
                topic = topic_map.get(topic_id)
                if not topic:
                    continue
                
                count = topic_counts.get(topic_id, 0)
                is_parent = topic['type'] == 1
                
                # 显示条件：
                # 1. 父节点（有子节点）：总是显示
                # 2. 叶子节点：如果父节点可见，则显示（不管题目数）
                should_show = is_parent or parent_visible
                
                if should_show:
                    self.topic_combo.add_item(
                        topic_id, 
                        topic['name'], 
                        count=count, 
                        checked=True, 
                        indent=indent,
                        is_parent=is_parent
                    )
                
                # 递归处理子节点（传递当前节点是否可见）
                add_topics_recursive(topic_id, indent + 1, parent_visible=should_show)
        
        # 从根节点开始
        add_topics_recursive('0')
        
        # 建立父子关系
        for topic_id, topic in topic_map.items():
            if topic['type'] == 1:  # 是父节点
                # 获取所有子节点ID
                children = parent_map.get(topic_id, [])
                self.topic_combo.set_parent_children(topic_id, children)
        
        self.topic_combo.blockSignals(False)
    
    def switch_tab(self, tab_name: str):
        """切换tab"""
        if tab_name == self.current_tab:
            return
        
        if tab_name == "create":
            self.current_tab = "create"
            self.create_tab_btn.setStyleSheet(self._tab_style(active=True))
            self.publish_tab_btn.setStyleSheet(self._tab_style(active=False))
            self.create_container.setVisible(True)
            self.library_view.setVisible(False)
            # 手动切换到创建作业tab时，重置目标文件夹ID为0（根目录）
            self.target_directory_id = 0
            # 加载课程列表（如果未加载）
            if not self.courses_loaded:
                self.load_courses()
            self.status_update.emit("切换到创建作业")
        elif tab_name == "library":
            self.current_tab = "library"
            self.create_tab_btn.setStyleSheet(self._tab_style(active=False))
            self.publish_tab_btn.setStyleSheet(self._tab_style(active=True))
            self.create_container.setVisible(False)
            self.library_view.setVisible(True)
            self.library_view.on_show()  # 加载作业库
    
    def _tab_style(self, active: bool) -> str:
        """Tab按钮样式"""
        if active:
            return """
                QPushButton {
                    background-color: #007acc;
                    color: white;
                    border: none;
                    border-radius: 4px 4px 0 0;
                    padding: 10px 25px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005c99;
                }
            """
        else:
            return """
                QPushButton {
                    background-color: #2d2d30;
                    color: #888888;
                    border: none;
                    border-radius: 4px 4px 0 0;
                    padding: 10px 25px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #3e3e42;
                    color: #cccccc;
                }
            """

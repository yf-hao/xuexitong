import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QComboBox, QTreeWidget, QTreeWidgetItem, 
                             QPushButton, QLabel, QSplitter, QFrame, QListView,
                             QListWidget, QListWidgetItem, QStackedWidget, QMessageBox, QFileDialog)
from PyQt6.QtCore import Qt, QSettings, QCoreApplication
from ui.workers import (CourseWorker, DetailsWorker, ClassWorker, MaterialWorker, DownloadWorker)
from ui.styles import MAIN_STYLE
from core.config import SIGNIN_DATA_FILE, APP_TITLE
from ui.views.stats_view import StatsView
from ui.views.management_view import ManagementView
from ui.views.activities_view import ActivitiesView
from ui.views.question_bank_view import QuestionBankView

class MainWindow(QMainWindow):
    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(1200, 900)
        self.worker = None 
        self.details_worker = None
        self.class_worker = None
        self.workers = [] # Keep references to prevent GC and crashes
        
        # State tracking for UI consistency
        self.last_nav_title = None
        
        # Premium Dark Theme QSS
        self.setStyleSheet(MAIN_STYLE)
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(SIGNIN_DATA_FILE), exist_ok=True)
        
        # Main layout
        central_widget = QWidget()
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Top Bar: Course Selection & Class Selection
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("选择课程:"))
        self.course_box = QComboBox()
        self.course_box.setView(QListView())
        self.course_box.currentIndexChanged.connect(self.on_course_changed)
        header_layout.addWidget(self.course_box)
        
        header_layout.addSpacing(20)
        
        header_layout.addWidget(QLabel("选择班级:"))
        self.clazz_box = QComboBox()
        self.clazz_box.setView(QListView())
        self.clazz_box.currentIndexChanged.connect(self.on_class_selected)
        header_layout.addWidget(self.clazz_box)
        
        header_layout.addStretch()
        
        # Logout Button
        self.btn_logout = QPushButton("🚪 退出登录")
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setFixedWidth(120)
        self.btn_logout.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ff5252;
                border: 1px solid #ff5252;
                padding: 5px 10px;
                font-size: 13px;
                font-weight: normal;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #ff5252;
                color: white;
            }
        """)
        self.btn_logout.clicked.connect(self.on_logout_clicked)
        header_layout.addWidget(self.btn_logout)
        
        main_layout.addLayout(header_layout)
        
        # Splitter Layout (Sidebar + Main Content)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Sidebar: Navigation (Activities, Stats, Materials...)
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 0, 5, 0)
        nav_label = QLabel("课程菜单")
        nav_label.setStyleSheet("color: #007acc; margin-bottom: 5px;")
        nav_layout.addWidget(nav_label)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nav_list")
        self.nav_list.setMinimumWidth(160)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.itemClicked.connect(self.on_nav_selected)
        nav_layout.addWidget(self.nav_list)
        splitter.addWidget(nav_container)
        
        # Main Area: Content View
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(5, 0, 0, 0)
        self.content_title = QLabel("资料列表")
        self.content_title.setStyleSheet("font-size: 16px; color: #007acc; margin-bottom: 5px;")
        content_layout.addWidget(self.content_title)
        
        # Stacked Widget for different views
        self.stacked_widget = QStackedWidget()
        
        # Page 0: Material View
        self.material_tree = QTreeWidget()
        self.material_tree.setHeaderLabels(["资源名称", "资源类型", "同步状态"])
        self.material_tree.setColumnWidth(0, 500)
        self.material_tree.setAlternatingRowColors(True)
        self.stacked_widget.addWidget(self.material_tree)
        
        # Page 1: Statistics View
        self.stats_view = StatsView(self.crawler, self._update_status, parent=self)
        self.stacked_widget.addWidget(self.stats_view)
        
        # Page 2: Management View
        self.management_view = ManagementView(self.crawler, self._update_status, self._get_current_class_ids, parent=self)
        self.stacked_widget.addWidget(self.management_view)
        
        # Page 3: Activities View
        self.activities_view = ActivitiesView(
            self.crawler, 
            self._update_status, 
            self._get_current_course, 
            self._get_current_class_name,
            self._get_current_class_id,
            parent=self
        )
        self.stacked_widget.addWidget(self.activities_view)
        
        # Page 4: Question Bank View
        self.question_bank_view = QuestionBankView(self.crawler, parent=self)
        self.question_bank_view.status_update.connect(self._update_status)
        self.stacked_widget.addWidget(self.question_bank_view)
        
        content_layout.addWidget(self.stacked_widget)
        splitter.addWidget(content_container)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
        
        # Bottom Bar
        self.bottom_widget = QFrame()
        self.bottom_widget.setFixedHeight(60)
        self.bottom_widget.setStyleSheet("background: transparent; border-top: 1px solid #252526;")
        bottom_bar = QHBoxLayout(self.bottom_widget)
        
        self.status_label = QLabel("正在初始化...")
        self.status_label.setStyleSheet("font-weight: normal; color: #007acc; font-size: 12px; border: none;")
        
        # Copyright information
        copyright_label = QLabel("hao@sias.edu.cn  |  Copyright @2006  |  Powered by Antigravity CodeBuddy")
        copyright_label.setStyleSheet("font-size: 14px; color: #666666; border: none;")
        
        self.download_btn = QPushButton("下载选中资料")
        self.download_btn.setMinimumWidth(180)
        self.download_btn.clicked.connect(self.download_selected)
        
        bottom_bar.addWidget(self.status_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(copyright_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.download_btn)
        main_layout.addWidget(self.bottom_widget)
        
        self.load_courses()

    def _update_status(self, message):
        self.status_label.setText(message)

    def _get_current_class_ids(self):
        return [str(self.clazz_box.itemData(i)) for i in range(self.clazz_box.count())]

    def _get_current_course(self):
        return self.course_box.currentData()

    def _get_current_class_name(self):
        return self.clazz_box.currentText()

    def _get_current_class_id(self):
        return self.clazz_box.currentData()

    def load_courses(self, preserve_nav: bool = False):
        """
        加载课程列表
        Args:
            preserve_nav: 是否保持当前选中的导航项（不自动跳转到统计）
        """
        # 如果需要保持导航，先保存当前选中的导航项
        if preserve_nav:
            current_item = self.nav_list.currentItem()
            current_nav_title = current_item.text() if current_item else None
            self._preserved_nav_title = current_nav_title
        else:
            self._preserved_nav_title = None

        self.status_label.setText("正在异步加载课程列表...")
        self.course_box.blockSignals(True)
        self.course_box.clear()

        self.course_loader = CourseWorker(self.crawler)
        self.course_loader.courses_ready.connect(self.on_courses_delivered)
        self.course_loader.start()

    def on_courses_delivered(self, courses):
        # 显示所有课程，已结课的标记"(已结课)"以便新建课程立即可见
        ongoing_courses = [c for c in courses if not c.is_finished]
        finished_courses = [c for c in courses if c.is_finished]

        for course in ongoing_courses:
            self.course_box.addItem(course.name, course)
        for course in finished_courses:
            self.course_box.addItem(f"{course.name} (已结课)", course)
            
        self.course_box.blockSignals(False)
        self.status_label.setText(
            f"就绪，共 {len(courses)} 门课程，进行中 {len(ongoing_courses)} 门，已结课 {len(finished_courses)} 门"
        )
        if courses:
            # 尝试恢复上次选择的课程
            settings = QSettings("SIAS", "Xuexitong")
            last_course_id = settings.value("last_course_id")
            
            if last_course_id:
                # 查找匹配的课程
                for i in range(self.course_box.count()):
                    course = self.course_box.itemData(i)
                    if course and str(course.id) == last_course_id:
                        self.course_box.setCurrentIndex(i)
                        self.on_course_changed(i)
                        return
            
            # 如果没有找到或没有保存的课程，默认选择第一个
            self.course_box.setCurrentIndex(0)
            self.on_course_changed(0)

    def on_course_changed(self, index):
        course = self.course_box.itemData(index)
        if not course: return

        # 保存选择的课程ID
        settings = QSettings("SIAS", "Xuexitong")
        settings.setValue("last_course_id", str(course.id))

        # 切课时重置 session 内的 courseid 和 clazzid，避免沿用上一门课的班级ID
        self.crawler.session_manager.course_params['courseid'] = str(course.id)
        self.crawler.session_manager.course_params['clazzid'] = ""
        self.crawler.session_manager.course_params['name'] = course.name
        self.status_label.setText(f"正在获取课程信息: {course.name}...")
        self.nav_list.clear()
        self.material_tree.clear()
        self.clazz_box.clear()
        
        # 1. Fetch Details (Navigation)
        self.details_worker = DetailsWorker(self.crawler, course)
        self.details_worker.details_ready.connect(self.on_details_loaded)
        self.details_worker.start()

        # 2. Fetch Class List
        self.class_worker = ClassWorker(self.crawler, course)
        self.class_worker.classes_ready.connect(self.on_classes_loaded)
        self.class_worker.start()

    def on_classes_loaded(self, classes, course):
        self.clazz_box.blockSignals(True)
        self.clazz_box.clear()
        
        ongoing_classes = [c for c in classes if not c.get('finished', False)]
        
        for c in ongoing_classes:
            self.clazz_box.addItem(c['name'], c['id'])
        self.clazz_box.blockSignals(False)
        
        if ongoing_classes:
            # 尝试恢复上次选择的班级
            settings = QSettings("SIAS", "Xuexitong")
            last_class_id = settings.value("last_class_id")
            
            found = False
            if last_class_id:
                for i in range(self.clazz_box.count()):
                    if self.clazz_box.itemData(i) == last_class_id:
                        self.clazz_box.setCurrentIndex(i)
                        self.on_class_selected(i)
                        found = True
                        break
            
            if not found:
                self.clazz_box.setCurrentIndex(0)
                self.on_class_selected(0)
            
            hidden_count = len(classes) - len(ongoing_classes)
            if hidden_count > 0:
                self.status_label.setText(f"已加载 {len(ongoing_classes)} 个进行中的班级 (已隐藏 {hidden_count} 个结课班级)")
        else:
            self.status_label.setText(f"提示: {course.name} 下未找到正在进行中的班级 (已过滤 {len(classes)} 个结课班级)")

    def on_class_selected(self, index):
        class_id = self.clazz_box.itemData(index)
        course = self.course_box.currentData()
        if class_id and course:
            # 保存选择的班级ID
            settings = QSettings("SIAS", "Xuexitong")
            settings.setValue("last_class_id", class_id)

            self.crawler.session_manager.course_params['clazzid'] = class_id
            self.status_label.setText(f"切换班级 {class_id}")
            
            self.details_worker = DetailsWorker(self.crawler, course)
            self.details_worker.details_ready.connect(lambda d, c: self.on_class_params_refreshed(d, c))
            self.details_worker.start()

    def on_class_params_refreshed(self, details, course):
        self.status_label.setText(f"授权同步完成")
        
        current_nav = self.nav_list.currentItem()
        if not current_nav and self.last_nav_title:
            items = self.nav_list.findItems(self.last_nav_title, Qt.MatchFlag.MatchExactly)
            if items:
                current_nav = items[0]
                self.nav_list.setCurrentItem(current_nav)

        if current_nav:
            self.on_nav_selected(current_nav)
            
            # Restore sub-feature
            title = current_nav.text()
            if "统计" in title and self.stats_view.last_stats_sub:
                self.stats_view.restore_sub_feature(self.stats_view.last_stats_sub)
            elif "管理" in title and self.management_view.last_manage_sub:
                self.management_view.restore_sub_feature(self.management_view.last_manage_sub)
            elif "活动" in title and self.activities_view.last_activity_sub:
                self.activities_view.restore_sub_feature(self.activities_view.last_activity_sub)

    def on_details_loaded(self, details, course):
        if not details or "nav_links" not in details:
            self.status_label.setText(f"目录获取失败: {course.name}")
            return

        nav_links = details.get("nav_links", [])
        material_item = None
        stats_item = None
        skip_keywords = ["AI工作台", "任务引擎", "课件","教案","作业","章节","资料","通知","讨论","考试","课程图谱","AI知识库","直播课/见面课"]
        for link in nav_links:
            if any(k in link['title'] for k in skip_keywords):
                continue
            item = QListWidgetItem(link['title'])
            item.setData(Qt.ItemDataRole.UserRole, link['url'])
            self.nav_list.addItem(item)

            if "统计" in link['title']:
                stats_item = item
            elif "资料" in link['title']:
                material_item = item

        self.status_label.setText(f"目录同步完成: {course.name}")

        # 检查是否需要恢复之前保存的导航项
        if hasattr(self, '_preserved_nav_title') and self._preserved_nav_title:
            # 尝试找到之前保存的导航项
            items = self.nav_list.findItems(self._preserved_nav_title, Qt.MatchFlag.MatchExactly)
            if items:
                self.nav_list.setCurrentItem(items[0])
                self.on_nav_selected(items[0])
            elif stats_item:
                # 如果找不到保存的导航项，则使用统计
                self.nav_list.setCurrentItem(stats_item)
                self.on_nav_selected(stats_item)
        elif stats_item:
            # 默认行为：跳转到统计
            self.nav_list.setCurrentItem(stats_item)
            self.on_nav_selected(stats_item)

    def on_nav_selected(self, item):
        title = item.text()
        self.last_nav_title = title
        course = self.course_box.currentData()
        
        self.content_title.setText(title)
        
        if "资料" in title:
            self.stacked_widget.setCurrentIndex(0)
            self.download_btn.show()
            self.start_loading_materials(course)
        elif "统计" in title:
            self.stacked_widget.setCurrentIndex(1)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.stats_view.on_show()
        elif "管理" in title:
            self.stacked_widget.setCurrentIndex(2)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.management_view.on_show()
        elif "活动" in title:
            self.stacked_widget.setCurrentIndex(3)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.activities_view.on_show()
        elif "题库" in title:
            self.stacked_widget.setCurrentIndex(4)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.question_bank_view.on_show()
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.material_tree.clear()
            self.download_btn.hide()
            self.status_label.setText(f"已选择功能: {title}")

    def start_loading_materials(self, course):
        self.status_label.setText(f"同步资料结构: {course.name} ...")
        self.material_tree.clear()
        
        self.worker = MaterialWorker(self.crawler, course)
        self.worker.materials_ready.connect(self.on_materials_loaded)
        self.worker.start()

    def on_materials_loaded(self, materials, course_name):
        if not materials:
            self.status_label.setText(f"资料结构为空: {course_name}")
            return
        for m in materials:
            tree_item = QTreeWidgetItem(self.material_tree)
            tree_item.setText(0, m.name)
            tree_item.setText(1, m.type)
            tree_item.setText(2, "可下载" if m.download_url else "已锁定/文件夹")
        self.status_label.setText(f"资料加载完成: {course_name}")

    def download_selected(self):
        # Implementation for downloading selected materials
        pass

    def on_logout_clicked(self):
        reply = QMessageBox.question(
            self, '退出登录', "确定要退出登录并清除保存的账号信息吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            settings = QSettings("HaoSoft", "XuexitongManager")
            settings.clear()
            self.status_label.setText("已清除登录信息，正在退出...")
            QCoreApplication.quit()

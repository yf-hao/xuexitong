import os
import traceback
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QComboBox, QTreeWidget, QTreeWidgetItem,
                             QHeaderView, QPushButton, QLabel, QSplitter, QFrame, QListView,
                             QStackedWidget, QMessageBox, QFileDialog)
from PyQt6.QtCore import QByteArray, QSize, Qt, QSettings, QCoreApplication
from ui.workers import (CourseWorker, DetailsWorker, ClassWorker, MaterialWorker, DownloadWorker)
from ui.styles import MAIN_STYLE
from ui.theme import apply_theme_stylesheet, get_theme_palette, refresh_theme_styles, theme_manager
from PyQt6.QtSvg import QSvgRenderer
from core.config import SIGNIN_DATA_FILE, APP_TITLE
from ui.views.stats_view import StatsView
from ui.views.management_view import ManagementView
from ui.views.activities_view import ActivitiesView
from ui.views.question_bank_view import QuestionBankView
from ui.views.learning_view import LearningView
from ui.views.study_status_view import StudyStatusView
from ui.views.homework_create_view import HomeworkCreateView
from ui.views.cloud_drive_view import CloudDriveView
from ui.views.notes_view import NotesView
from ui.views.chat_view import ChatView
from ui.dialogs.ai_settings_dialog import AISettingsDialog
from core.logger import get_logger

logger = get_logger()
NAV_GROUP_ROLE = int(Qt.ItemDataRole.UserRole) + 1

class MainWindow(QMainWindow):
    SELECTOR_MAX_WIDTH = 640

    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 900)
        self.worker = None 
        self.details_worker = None
        self.class_worker = None
        self.workers = [] # Keep references to prevent GC and crashes
        
        # State tracking for UI consistency
        self.last_nav_title = None
        
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
        self.course_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.course_box.setMaximumWidth(self.SELECTOR_MAX_WIDTH)
        self.course_box.setView(QListView())
        self.course_box.currentIndexChanged.connect(self.on_course_changed)
        header_layout.addWidget(self.course_box)
        
        header_layout.addSpacing(20)
        
        header_layout.addWidget(QLabel("选择班级:"))
        self.clazz_box = QComboBox()
        self.clazz_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.clazz_box.setMaximumWidth(self.SELECTOR_MAX_WIDTH)
        self.clazz_box.setView(QListView())
        self.clazz_box.currentIndexChanged.connect(self.on_class_selected)
        header_layout.addWidget(self.clazz_box)
        
        header_layout.addStretch()

        self.theme_toggle_btn = QPushButton("☀️")
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.setFixedSize(36, 36)
        self.theme_toggle_btn.clicked.connect(self._toggle_theme)
        apply_theme_stylesheet(self.theme_toggle_btn, lambda palette: f"""
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text_muted};
                border: 1px solid {palette.border};
                border-radius: 18px;
                padding: 0;
                font-size: 16px;
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: {palette.hover_bg};
                color: {palette.text};
                border: 1px solid {palette.accent};
            }}
        """)
        header_layout.addWidget(self.theme_toggle_btn)

        # AI Settings Button
        self.btn_ai_settings = QPushButton("🤖")
        self.btn_ai_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_settings.setToolTip("配置生成式AI答疑助手（API Key、模型、提示词）")
        self.btn_ai_settings.setFixedSize(36, 36)
        apply_theme_stylesheet(self.btn_ai_settings, lambda palette: f"""
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: #a8e6c1;
                border: 1px solid #2d7d46;
                border-radius: 18px;
                padding: 0;
                font-size: 16px;
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: #1a472a;
                color: #ffffff;
                border: 1px solid #4caf50;
            }}
        """)
        self.btn_ai_settings.clicked.connect(self._on_ai_settings_clicked)
        header_layout.addWidget(self.btn_ai_settings)

        # Logout Button
        self.btn_logout = QPushButton("🚪 退出登录")
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logout.setFixedWidth(120)
        apply_theme_stylesheet(self.btn_logout, lambda palette: f"""
            QPushButton {{
                background-color: transparent;
                color: {palette.warning};
                border: 1px solid {palette.warning};
                padding: 5px 10px;
                font-size: 13px;
                font-weight: normal;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {palette.warning};
                color: #ffffff;
            }}
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
        nav_label = QLabel("功能菜单")
        apply_theme_stylesheet(nav_label, lambda palette: f"""
            QLabel {{
                background-color: {palette.accent};
                color: #ffffff;
                border-radius: 6px;
                padding: 8px 12px;
                margin-bottom: 5px;
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        nav_layout.addWidget(nav_label)
        self.nav_list = QTreeWidget()
        self.nav_list.setObjectName("nav_list")
        self.nav_list.setColumnCount(2)
        self.nav_list.setHeaderHidden(True)
        self.nav_list.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.nav_list.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.nav_list.setColumnWidth(0, 42)
        self.nav_list.setRootIsDecorated(True)
        self.nav_list.setIndentation(8)
        self.nav_list.setItemsExpandable(True)
        self.nav_list.setExpandsOnDoubleClick(False)
        self.nav_list.setIconSize(QSize(18, 18))
        self.nav_list.setMinimumWidth(160)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.itemClicked.connect(self._on_nav_item_clicked)
        self.nav_list.itemExpanded.connect(self._save_nav_group_state)
        self.nav_list.itemCollapsed.connect(self._save_nav_group_state)
        nav_layout.addWidget(self.nav_list)
        splitter.addWidget(nav_container)
        
        # Main Area: Content View
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(5, 0, 0, 0)
        
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

        # Page 5: Learning View
        self.learning_view = LearningView(self.crawler, self._update_status, parent=self)
        self.stacked_widget.addWidget(self.learning_view)
        
        # Page 6: Study Status View
        self.study_status_view = StudyStatusView(self.crawler, parent=self)
        self.study_status_view.status_update.connect(self._update_status)
        self.stacked_widget.addWidget(self.study_status_view)

        # Page 7: Homework Create View
        self.homework_create_view = HomeworkCreateView(self.crawler, parent=self)
        self.homework_create_view.status_update.connect(self._update_status)
        self.stacked_widget.addWidget(self.homework_create_view)

        # Page 8: Cloud Drive View
        self.cloud_drive_view = CloudDriveView(self.crawler, parent=self)
        self.cloud_drive_view.status_update.connect(self._update_status)
        self.stacked_widget.addWidget(self.cloud_drive_view)

        # Page 9: Notes View
        self.notes_view = NotesView(self.crawler, parent=self)
        self.stacked_widget.addWidget(self.notes_view)

        # Page 10: Chat View
        self.chat_view = ChatView(self.crawler, parent=self)
        self.chat_view.msync_status_changed.connect(self._update_status)
        self.stacked_widget.addWidget(self.chat_view)

        content_layout.addWidget(self.stacked_widget)
        splitter.addWidget(content_container)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
        
        # Bottom Bar
        self.bottom_widget = QFrame()
        self.bottom_widget.setFixedHeight(30)
        apply_theme_stylesheet(self.bottom_widget, lambda palette: f"background: transparent; border-top: 1px solid {palette.border};")
        bottom_bar = QHBoxLayout(self.bottom_widget)
        
        self.status_label = QLabel("正在初始化...")
        apply_theme_stylesheet(self.status_label, lambda palette: f"font-weight: normal; color: {palette.accent}; font-size: 12px; border: none;")
        self.download_btn = QPushButton("下载选中资料")
        self.download_btn.setMinimumWidth(180)
        self.download_btn.clicked.connect(self.download_selected)
        
        bottom_bar.addWidget(self.status_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.download_btn)
        main_layout.addWidget(self.bottom_widget)
        
        self.load_courses()
        theme_manager().theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager().mode)

    def _toggle_theme(self):
        mode = theme_manager().mode
        theme_manager().set_mode("dark" if mode == "light" else "light")

    def _apply_theme(self, mode):
        apply_theme_stylesheet(self, MAIN_STYLE, mode)
        if mode == "light":
            self.theme_toggle_btn.setText("🌙")
            self.theme_toggle_btn.setToolTip("切换到暗色主题")
        else:
            self.theme_toggle_btn.setText("☀️")
            self.theme_toggle_btn.setToolTip("切换到亮色主题")
        refresh_theme_styles(self, mode)
        self._update_nav_group_icons(mode)

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

    def load_courses(self):
        self.status_label.setText("正在异步加载课程列表...")
        self.course_box.blockSignals(True)
        self.course_box.clear()
        
        self.course_loader = CourseWorker(self.crawler)
        self.course_loader.courses_ready.connect(self.on_courses_delivered)
        self.course_loader.start()

    def on_courses_delivered(self, courses):
        # 显示所有课程，已结课的标记“(已结课)”以便新建课程立即可见
        ongoing_courses = [c for c in courses if not c.is_finished]
        finished_courses = [c for c in courses if c.is_finished]

        for course in ongoing_courses:
            self.course_box.addItem(course.name, course)
        for course in finished_courses:
            self.course_box.addItem(f"{course.name} (已结课)", course)
            
        self.status_label.setText(
            f"就绪，共 {len(courses)} 门课程，进行中 {len(ongoing_courses)} 门，已结课 {len(finished_courses)} 门"
        )
        if courses:
            settings = QSettings("HaoSoft", "XuexitongManager")
            last_course_id = settings.value("last_course_id", "")

            selected_index = 0
            if last_course_id:
                for i in range(self.course_box.count()):
                    course = self.course_box.itemData(i)
                    if course and str(course.id) == str(last_course_id):
                        selected_index = i
                        break

            # 手动触发课程切换，blockSignals避免setCurrentIndex触发信号导致重复调用
            self.course_box.setCurrentIndex(selected_index)
            self.course_box.blockSignals(False)
            self.on_course_changed(selected_index)
        else:
            self.course_box.blockSignals(False)

    def on_course_changed(self, index):
        course = self.course_box.itemData(index)
        if not course: return

        settings = QSettings("HaoSoft", "XuexitongManager")
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

    def refresh_class_list(self):
        """重新拉取当前课程的班级列表，并尽量保留当前班级选择。"""
        course = self.course_box.currentData()
        if not course:
            return

        current_class_id = self.clazz_box.currentData()
        self.status_label.setText(f"正在刷新班级列表: {course.name}...")

        self.class_worker = ClassWorker(self.crawler, course)
        self.class_worker.classes_ready.connect(
            lambda classes, current_course, preferred_class_id=current_class_id: self.on_classes_loaded(
                classes, current_course, preferred_class_id
            )
        )
        self.class_worker.start()

    def on_classes_loaded(self, classes, course, preferred_class_id=None):
        self.clazz_box.blockSignals(True)
        self.clazz_box.clear()
        
        ongoing_classes = [c for c in classes if not c.get('finished', False)]
        
        for c in ongoing_classes:
            self.clazz_box.addItem(c['name'], c['id'])
        self.clazz_box.blockSignals(False)
        
        if ongoing_classes:
            selected_index = 0
            if preferred_class_id:
                for i in range(self.clazz_box.count()):
                    class_id = self.clazz_box.itemData(i)
                    if str(class_id) == str(preferred_class_id):
                        selected_index = i
                        break

            self.clazz_box.setCurrentIndex(selected_index)
            hidden_count = len(classes) - len(ongoing_classes)
            if hidden_count > 0:
                self.status_label.setText(f"已加载 {len(ongoing_classes)} 个进行中的班级 (已隐藏 {hidden_count} 个结课班级)")
        else:
            self.status_label.setText(f"提示: {course.name} 下未找到正在进行中的班级 (已过滤 {len(classes)} 个结课班级)")

    def on_class_selected(self, index):
        class_id = self.clazz_box.itemData(index)
        course = self.course_box.currentData()
        if class_id and course:
            self.crawler.session_manager.course_params['clazzid'] = class_id
            self.status_label.setText(f"切换班级 {class_id}")
            
            self.details_worker = DetailsWorker(self.crawler, course)
            self.details_worker.details_ready.connect(lambda d, c: self.on_class_params_refreshed(d, c))
            self.details_worker.start()

    def on_class_params_refreshed(self, details, course):
        self.status_label.setText(f"授权同步完成")
        
        current_nav = self.nav_list.currentItem()
        if not current_nav and self.last_nav_title:
            items = self.nav_list.findItems(self.last_nav_title, Qt.MatchFlag.MatchExactly, 1)
            if items:
                current_nav = items[0]
                self.nav_list.setCurrentItem(current_nav)

        if current_nav:
            self.on_nav_selected(current_nav)
            
            # Restore sub-feature
            title = current_nav.text(1)
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
        skip_keywords = ["AI工作台", "任务引擎", "课件","教案","章节","考试","资料","通知","讨论","课程图谱","AI知识库","直播课/见面课"]
        
        # 过滤掉不需要的项目
        filtered_links = []
        for link in nav_links:
            if any(k in link['title'] for k in skip_keywords):
                continue
            filtered_links.append(link)
        
        course_group = self._add_nav_group("course", "课程功能")
        shared_group = self._add_nav_group("shared", "通用功能")
        self._update_nav_group_icons(theme_manager().mode)

        # Keep course-bound items separate from account-wide tools.
        menu_order = ["活动", "题库", "作业","学情", "统计", "笔记", "云盘", "消息", "管理"]
        
        for keyword in menu_order:
            if keyword == "题库":
                self._add_nav_item(shared_group, "题库", "question_bank")
            elif keyword == "学情":
                self._add_nav_item(course_group, "学情", "learning")
            elif keyword == "云盘":
                self._add_nav_item(shared_group, "云盘", "cloud_drive")
            elif keyword == "笔记":
                self._add_nav_item(shared_group, "笔记", "notes")
            elif keyword == "消息":
                self._add_nav_item(shared_group, "消息", "chat")
            else:
                # 从 filtered_links 中查找匹配的项目
                for link in filtered_links:
                    if keyword in link['title']:
                        display_title = "签到" if keyword == "活动" else link['title']
                        self._add_nav_item(course_group, display_title, link['url'])
                        break
            
        self.status_label.setText(f"目录同步完成: {course.name}")
        self.nav_list.clearSelection()
        self.download_btn.hide()

    def _add_nav_group(self, group_id, title):
        item = QTreeWidgetItem(self.nav_list, ["", title])
        item.setData(0, NAV_GROUP_ROLE, group_id)
        font = item.font(1)
        font.setBold(True)
        item.setFont(1, font)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        settings = QSettings("HaoSoft", "XuexitongManager")
        expanded = settings.value(
            f"ui/navigation_groups/{group_id}_expanded", True, type=bool
        )
        item.setExpanded(expanded)
        return item

    def _update_nav_group_icons(self, mode):
        color = get_theme_palette(mode).text_muted
        svg_by_group = {
            "course": f"""<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 6.2c-2-1.4-4.8-2-8-1.7v13c3.2-.3 6 .3 8 1.7m0-13c2-1.4 4.8-2 8-1.7v13c-3.2-.3-6 .3-8 1.7m0-13v13" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>""",
            "shared": f"""<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none">
                <rect x="4" y="4" width="6.5" height="6.5" rx="1.2" stroke="{color}" stroke-width="1.8"/>
                <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2" stroke="{color}" stroke-width="1.8"/>
                <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2" stroke="{color}" stroke-width="1.8"/>
                <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2" stroke="{color}" stroke-width="1.8"/>
            </svg>""",
        }
        for index in range(self.nav_list.topLevelItemCount()):
            item = self.nav_list.topLevelItem(index)
            svg = svg_by_group.get(item.data(0, NAV_GROUP_ROLE))
            if not svg:
                continue
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            pixmap = QPixmap(18, 18)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            item.setIcon(0, QIcon(pixmap))

    @staticmethod
    def _add_nav_item(parent, title, action):
        item = QTreeWidgetItem(parent, ["", title])
        item.setData(0, Qt.ItemDataRole.UserRole, action)
        return item

    def _on_nav_item_clicked(self, item, _column):
        if item.data(0, NAV_GROUP_ROLE):
            item.setExpanded(not item.isExpanded())
            return
        self.on_nav_selected(item)

    @staticmethod
    def _save_nav_group_state(item):
        group_id = item.data(0, NAV_GROUP_ROLE)
        if not group_id:
            return
        settings = QSettings("HaoSoft", "XuexitongManager")
        settings.setValue(
            f"ui/navigation_groups/{group_id}_expanded", item.isExpanded()
        )

    def on_nav_selected(self, item):
        if item is None or item.parent() is None:
            return
        title = item.text(1)
        self.last_nav_title = title
        course = self.course_box.currentData()
        is_activity_page = "活动" in title or "签到" in title
        if self.stacked_widget.currentIndex() == 3 and not is_activity_page:
            self.activities_view.on_hide()
        
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
        elif "活动" in title or "签到" in title:
            self.stacked_widget.setCurrentIndex(3)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.activities_view.on_show()
        elif "题库" in title:
            self.stacked_widget.setCurrentIndex(4)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.question_bank_view.on_show()
        elif "学情" in title:
            self.stacked_widget.setCurrentIndex(6)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.study_status_view.on_show()
        elif "作业" in title:
            self.stacked_widget.setCurrentIndex(7)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.homework_create_view.on_show()
        elif "云盘" in title:
            self.stacked_widget.setCurrentIndex(8)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.cloud_drive_view.on_show()
        elif "笔记" in title:
            self.stacked_widget.setCurrentIndex(9)
            self.download_btn.hide()
            self.status_label.setText(f"已进入: {title}")
            self.notes_view.on_show()
        elif "消息" in title or "聊天" in title:
            self.stacked_widget.setCurrentIndex(10)
            self.download_btn.hide()
            self.status_label.setText(f"已进入：{title}")
            self.chat_view.on_show()
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.material_tree.clear()
            self.download_btn.hide()
            self.status_label.setText(f"已选择功能: {title}")

    def _on_ai_settings_clicked(self):
        """打开 AI 设置对话框"""
        dialog = AISettingsDialog(self)
        dialog.exec()

    def _stop_qthread(self, worker, timeout_ms: int = 3000):
        """在窗口关闭前等待后台 QThread 结束，避免对象析构时线程仍在运行。"""
        if not worker:
            return
        try:
            if worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                worker.wait(timeout_ms)
        except Exception:
            pass

    def closeEvent(self, event):
        """窗口关闭事件，保存相关状态并退出系统"""
        try:
            # 先等待主窗口自身启动的后台 worker 结束
            try:
                owned_workers = [
                    getattr(self, "course_loader", None),
                    getattr(self, "details_worker", None),
                    getattr(self, "class_worker", None),
                    getattr(self, "worker", None),
                    *list(getattr(self, "workers", []) or []),
                ]
            except Exception:
                owned_workers = []

            for worker in owned_workers:
                self._stop_qthread(worker)

            # 停止已知子视图的后台工作，尤其是聊天实时连接
            for view in [
                getattr(self, "chat_view", None),
                getattr(self, "cloud_drive_view", None),
                getattr(self, "notes_view", None),
                getattr(self, "question_bank_view", None),
                getattr(self, "study_status_view", None),
                getattr(self, "homework_create_view", None),
            ]:
                if view and hasattr(view, "stop_workers"):
                    try:
                        view.stop_workers()
                    except Exception:
                        pass

            # 关闭 session manager (保存 cookie 等)
            if self.crawler and self.crawler.session_manager:
                try:
                    self.crawler.session_manager.close()
                except Exception:
                    pass
        except Exception:
            logger.error("MainWindow.closeEvent exception:\n%s", traceback.format_exc())
        finally:
            event.accept()

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
        settings = QSettings("HaoSoft", "XuexitongManager")
        settings.clear()
        self.status_label.setText("已清除登录信息，正在退出...")
        QCoreApplication.quit()

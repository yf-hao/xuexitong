import json
import os
import random
import copy
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLabel, QFrame, QScrollArea, QComboBox, 
    QSpinBox, QDateEdit, QGroupBox, QInputDialog, QMessageBox,
    QListView, QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, QDate, QTimer
from ui.workers import (
    GroupWorker, AddGroupWorker, RenameWorker, DeleteGroupWorker, 
    PublishSigninWorker, DeleteSigninWorker
)
from ui.styles import STAT_BUTTON_STYLE, STAT_CARD_CONTAINER_STYLE
from core.config import SIGNIN_DATA_FILE, LOCATION_DATA_FILE, DEFAULT_COMMON_LOCATIONS

class ActivitiesView(QWidget):
    def __init__(self, crawler, status_callback, get_course_callback, get_class_name_callback, get_class_id_callback, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.status_callback = status_callback
        self.get_course_callback = get_course_callback
        self.get_class_name_callback = get_class_name_callback
        self.get_class_id_callback = get_class_id_callback
        self.workers = []
        self.last_activity_sub = None
        
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QGridLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.layout.setContentsMargins(10, 20, 10, 10)
        self.layout.setSpacing(25)
        
        # Buttons
        self.btn_signin = QPushButton("📍 签到")
        self.btn_questionnaire = QPushButton("📝 问卷")
        self.btn_practice = QPushButton("✏️ 随堂练习")
        self.btn_group_manage = QPushButton("👥 活动分组")
        
        self.buttons = [
            self.btn_signin, self.btn_questionnaire, 
            self.btn_practice, self.btn_group_manage
        ]
        
        for btn in self.buttons:
            btn.setStyleSheet(STAT_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
        self.btn_questionnaire.setEnabled(False)
        self.btn_questionnaire.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn_questionnaire.setText("📝 问卷 (敬请期待)")
        
        self.btn_practice.setEnabled(False)
        self.btn_practice.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn_practice.setText("✏️ 随堂练习 (敬请期待)")

        self.layout.addWidget(self.btn_signin, 0, 0)
        self.layout.addWidget(self.btn_questionnaire, 0, 1)
        self.layout.addWidget(self.btn_practice, 0, 2)
        self.layout.addWidget(self.btn_group_manage, 0, 3)
        
        # Result area
        self.activities_scroll = QFrame()
        self.activities_scroll.setStyleSheet(STAT_CARD_CONTAINER_STYLE)
        self.activities_scroll_layout = QVBoxLayout(self.activities_scroll)
        self.activities_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.activities_scroll_layout.setSpacing(10)
        
        self.activities_scroll_area = QScrollArea()
        self.activities_scroll_area.setWidgetResizable(True)
        self.activities_scroll_area.setWidget(self.activities_scroll)
        self.activities_scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.layout.addWidget(self.activities_scroll_area, 1, 0, 1, 4)
        
        # Connect signals
        self.btn_signin.clicked.connect(self.on_signin_clicked)
        self.btn_questionnaire.clicked.connect(self.on_questionnaire_clicked)
        self.btn_practice.clicked.connect(self.on_practice_clicked)
        self.btn_group_manage.clicked.connect(self.on_group_manage_clicked)

    def clear_activities_list(self):
        while self.activities_scroll_layout.count():
            item = self.activities_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def on_signin_clicked(self):
        self.last_activity_sub = "signin"
        self.clear_activities_list()
        
        # 1. Configuration Box
        config_box = self._setup_signin_config_ui()
        self.activities_scroll_layout.addWidget(config_box)
        
        # 1.5. Load locations to combo
        self._load_locations_to_combo()
        
        # 2. Results Container
        self.signin_results_widget = QWidget()
        self.signin_results_layout = QVBoxLayout(self.signin_results_widget)
        self.signin_results_layout.setContentsMargins(0, 10, 0, 0)
        self.signin_results_layout.setSpacing(10)
        self.activities_scroll_layout.addWidget(self.signin_results_widget)

        # 3. Load existing plans
        plans = self._load_signin_plans()
        key = self._get_current_key()
        
        if key and key in plans:
            data = plans[key]
            # Handle both old (list) and new (dict) formats
            if isinstance(data, dict):
                config = data.get("config", {})
                items = data.get("items", [])
                
                # Restore config to UI
                if "start_date" in config:
                    self.start_date_edit.setDate(QDate.fromString(config["start_date"], Qt.DateFormat.ISODate))
                if "odd" in config:
                    self.odd_times.setValue(config["odd"])
                if "even" in config:
                    self.even_times.setValue(config["even"])
                if "weeks" in config:
                    self.total_weeks.setValue(config["weeks"])
            else:
                items = data
            #self.current_session_items = [it for it in items if not it.get('published', False)]
            self.current_session_items = items
            self._display_signin_items(self.current_session_items)
            self.status_callback(f"已加载保存的签到计划 ({key})")
        else:
            self.current_session_items = []
            self.status_callback("签到批量预设模式 - 请点击生成列表")
            
        # 4. Fetch groups
        course = self.get_course_callback()
        class_id = self.get_class_id_callback()
        if course:
            worker = GroupWorker(self.crawler, course.id, class_id)
            self.workers.append(worker)
            worker.groups_ready.connect(self._populate_signin_groups)
            worker.groups_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _setup_signin_config_ui(self):
        config_box = QGroupBox("")
        config_box.setStyleSheet("""
            QGroupBox {
                border: 2px solid #333333;
                border-radius: 10px;
                padding-top: 15px;
            }
        """)
        config_layout = QGridLayout(config_box)
        config_layout.setSpacing(15)

        # UI elements
        lbl_date = QLabel("📅 第一周周一")
        lbl_date.setStyleSheet("font-size: 14px; color: #ffffff;")
        config_layout.addWidget(lbl_date, 0, 0)
        self.start_date_edit = QDateEdit(QDate.currentDate())
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setMinimumHeight(35)
        self.start_date_edit.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 4px; padding-left: 5px;")
        config_layout.addWidget(self.start_date_edit, 0, 1)

        lbl_group = QLabel("👥 活动分组")
        lbl_group.setStyleSheet("font-size: 14px; color: #ffffff; margin-left: 10px;")
        config_layout.addWidget(lbl_group, 0, 2)
        self.group_combo = QComboBox()
        self.group_combo.setView(QListView())
        self.group_combo.setMinimumHeight(35)
        self.group_combo.setMinimumWidth(180)
        self.group_combo.setStyleSheet("""
            QComboBox {
                background: #252526; 
                color: white; 
                border: 1px solid #444; 
                border-radius: 4px;
                padding-left: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                selection-background-color: #007acc;
                outline: none;
            }
            QListView::item {
                min-height: 35px;
                padding-left: 10px;
            }
            QListView::item:hover {
                background-color: #007acc;
                color: #ffffff;
            }
        """)
        self.group_combo.addItem("正在加载分组...", None)
        config_layout.addWidget(self.group_combo, 0, 3, 1, 3)

        lbl_weeks = QLabel("🗓️ 总周数")
        lbl_weeks.setStyleSheet("font-size: 14px; color: #ffffff;")
        config_layout.addWidget(lbl_weeks, 1, 0)
        self.total_weeks = QSpinBox()
        self.total_weeks.setRange(1, 52)
        self.total_weeks.setValue(16)
        self.total_weeks.setMinimumHeight(35)
        self.total_weeks.setFixedWidth(60)
        self.total_weeks.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 4px;")
        config_layout.addWidget(self.total_weeks, 1, 1)

        lbl_odd = QLabel("🔢 单周次数")
        lbl_odd.setStyleSheet("font-size: 14px; color: #ffffff; margin-left: 10px;")
        config_layout.addWidget(lbl_odd, 1, 2)
        self.odd_times = QSpinBox()
        self.odd_times.setRange(0, 10)
        self.odd_times.setValue(2)
        self.odd_times.setMinimumHeight(35)
        self.odd_times.setFixedWidth(60)
        self.odd_times.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 4px;")
        config_layout.addWidget(self.odd_times, 1, 3)

        lbl_even = QLabel("🔠 双周次数")
        lbl_even.setStyleSheet("font-size: 14px; color: #ffffff; margin-left: 10px;")
        config_layout.addWidget(lbl_even, 1, 4)
        self.even_times = QSpinBox()
        self.even_times.setRange(0, 10)
        self.even_times.setValue(2)
        self.even_times.setMinimumHeight(35)
        self.even_times.setFixedWidth(60)
        self.even_times.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 4px;")
        config_layout.addWidget(self.even_times, 1, 5)

        # === 位置签到配置 ===
        self.chk_enable_location = QCheckBox("启用位置签到")
        self.chk_enable_location.setStyleSheet("""
            QCheckBox {
                font-size: 13px;
                color: #ffffff;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #666;
                border-radius: 3px;
                background: #252526;
            }
            QCheckBox::indicator:hover {
                border: 2px solid #007acc;
                background: #2d2d2d;
            }
            QCheckBox::indicator:checked {
                background: #007acc;
                border: 2px solid #007acc;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEwIDNMNC41IDguNUwyIDYiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPg==);
            }
        """)
        config_layout.addWidget(self.chk_enable_location, 2, 0)
        
        # 位置下拉框
        self.combo_location = QComboBox()
        self.combo_location.setMinimumHeight(35)
        self.combo_location.setMinimumWidth(180)
        self.combo_location.setStyleSheet("""
            QComboBox {
                background: #252526; 
                color: white; 
                border: 1px solid #444; 
                border-radius: 4px;
                padding-left: 5px;
            }
            QComboBox:disabled {
                background: #1a1a1a;
                color: #666666;
                border: 1px solid #333;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                selection-background-color: #007acc;
                outline: none;
            }
            QListView::item {
                min-height: 35px;
                padding-left: 10px;
            }
            QListView::item:hover {
                background-color: #007acc;
                color: #ffffff;
            }
        """)
        self.combo_location.addItem("暂无位置数据", None)
        config_layout.addWidget(self.combo_location, 2, 1)
        
        # 位置配置按钮
        self.btn_config_location = QPushButton("位置模板")
        self.btn_config_location.setFixedHeight(35)
        self.btn_config_location.setMinimumWidth(70)
        self.btn_config_location.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_config_location.setStyleSheet("""
            QPushButton { 
                background-color: #0078d4; 
                color: #ffffff; 
                border: none;
                border-radius: 4px; 
                font-size: 13px;
                font-weight: bold;
                padding: 0 10px;
            }
            QPushButton:hover { 
                background-color: #1e90ff; 
            }
            QPushButton:pressed { 
                background-color: #0066b8; 
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        config_layout.addWidget(self.btn_config_location, 2, 2)
        
        # 连接信号
        self.chk_enable_location.stateChanged.connect(self._on_location_enable_changed)
        self.combo_location.currentIndexChanged.connect(self._on_location_combo_changed)
        self.btn_config_location.clicked.connect(self._on_config_location_clicked)
        
        # 初始状态
        self._update_location_ui_state()

        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        self.btn_generate = QPushButton("⚡ 生成列表")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; border-radius: 6px; padding: 10px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #1a8ad4; }
        """)
        self.btn_generate.clicked.connect(self._generate_signin_items)
        
        self.btn_batch_publish = QPushButton("🚀 一键发布")
        self.btn_batch_publish.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_publish.setStyleSheet("""
            QPushButton { background-color: #4ec9b0; color: white; border-radius: 6px; padding: 10px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #45b79d; }
            QPushButton:disabled { background-color: #3e3e42; color: #888888; }
        """)
        self.btn_batch_publish.clicked.connect(self._handle_batch_publish)
        
        button_layout.addWidget(self.btn_generate)
        button_layout.addWidget(self.btn_batch_publish)
        
        config_layout.addLayout(button_layout, 5, 0, 1, 6)
        
        return config_box

    def _populate_signin_groups(self, result):
        if not hasattr(self, 'group_combo'): return
        
        self.group_combo.clear()
        self.group_combo.addItem("--- 请选择活动分组 ---", None)
        
        if isinstance(result, list):
            for group in result:
                self.group_combo.addItem(f"👥 {group.get('name')}", group.get('id'))
                
        # Restore saved group selection
        plans = self._load_signin_plans()
        key = self._get_current_key()
        if key and key in plans:
            saved_config = plans[key].get("config", {})
            saved_group_id = saved_config.get("planId")
            if saved_group_id:
                index = self.group_combo.findData(saved_group_id)
                if index >= 0:
                    self.group_combo.setCurrentIndex(index)

    def _get_current_key(self):
        params = self.crawler.session_manager.course_params
        cid = params.get('courseid')
        clazz = params.get('clazzid')
        return f"{cid}_{clazz}" if cid and clazz else None



    def _load_signin_plans(self):
        if os.path.exists(SIGNIN_DATA_FILE):
            try:
                with open(SIGNIN_DATA_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_signin_plans(self, plans):
        try:
            with open(SIGNIN_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(plans, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Save error: {e}")

    def _generate_signin_items(self):
        key = self._get_current_key()
        if not key:
            QMessageBox.warning(self, "错误", "未能识别当前课程或班级信息")
            return
            
        plans = self._load_signin_plans()
        if key in plans:
            reply = QMessageBox.question(
                self, '确认生成', 
                f"班级 {key} 已存在签到计划，重新生成将覆盖并重置所有记录。\n\n是否确定要重新生成？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        odd_val = self.odd_times.value()
        even_val = self.even_times.value()
        weeks_val = self.total_weeks.value()
        plan_id = self.group_combo.currentData()
        
        if not plan_id:
            QMessageBox.warning(self, "错误", "请先选择所属的分组")
            return
            
        cid, clazz = key.split('_')
        start_date = self.start_date_edit.date()
        
        new_items = []
        for week in range(1, weeks_val + 1):
            # Calculate date range for this week
            week_start_date = start_date.addDays((week - 1) * 7)
            week_end_date = week_start_date.addDays(6)
            date_range_str = f"{week_start_date.toString('yyyy.MM.dd')}-{week_end_date.toString('yyyy.MM.dd')}"
            
            current_week_times = odd_val if week % 2 != 0 else even_val
            for count in range(1, current_week_times + 1):
                chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                sc = "".join(random.choice(chars[1:]) for _ in range(5))
                
                new_items.append({
                    "name": f"{week}-{count}", 
                    "date": date_range_str,
                    "dateRange": date_range_str,
                    "published": False,
                    "courseId": cid,
                    "classId": clazz,
                    "planId": plan_id,
                    "signcode": sc,
                    "otherId": 2,
                    "ifNeedVCode": 1,
                    "openCheckWeChatFlag": 1,
                    "openCheckFaceFlag": 1,
                    "ifrefreshewm": 1,
                    "ewmRefreshTime": 10,
                    "now": 0
                })

        plans = self._load_signin_plans()
        key = self._get_current_key()
        if key:
            plans[key] = {
                "config": {
                    "start_date": self.start_date_edit.date().toString(Qt.DateFormat.ISODate),
                    "odd": odd_val,
                    "even": even_val,
                    "weeks": weeks_val,
                    "planId": plan_id,
                    "courseName": getattr(self.get_course_callback(), 'name', '未知课程'),
                    "className": self.get_class_name_callback()
                },
                "items": new_items
            }
            self._save_signin_plans(plans)
            self.current_session_items = new_items
            self._display_signin_items(self.current_session_items)
            self.status_callback(f"已生成并保存 {len(new_items)} 个签到计划")

    def _display_signin_items(self, items):
        while self.signin_results_layout.count():
            w = self.signin_results_layout.takeAt(0).widget()
            if w: w.deleteLater()

        displayed_count = 0
        for item in items:
            displayed_count += 1
            name = item['name']
            is_published = item.get('published', False)
            
            card = QFrame()
            card.setObjectName("signin_card")
            card.setStyleSheet(f"""
                QFrame#signin_card {{ 
                    background-color: {'#2d2d2d' if is_published else '#1e1e1e'}; 
                    border: 1px solid {'#444' if is_published else '#333333'}; 
                    border-radius: 8px; 
                    padding: 10px; 
                }}
                QFrame#signin_card:hover {{ border: 1px solid {'#444' if is_published else '#007acc'}; }}
            """)
            card_layout = QHBoxLayout(card)
            
            title_lbl = QLabel(f"📍 签到: {name}")
            title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {'#888888' if is_published else '#ffffff'};")
            card_layout.addWidget(title_lbl)
            
            date_val = item.get("date") or item.get("dateRange", "")
            if date_val:
                date_lbl = QLabel(f"({date_val})")
                date_lbl.setStyleSheet(f"font-size: 12px; color: {'#555555' if is_published else '#aaaaaa'}; margin-left: 5px;")
                card_layout.addWidget(date_lbl)
                
            card_layout.addStretch()
            
            pub_btn = QPushButton("已发布" if is_published else "发布此签到")
            pub_btn.setFixedWidth(100)
            pub_btn.setEnabled(not is_published)
            
            if is_published:
                pub_btn.setStyleSheet("""
                    QPushButton { background-color: #3e3e42; color: #888888; border-radius: 4px; padding: 5px; font-size: 12px; }
                """)
            else:
                pub_btn.setStyleSheet("""
                    QPushButton { background-color: #28a745; color: white; border-radius: 4px; padding: 5px; font-size: 12px; }
                    QPushButton:hover { background-color: #218838; }
                """)
                pub_btn.clicked.connect(lambda checked, n=name: self._handle_publish_action(n))
            
            card_layout.addWidget(pub_btn)

            # Add Delete Button
            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(60)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet("""
                QPushButton { background-color: #442222; color: #ff8888; border: 1px solid #ff4d4d; border-radius: 4px; padding: 5px; font-size: 12px; }
                QPushButton:hover { background-color: #ff4d4d; color: white; }
            """)
            del_btn.clicked.connect(lambda checked, n=name, pub=is_published, aid=item.get('activeId'): self._handle_delete_action(n, pub, aid))
            card_layout.addWidget(del_btn)

            self.signin_results_layout.addWidget(card)
        
        if displayed_count == 0:
            self.signin_results_layout.addWidget(QLabel("✅ 暂无待发布的签到任务"))

    def _handle_batch_publish(self):
        if not hasattr(self, 'current_session_items') or not self.current_session_items:
            QMessageBox.warning(self, "错误", "暂无签到计划可以发布，请先生成列表。")
            return
            
        items_to_publish = [it for it in self.current_session_items if not it.get('published', False)]
        if not items_to_publish:
            QMessageBox.information(self, "提示", "所有签到计划均已发布。")
            return
        
        # 检查位置签到配置
        if hasattr(self, 'chk_enable_location') and self.chk_enable_location.isChecked():
            selected_data = self.combo_location.currentData()
            
            # 判断是否有有效位置
            has_location = False
            if selected_data is None:
                has_location = False
            elif isinstance(selected_data, dict) and selected_data.get("template"):
                # 选择了位置模板，检查是否有配置
                # 只检查第一个待发布任务的位置配置
                first_item = items_to_publish[0]
                location = self._get_location_from_template(first_item.get('name', ''))
                has_location = location is not None
            else:
                has_location = True
            
            if not has_location:
                QMessageBox.warning(self, "提示", "已启用位置签到，但未选择位置。\n\n请在下拉框中选择位置或启用位置模板。")
                return
            
        reply = QMessageBox.question(
            self, "确认一键发布", 
            f"在泛雅中，先发布的签到会显示在后面，所以将按逆序发布剩余的 {len(items_to_publish)} 个签到任务!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # We want to publish in reverse order (e.g., 16-2, 16-1, ... 1-1)
            # The items are already in order, so we just reverse the list of un-published items
            self.batch_queue = items_to_publish[::-1]
            self.btn_batch_publish.setEnabled(False)
            self._publish_next_in_batch()

    def _build_publish_params(self, item: dict) -> dict:
        """统一构建发布参数 - DRY原则"""
        params = {
            "title": item.get('name'),
            "courseId": item.get('courseId'),
            "classId": item.get('classId'),
            "planId": item.get('planId'),
            "signCode": item.get('signcode'),
            "otherId": item.get('otherId', 2),
            "ifNeedVCode": item.get('ifNeedVCode', 1),
            "openCheckWeChatFlag": item.get('openCheckWeChatFlag', 1),
            "openCheckFaceFlag": item.get('openCheckFaceFlag', 0),
            "ifrefreshewm": item.get('ifrefreshewm', 1),
            "ewmRefreshTime": item.get('ewmRefreshTime', 10),
            "now": item.get('now', 0)
        }
        
        # 添加位置签到参数
        if hasattr(self, 'chk_enable_location') and self.chk_enable_location.isChecked():
            selected_data = self.combo_location.currentData()
            selected_location = None
            
            # 判断选择类型
            if selected_data is None:
                # "-- 手动选择位置 --" 或未选择，不使用位置
                pass
            elif isinstance(selected_data, dict) and selected_data.get("template"):
                # 选择了"启用位置模板"，从模板获取位置
                selected_location = self._get_location_from_template(item.get('name', ''))
            else:
                # 选择了具体位置
                selected_location = selected_data
            
            if selected_location:
                location_name = selected_location.get("name", "")
                params["ifopenAddress"] = "1"  # 开启位置签到
                params["locationText"] = f"郑州市新郑市 {location_name}"
                params["locationLatitude"] = str(selected_location.get("latitude"))
                params["locationLongitude"] = str(selected_location.get("longitude"))
                params["locationRange"] = str(selected_location.get("range", 500))
            else:
                params["ifopenAddress"] = "0"  # 未选择位置
        else:
            params["ifopenAddress"] = "0"  # 未启用位置签到
        
        return params
    
    def _get_location_from_template(self, item_name: str) -> dict:
        """根据签到名称从位置模板获取自动位置
        
        Args:
            item_name: 签到名称，格式如 "16-1" 表示第16周第1次课
            
        Returns:
            位置字典，如果未配置则返回None
        """
        import json
        import os
        from core.config import LOCATION_DATA_FILE, DEFAULT_LOCATION_TEMPLATE, DEFAULT_COMMON_LOCATIONS
        
        # 解析周次和课次
        try:
            parts = item_name.split('-')
            if len(parts) != 2:
                return None
            week = int(parts[0])
            slot_index = int(parts[1]) - 1  # 转为0-based索引
        except (ValueError, IndexError):
            return None
        
        # 加载位置模板配置
        template = None
        if os.path.exists(LOCATION_DATA_FILE):
            try:
                with open(LOCATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    template = data.get("locationTemplate", {})
            except:
                pass
        
        if not template:
            template = DEFAULT_LOCATION_TEMPLATE.copy()
        
        # 检查模板是否启用
        if not template.get("enabled", False):
            return None
        
        # 获取常用位置列表（用于查找位置详情）
        # 合并内置位置和用户自定义位置
        user_locations = []
        if os.path.exists(LOCATION_DATA_FILE):
            try:
                with open(LOCATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    user_locations = data.get("customLocations", [])
            except:
                pass
        
        built_in_names = {loc.get("name") for loc in DEFAULT_COMMON_LOCATIONS}
        common_locations = list(DEFAULT_COMMON_LOCATIONS) + [
            loc for loc in user_locations 
            if loc.get("name") not in built_in_names
        ]
        
        # 根据模式选择位置
        mode = template.get("mode", "weekly")
        
        if mode == "weekly":
            # 每周重复模式
            slots = template.get("weeklySlots", [])
        else:
            # 单双周不同模式
            if week % 2 == 1:  # 单周
                slots = template.get("oddSlots", [])
            else:  # 双周
                slots = template.get("evenSlots", [])
        
        # 获取对应课次的位置
        if slot_index < len(slots):
            slot_data = slots[slot_index]
            if slot_data:
                # slot_data 可能是完整位置对象或位置名称
                if isinstance(slot_data, dict):
                    return slot_data
                elif isinstance(slot_data, str):
                    # 按名称查找位置
                    for loc in common_locations:
                        if loc.get("name") == slot_data:
                            return loc
        
        return None

    def _publish_next_in_batch(self):
        if not hasattr(self, 'batch_queue') or not self.batch_queue:
            self.btn_batch_publish.setEnabled(True)
            self.status_callback("一键发布完成")
            return
            
        item = self.batch_queue.pop(0)
        self.status_callback(f"正在一键发布: {item.get('name')} ... ({len(self.batch_queue)} 剩余)")
        
        params = self._build_publish_params(item)
        
        worker = PublishSigninWorker(self.crawler, params)
        self.workers.append(worker)
        
        def on_finished(success, message, task_name, active_id=None):
            if success:
                self._mark_item_published(task_name, active_id)
                # Small delay to avoid triggering server rate limits
                QTimer.singleShot(1000, self._publish_next_in_batch)
            else:
                QMessageBox.warning(self, "发布中断", f"发布 {task_name} 时出错: {message}\n后续任务量已停止。")
                self.btn_batch_publish.setEnabled(True)
                self.batch_queue = [] # Clear queue on error
            
            if worker in self.workers:
                self.workers.remove(worker)

        worker.signin_published.connect(on_finished)
        worker.start()

    def _handle_publish_action(self, item_name):
        plans = self._load_signin_plans()
        key = self._get_current_key()
        target_item = None
        
        if key and key in plans:
            data = plans[key]
            items = data.get("items", []) if isinstance(data, dict) else data
            for item in items:
                if item['name'] == item_name:
                    target_item = item
                    break
        
        if not target_item:
            self.status_callback(f"错误: 未找到任务 {item_name} 的配置信息")
            return

        # 检查位置签到配置
        if hasattr(self, 'chk_enable_location') and self.chk_enable_location.isChecked():
            selected_data = self.combo_location.currentData()
            
            # 判断是否有有效位置
            has_location = False
            if selected_data is None:
                # "-- 手动选择位置 --" 或未选择
                has_location = False
            elif isinstance(selected_data, dict) and selected_data.get("template"):
                # 选择了"启用位置模板"，检查模板是否有配置
                location = self._get_location_from_template(item_name)
                has_location = location is not None
            else:
                # 选择了具体位置
                has_location = True
            
            if not has_location:
                QMessageBox.warning(self, "提示", "已启用位置签到，但未选择位置。\n\n请在下拉框中选择位置或启用位置模板。")
                return

        # Prepare parameters for the API (使用统一方法)
        params = self._build_publish_params(target_item)
        
        self.status_callback(f"正在发布签到: {item_name} ...")
        
        # Disable the button temporarily? 
        # For now just start the worker
        worker = PublishSigninWorker(self.crawler, params)
        self.workers.append(worker)
        worker.signin_published.connect(self._on_signin_published_finished)
        worker.signin_published.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def _on_signin_published_finished(self, success, message, task_name, active_id=None):
        if success:
             self.status_callback(f"发布成功: {task_name}")
             self._mark_item_published(task_name, active_id)
        else:
             QMessageBox.warning(self, "发布失败", message)
             self.status_callback(f"发布失败: {task_name}")

    def _mark_item_published(self, item_name, active_id=None):
        plans = self._load_signin_plans()
        key = self._get_current_key()
        if key and key in plans:
            data = plans[key]
            items = data.get("items", []) if isinstance(data, dict) else data
            for item in items:
                if item['name'] == item_name:
                    item['published'] = True
                    if active_id:
                        item['activeId'] = active_id
                    break
            self._save_signin_plans(plans)
            
            for item in getattr(self, "current_session_items", []):
                if item['name'] == item_name:
                    item['published'] = True
                    if active_id:
                        item['activeId'] = active_id
                    break
            
            self._display_signin_items(self.current_session_items)

    def _handle_delete_action(self, item_name, is_published, active_id):
        msg = f"确定要删除签到任务 {item_name} 吗？"
        if is_published:
            msg += "\n此任务已发布，删除将同步从服务器移除。"
        else:
            msg += "\n此任务未发布，仅从本地列表中已移除。"
            
        reply = QMessageBox.question(self, "确认删除", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback(f"正在删除 {item_name} ...")
            worker = DeleteSigninWorker(self.crawler, item_name, active_id)
            self.workers.append(worker)
            worker.signin_deleted.connect(self._on_signin_deleted_finished)
            # Remove the lambda to ensure _on_signin_deleted_finished is definitely called first
            worker.start()

    def _on_signin_deleted_finished(self, success, message, task_name):
        print(f"DEBUG: _on_signin_deleted_finished called: success={success}, task={task_name}", flush=True)
        
        # Clean up worker
        sender = self.sender()
        if sender in self.workers:
            self.workers.remove(sender)
            
        if success:
            self.status_callback(f"删除成功: {task_name}")
            self._remove_item_locally(task_name)
        else:
            QMessageBox.warning(self, "删除失败", message)
            self.status_callback(f"删除失败: {task_name}")

    def _remove_item_locally(self, item_name):
        print(f"DEBUG: Entering _remove_item_locally for {item_name}", flush=True)
        plans = self._load_signin_plans()
        key = self._get_current_key()
        print(f"DEBUG: Current key: {key}", flush=True)
        
        if key and key in plans:
            data = plans[key]
            # items might be the direct value or under 'items' key
            if isinstance(data, dict):
                items = data.get("items", [])
            else:
                items = data
            
            print(f"DEBUG: Found {len(items)} items in plan {key}", flush=True)
            
            # Use name comparison
            original_count = len(items)
            new_items = [it for it in items if str(it.get('name')).strip() != str(item_name).strip()]
            
            print(f"DEBUG: Remaining count: {len(new_items)}", flush=True)
            
            if len(new_items) == original_count:
                print(f"DEBUG: WARNING - Item '{item_name}' was NOT found in items list.", flush=True)
                # Let's print the names we have to debug mismatch
                names = [it.get('name') for it in items]
                print(f"DEBUG: Names in list: {names}", flush=True)
            
            # Update plans dictionary
            if isinstance(plans[key], dict):
                plans[key]['items'] = new_items
            else:
                plans[key] = new_items
                
            print(f"DEBUG: Saving to file: {SIGNIN_DATA_FILE}", flush=True)
            self._save_signin_plans(plans)
            
            # Update current session UI list
            self.current_session_items = new_items
            self._display_signin_items(self.current_session_items)
            print(f"DEBUG: Local removal complete for {item_name}", flush=True)
        else:
            print(f"DEBUG: Key {key} not found in plans or key is None.", flush=True)
            if key:
                print(f"DEBUG: Available keys: {list(plans.keys())}", flush=True)

    def on_questionnaire_clicked(self):
        self.last_activity_sub = "questionnaire"
        self.clear_activities_list()
        self.status_callback("正在加载问卷活动...")

    def on_practice_clicked(self):
        self.last_activity_sub = "practice"
        self.clear_activities_list()
        self.status_callback("正在加载随堂练习...")

    def on_group_manage_clicked(self):
        self.last_activity_sub = "group_manage"
        course = self.get_course_callback()
        if not course:
            QMessageBox.warning(self, "错误", "请先选择课程")
            return
            
        self.clear_activities_list()
        
        loading_label = QLabel("正在同步分组数据，请稍候...")
        loading_label.setStyleSheet("color: #007acc; padding: 20px;")
        self.activities_scroll_layout.addWidget(loading_label)
        
        worker = GroupWorker(self.crawler, course.id, self.get_class_id_callback())
        self.workers.append(worker)
        worker.groups_ready.connect(self._display_group_results)
        worker.groups_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        
        self.status_callback(f"同步分组列表: {course.name}")

    def _display_group_results(self, result):
        self.clear_activities_list()
        
        # Header with Add button
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 5)
        
        count_lbl = QLabel(f"<b>分组列表</b> ({len(result) if isinstance(result, list) else 0})")
        count_lbl.setStyleSheet("color: #ffffff; font-size: 14px;")
        header_layout.addWidget(count_lbl)
        header_layout.addStretch()
        
        add_btn = QPushButton("➕ 新增分组")
        add_btn.setFixedWidth(100)
        add_btn.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; border-radius: 4px; padding: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #1a8ad4; }
        """)
        add_btn.clicked.connect(self._handle_add_group)
        header_layout.addWidget(add_btn)
        
        self.activities_scroll_layout.addWidget(header_widget)
        
        if isinstance(result, str):
            error_label = QLabel(result)
            error_label.setStyleSheet("color: #ff4d4d; padding: 20px;")
            self.activities_scroll_layout.addWidget(error_label)
            return

        if not result:
            empty_label = QLabel("💡 该课程下暂无分组信息")
            empty_label.setStyleSheet("color: #aaaaaa; padding: 25px; font-size: 14px; text-align: center;")
            self.activities_scroll_layout.addWidget(empty_label)
            return

        for group in result:
            group_id = group.get('id')
            group_name = group.get('name', '未命名分组')
            
            card = QFrame()
            card.setObjectName("group_card")
            card.setStyleSheet("""
                QFrame#group_card { 
                    background-color: #1e1e1e; 
                    border: 1px solid #333333; 
                    border-radius: 8px; 
                    padding: 12px; 
                    margin-bottom: 5px; 
                }
                QFrame#group_card:hover { border: 1px solid #007acc; }
            """)
            card_layout = QHBoxLayout(card)
            
            info_layout = QVBoxLayout()
            name_lbl = QLabel(f"👥 {group_name}")
            name_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
            
            create_ts = group.get('createtime')
            time_str = datetime.fromtimestamp(create_ts / 1000).strftime('%Y-%m-%d %H:%M') if create_ts else "未知时间"
            teacher = group.get('teacherName', '未知')
            desc_lbl = QLabel(f"创建者: {teacher}  |  时间: {time_str}")
            desc_lbl.setStyleSheet("font-size: 12px; color: #aaaaaa;")
            
            info_layout.addWidget(name_lbl)
            info_layout.addWidget(desc_lbl)
            card_layout.addLayout(info_layout)
            card_layout.addStretch()
            
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(8)
            
            edit_btn = QPushButton("✏️ 重命名")
            edit_btn.setFixedWidth(75)
            edit_btn.setStyleSheet("""
                QPushButton { background-color: #3e3e42; color: #d4d4d4; border-radius: 4px; padding: 4px; font-size: 12px; }
                QPushButton:hover { background-color: #4e4e52; color: white; }
            """)
            edit_btn.clicked.connect(lambda checked, g=group: self._handle_rename_group(g))
            
            del_btn = QPushButton("🗑️ 删除")
            del_btn.setFixedWidth(70)
            del_btn.setStyleSheet("""
                QPushButton { background-color: #442222; color: #ff8888; border-radius: 4px; padding: 4px; font-size: 12px; }
                QPushButton:hover { background-color: #662222; color: #ffaaaa; }
            """)
            del_btn.clicked.connect(lambda checked, gid=group_id: self._handle_delete_group(gid))
            
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(del_btn)
            card_layout.addWidget(btn_container)
            
            self.activities_scroll_layout.addWidget(card)
            
        self.status_callback(f"同步完成 (共 {len(result)} 个分组)")

    def _handle_add_group(self):
        key = self._get_current_key()
        if not key:
            QMessageBox.warning(self, "错误", "未能确定当前班级信息")
            return
        
        cid, clazz = key.split('_')
        name, ok = QInputDialog.getText(self, "新增分组", "请输入分组名称:")
        if ok and name:
            self.status_callback(f"正在创建分组: {name}...")
            worker = AddGroupWorker(self.crawler, cid, clazz, name)
            self.workers.append(worker)
            worker.group_added.connect(self._on_group_added_finished)
            worker.group_added.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_group_added_finished(self, success, message):
        if success:
            self.status_callback(message)
            self.on_group_manage_clicked()
        else:
            QMessageBox.warning(self, "创建失败", message)
            self.status_callback("操作失败")

    def _handle_rename_group(self, group):
        old_name = group.get('name', '')
        group_id = group.get('id')
        
        new_name, ok = QInputDialog.getText(self, "重命名分组", "请输入新的分组名称:", text=old_name)
        
        if ok and new_name and new_name != old_name:
            self.status_callback(f"正在重命名: {old_name} -> {new_name}...")
            worker = RenameWorker(self.crawler, group_id, new_name)
            self.workers.append(worker)
            worker.rename_finished.connect(self._on_group_rename_finished)
            worker.rename_finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_group_rename_finished(self, success, message):
        if success:
            self.status_callback(message)
            self.on_group_manage_clicked()
        else:
            QMessageBox.warning(self, "重命名失败", message)
            self.status_callback("操作失败")

    def _handle_delete_group(self, group_id):
        reply = QMessageBox.question(self, '确认删除', f"确定要彻底删除该分组吗？此操作不可恢复。",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                   QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback(f"正在删除分组 (ID: {group_id})...")
            worker = DeleteGroupWorker(self.crawler, str(group_id))
            self.workers.append(worker)
            worker.group_deleted.connect(self._on_group_deleted_finished)
            worker.group_deleted.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_group_deleted_finished(self, success, message):
        if success:
            self.status_callback(message)
            self.on_group_manage_clicked()
        else:
            QMessageBox.warning(self, "删除失败", message)
            self.status_callback("操作失败")

    def restore_sub_feature(self, sub_type):
        mapping = {
            "signin": self.on_signin_clicked,
            "questionnaire": self.on_questionnaire_clicked,
            "practice": self.on_practice_clicked,
            "group_manage": self.on_group_manage_clicked
        }
        if sub_type in mapping:
            mapping[sub_type]()

    def _on_location_enable_changed(self, state):
        """启用/禁用位置签到时的处理"""
        self._update_location_ui_state()
    
    def _on_location_combo_changed(self, index):
        """位置下拉框选择变化时的处理"""
        self._update_location_ui_state()
    
    def _update_location_ui_state(self):
        """更新位置配置UI的启用状态"""
        enabled = self.chk_enable_location.isChecked()
        
        # 启用/禁用位置下拉框
        self.combo_location.setEnabled(enabled)
        
        # 未启用时，显示提示文字
        if not enabled:
            self.combo_location.blockSignals(True)
            current_index = self.combo_location.currentIndex()
            self.combo_location.setItemText(0, "未启用位置签到")
            self.combo_location.setCurrentIndex(0)
            self.combo_location.blockSignals(False)
        else:
            # 启用时，恢复正常文字
            self.combo_location.blockSignals(True)
            self.combo_location.setItemText(0, "-- 手动选择位置 --")
            self.combo_location.blockSignals(False)
        
        # 根据下拉框选择决定是否启用"位置模板"按钮
        # 只有选择"启用位置模板"时才启用按钮
        if enabled:
            current_text = self.combo_location.currentText()
            is_template_mode = "启用位置模板" in current_text
            self.btn_config_location.setEnabled(is_template_mode)
        else:
            self.btn_config_location.setEnabled(False)
    
    def _on_config_location_clicked(self):
        """点击配置按钮时打开位置配置对话框"""
        from ui.dialogs.location_dialog import LocationConfigDialog
        
        # 传入主界面的课次配置
        weekly_count = 2  # 每周重复模式默认值
        odd_count = self.odd_times.value()  # 单周次数
        even_count = self.even_times.value()  # 双周次数
        
        dialog = LocationConfigDialog(self, weekly_count, odd_count, even_count)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 重新加载位置数据到下拉框，并选中"启用位置模板"
            self._load_locations_to_combo(select_template=True)
    
    def _load_locations_to_combo(self, select_template=False):
        """加载位置数据到下拉框
        
        Args:
            select_template: 是否选中"启用位置模板"选项
        """
        self.combo_location.clear()
        
        # 加载用户自定义位置
        user_locations = []
        template_configured = False
        try:
            if os.path.exists(LOCATION_DATA_FILE):
                with open(LOCATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    user_locations = data.get("customLocations", [])
                    # 检查位置模板是否已配置（有课次配置）
                    template = data.get("locationTemplate", {})
                    slots = template.get("weeklySlots", []) or template.get("oddSlots", []) or template.get("evenSlots", [])
                    template_configured = len(slots) > 0 and any(s is not None for s in slots)
        except Exception as e:
            print(f"加载位置数据失败: {e}")
        
        # 合并内置位置和用户自定义位置
        built_in_locations = copy.deepcopy(DEFAULT_COMMON_LOCATIONS)
        built_in_names = {loc.get("name") for loc in built_in_locations}
        
        # 合并：内置位置 + 用户自定义位置（排除与内置位置同名的）
        locations = built_in_locations + [
            loc for loc in user_locations 
            if loc.get("name") not in built_in_names
        ]
        
        if locations:
            self.combo_location.clear()
            
            # 第一项：手动选择位置（默认）
            self.combo_location.addItem("-- 手动选择位置 --", None)
            
            # 第二项：启用位置模板
            template_text = "📋 启用位置模板" if template_configured else "📋 启用位置模板（未配置）"
            self.combo_location.addItem(template_text, {"template": True})
            
            # 具体位置选项
            for loc in locations:
                name = loc.get("name", "")
                self.combo_location.addItem(f"📍 {name}", loc)
            
            # 根据参数决定选中哪一项
            if select_template and template_configured:
                self.combo_location.setCurrentIndex(1)  # 选中"启用位置模板"
            else:
                self.combo_location.setCurrentIndex(0)  # 默认选中第一项
            
            # 更新按钮状态
            self._update_location_ui_state()

    def on_show(self):
        self.clear_activities_list()

"""位置管理对话框"""
import json
import os
import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QLineEdit, QSpinBox,
    QGroupBox, QTabWidget, QWidget, QMessageBox, QListWidget,
    QListWidgetItem, QRadioButton, QButtonGroup, QStackedWidget
)
from PyQt6.QtCore import Qt
from core.config import LOCATION_DATA_FILE, DEFAULT_COMMON_LOCATIONS, DEFAULT_LOCATION_TEMPLATE


class LocationConfigDialog(QDialog):
    """位置配置对话框"""
    
    def __init__(self, parent=None, weekly_count=2, odd_count=2, even_count=2):
        super().__init__(parent)
        self.setWindowTitle("📍 位置配置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        # 从主界面传入的课次配置
        self.main_weekly_count = weekly_count
        self.main_odd_count = odd_count
        self.main_even_count = even_count
        
        # 加载位置数据
        self.location_data = self._load_location_data()
        
        # 存储课次配置的引用
        self.odd_slots_widgets = []  # 单周课次下拉框
        self.even_slots_widgets = []  # 双周课次下拉框
        self.weekly_slots_widgets = []  # 每周重复模式的课次下拉框
        self.odd_slots_container = None
        self.even_slots_container = None
        self.weekly_slots_container = None
        self.odd_slots_layout = None
        self.even_slots_layout = None
        self.weekly_slots_layout = None
        
        self.setup_ui()
        self.load_data_to_ui()
    
    def _load_location_data(self):
        """加载位置数据"""
        user_data = {}
        if os.path.exists(LOCATION_DATA_FILE):
            try:
                with open(LOCATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
            except:
                pass
        
        # 合并内置位置和用户自定义位置
        # 内置位置始终使用最新配置（如 range 从 300 改为 500）
        built_in_locations = copy.deepcopy(DEFAULT_COMMON_LOCATIONS)
        user_locations = user_data.get("customLocations", [])  # 用户自定义位置
        hidden_built_in = user_data.get("hiddenBuiltInLocations", [])  # 被隐藏的内置位置
        
        # 获取内置位置名称列表，用于去重
        built_in_names = {loc.get("name") for loc in built_in_locations}
        
        # 过滤掉被隐藏的内置位置
        visible_built_in = [
            loc for loc in built_in_locations
            if loc.get("name") not in hidden_built_in
        ]
        
        # 合并：可见的内置位置 + 用户自定义位置（排除与内置位置同名的）
        all_locations = visible_built_in + [
            loc for loc in user_locations 
            if loc.get("name") not in built_in_names
        ]
        
        return {
            "commonLocations": all_locations,  # 用于界面显示
            "customLocations": user_locations,  # 用户自定义位置（保存时使用）
            "locationTemplate": user_data.get("locationTemplate", copy.deepcopy(DEFAULT_LOCATION_TEMPLATE)),
            "hiddenBuiltInLocations": user_data.get("hiddenBuiltInLocations", [])  # 被隐藏的内置位置
        }
    
    def _save_location_data(self):
        """保存位置数据"""
        try:
            os.makedirs(os.path.dirname(LOCATION_DATA_FILE), exist_ok=True)
            
            # 只保存用户自定义位置、被隐藏的内置位置和位置模板
            save_data = {
                "customLocations": self.location_data.get("customLocations", []),
                "locationTemplate": self.location_data.get("locationTemplate", {}),
                "hiddenBuiltInLocations": self.location_data.get("hiddenBuiltInLocations", [])
            }
            
            with open(LOCATION_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"保存位置数据失败: {e}")
            return False
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #1e1e1e;
            }
            QTabBar::tab {
                background: #2d2d2d;
                color: #ffffff;
                padding: 8px 20px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #007acc;
            }
        """)
        
        # Tab 1: 位置模板配置
        tab_template = self._create_template_tab()
        self.tab_widget.addTab(tab_template, "位置模板")
        
        # Tab 2: 常用位置管理
        tab_common = self._create_common_locations_tab()
        self.tab_widget.addTab(tab_common, "常用位置")
        
        # 监听Tab切换，切换到常用位置Tab时取消选中
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        layout.addWidget(self.tab_widget)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_save = QPushButton("💾 保存")
        btn_save.setFixedWidth(100)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1a8ad4;
            }
        """)
        btn_save.clicked.connect(self._on_save)
        
        btn_cancel = QPushButton("❌ 取消")
        btn_cancel.setFixedWidth(100)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        button_layout.addWidget(btn_save)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def _create_template_tab(self):
        """创建位置模板配置Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # 模式选择
        mode_group = QGroupBox("位置模式")
        mode_group.setStyleSheet("""
            QGroupBox {
                color: #007acc;
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        mode_layout = QVBoxLayout(mode_group)
        
        self.radio_weekly = QRadioButton("每周重复")
        self.radio_weekly.setStyleSheet("color: white;")
        self.radio_weekly.setChecked(True)
        
        self.radio_biweekly = QRadioButton("单双周不同")
        self.radio_biweekly.setStyleSheet("color: white;")
        
        self.mode_button_group = QButtonGroup()
        self.mode_button_group.addButton(self.radio_weekly)
        self.mode_button_group.addButton(self.radio_biweekly)
        
        mode_layout.addWidget(self.radio_weekly)
        mode_layout.addWidget(self.radio_biweekly)
        
        layout.addWidget(mode_group)
        
        # 监听模式切换
        self.radio_weekly.toggled.connect(self._on_mode_changed)
        
        # 使用 QStackedWidget 保持高度固定
        self.config_stack = QStackedWidget()
        
        # Page 1: 每周重复模式的配置区域
        self.weekly_config_widget = self._create_weekly_config_widget()
        self.config_stack.addWidget(self.weekly_config_widget)
        
        # Page 2: 单双周Tab
        self.weekly_tab = QTabWidget()
        self.weekly_tab.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                background: #1e1e1e;
            }
            QTabBar::tab {
                background: #2d2d2d;
                color: #ffffff;
                padding: 6px 15px;
            }
            QTabBar::tab:selected {
                background: #4ec9b0;
            }
        """)
        
        # 单周Tab
        self.odd_week_widget = self._create_week_slots_widget("odd")
        self.weekly_tab.addTab(self.odd_week_widget, "单周")
        
        # 双周Tab
        self.even_week_widget = self._create_week_slots_widget("even")
        self.weekly_tab.addTab(self.even_week_widget, "双周")
        
        self.config_stack.addWidget(self.weekly_tab)
        
        layout.addWidget(self.config_stack)
        
        return widget
    
    def _create_weekly_config_widget(self):
        """创建每周重复模式的配置Widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 课次数量选择（从主界面获取，禁用调整）
        count_layout = QHBoxLayout()
        count_label = QLabel(f"每周课次数:")
        count_label.setStyleSheet("color: white;")
        count_layout.addWidget(count_label)
        
        self.weekly_slot_count = QSpinBox()
        self.weekly_slot_count.setRange(1, 10)
        self.weekly_slot_count.setValue(self.main_weekly_count)
        self.weekly_slot_count.setEnabled(False)  # 禁用调整，使用主界面设置
        self.weekly_slot_count.setStyleSheet("""
            QSpinBox {
                background: #1a1a1a;
                color: #888888;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 3px;
            }
        """)
        count_layout.addWidget(self.weekly_slot_count)
        count_layout.addStretch()
        
        layout.addLayout(count_layout)
        
        # 课次位置列表
        slots_group = QGroupBox("课次位置配置")
        slots_group.setStyleSheet("""
            QGroupBox {
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        slots_layout = QVBoxLayout(slots_group)
        
        # 创建课次配置区域
        slots_container = QWidget()
        slots_container_layout = QVBoxLayout(slots_container)
        slots_container_layout.setSpacing(10)
        slots_layout.addWidget(slots_container)
        
        self.weekly_slots_container = slots_container
        self.weekly_slots_layout = slots_container_layout
        
        layout.addWidget(slots_group)
        
        # 连接信号 - 当课次数量改变时更新界面
        self.weekly_slot_count.valueChanged.connect(lambda count: self._update_slot_widgets("weekly", count))
        
        return widget
    
    def _on_mode_changed(self):
        """模式切换时更新界面"""
        is_weekly = self.radio_weekly.isChecked()
        
        # 使用 QStackedWidget 切换页面（保持高度固定）
        if is_weekly:
            self.config_stack.setCurrentIndex(0)  # 显示每周重复配置
        else:
            self.config_stack.setCurrentIndex(1)  # 显示单双周配置
    
    def _create_week_slots_widget(self, week_type):
        """创建每周课次位置配置Widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 课次数量选择（从主界面获取，禁用调整）
        count_layout = QHBoxLayout()
        count_label = QLabel(f"每周课次数:")
        count_label.setStyleSheet("color: white;")
        count_layout.addWidget(count_label)
        
        spin_count = QSpinBox()
        spin_count.setRange(1, 10)
        # 使用主界面传入的单周或双周次数
        spin_count.setValue(self.main_odd_count if week_type == "odd" else self.main_even_count)
        spin_count.setEnabled(False)  # 禁用调整，使用主界面设置
        spin_count.setStyleSheet("""
            QSpinBox {
                background: #1a1a1a;
                color: #888888;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 3px;
            }
        """)
        count_layout.addWidget(spin_count)
        count_layout.addStretch()
        
        layout.addLayout(count_layout)
        
        # 课次位置列表
        slots_group = QGroupBox("课次位置配置")
        slots_group.setStyleSheet("""
            QGroupBox {
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        slots_layout = QVBoxLayout(slots_group)
        
        # 存储spinbox引用
        if week_type == "odd":
            self.odd_slot_count = spin_count
        else:
            self.even_slot_count = spin_count
        
        # 创建课次配置区域
        slots_container = QWidget()
        slots_container_layout = QVBoxLayout(slots_container)
        slots_container_layout.setSpacing(10)
        slots_layout.addWidget(slots_container)
        
        # 存储容器引用
        if week_type == "odd":
            self.odd_slots_container = slots_container
            self.odd_slots_layout = slots_container_layout
        else:
            self.even_slots_container = slots_container
            self.even_slots_layout = slots_container_layout
        
        layout.addWidget(slots_group)
        
        # 连接信号 - 当课次数量改变时更新界面
        spin_count.valueChanged.connect(lambda count: self._update_slot_widgets(week_type, count))
        
        return widget
    
    def _get_common_locations(self):
        """获取常用位置列表"""
        # 从当前的 location_list 获取（如果在常用位置tab已编辑）
        locations = []
        for i in range(self.location_list.count()):
            item = self.location_list.item(i)
            loc_data = item.data(Qt.ItemDataRole.UserRole)
            locations.append(loc_data)
        
        # 如果常用位置tab还没数据，从加载的数据获取
        if not locations:
            locations = self.location_data.get("commonLocations", [])
        
        return locations
    
    def _update_slot_widgets(self, week_type, count):
        """根据课次数量动态创建位置下拉框"""
        # 确定使用哪个容器和列表
        if week_type == "odd":
            container = self.odd_slots_container
            container_layout = self.odd_slots_layout
            widgets_list = self.odd_slots_widgets
        elif week_type == "even":
            container = self.even_slots_container
            container_layout = self.even_slots_layout
            widgets_list = self.even_slots_widgets
        else:  # weekly
            container = self.weekly_slots_container
            container_layout = self.weekly_slots_layout
            widgets_list = self.weekly_slots_widgets
        
        # 清空现有的课次配置行
        while container_layout.count():
            item = container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        widgets_list.clear()
        
        # 获取常用位置
        common_locations = self._get_common_locations()
        
        # 创建新的课次配置行
        for i in range(count):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            # 课次标签
            label = QLabel(f"第{i+1}次课:")
            label.setStyleSheet("color: white;")
            label.setFixedWidth(70)
            row_layout.addWidget(label)
            
            # 位置下拉框
            combo = QComboBox()
            combo.setStyleSheet("""
                QComboBox {
                    background: #252526;
                    color: white;
                    border: 1px solid #444;
                    border-radius: 3px;
                    padding: 5px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    background: #252526;
                    color: white;
                    selection-background-color: #007acc;
                }
            """)
            
            # 添加"不限制"选项
            combo.addItem("不限制位置", None)
            
            # 添加常用位置
            for loc in common_locations:
                combo.addItem(loc.get("name", ""), loc)
            
            row_layout.addWidget(combo)
            
            container_layout.addWidget(row_widget)
            widgets_list.append(combo)
    
    def _create_common_locations_tab(self):
        """创建常用位置管理Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 位置列表
        list_label = QLabel("常用位置列表:")
        list_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(list_label)
        
        self.location_list = QListWidget()
        self.location_list.setStyleSheet("""
            QListWidget {
                background: #252526;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QListWidget::item {
                color: white;
                padding: 8px;
            }
            QListWidget::item:selected {
                background: #007acc;
            }
        """)
        layout.addWidget(self.location_list)
        
        # 编辑区域
        edit_group = QGroupBox("位置信息")
        edit_group.setStyleSheet("""
            QGroupBox {
                color: #007acc;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
        """)
        edit_layout = QGridLayout(edit_group)
        
        # 名称
        edit_layout.addWidget(QLabel("名称:"), 0, 0)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("如: 教学楼A-101")
        self.edit_name.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 3px; padding: 5px;")
        edit_layout.addWidget(self.edit_name, 0, 1, 1, 3)
        
        # 经纬度
        edit_layout.addWidget(QLabel("纬度:"), 1, 0)
        self.edit_lat = QLineEdit()
        self.edit_lat.setPlaceholderText("34.4034")
        self.edit_lat.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 3px; padding: 5px;")
        edit_layout.addWidget(self.edit_lat, 1, 1)
        
        edit_layout.addWidget(QLabel("经度:"), 1, 2)
        self.edit_lng = QLineEdit()
        self.edit_lng.setPlaceholderText("113.7713")
        self.edit_lng.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 3px; padding: 5px;")
        edit_layout.addWidget(self.edit_lng, 1, 3)
        
        # 范围
        edit_layout.addWidget(QLabel("范围(米):"), 2, 0)
        self.edit_range = QSpinBox()
        self.edit_range.setRange(10, 5000)
        self.edit_range.setValue(300)
        self.edit_range.setStyleSheet("background: #252526; color: white; border: 1px solid #444; border-radius: 3px; padding: 3px;")
        edit_layout.addWidget(self.edit_range, 2, 1)
        
        # 导入导出按钮（放在范围后面）
        btn_import = QPushButton("📥 导入")
        btn_import.setStyleSheet("""
            QPushButton {
                background: #4a4a4a;
                color: white;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #5a5a5a;
            }
        """)
        btn_import.clicked.connect(self._on_import)
        edit_layout.addWidget(btn_import, 2, 2)
        
        btn_export = QPushButton("📤 导出")
        btn_export.setStyleSheet("""
            QPushButton {
                background: #4a4a4a;
                color: white;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #5a5a5a;
            }
        """)
        btn_export.clicked.connect(self._on_export)
        edit_layout.addWidget(btn_export, 2, 3)
        
        layout.addWidget(edit_group)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("➕ 新增")
        btn_add.setStyleSheet("background: #007acc; color: white; border-radius: 4px; padding: 6px;")
        btn_add.clicked.connect(self._on_add_location)
        
        btn_update = QPushButton("✏️ 更新")
        btn_update.setStyleSheet("background: #4ec9b0; color: white; border-radius: 4px; padding: 6px;")
        btn_update.clicked.connect(self._on_update_location)
        
        btn_delete = QPushButton("🗑️ 删除")
        btn_delete.setStyleSheet("background: #d13438; color: white; border-radius: 4px; padding: 6px;")
        btn_delete.clicked.connect(self._on_delete_location)
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_update)
        btn_layout.addWidget(btn_delete)
        
        layout.addLayout(btn_layout)
        
        # 连接信号
        self.location_list.currentRowChanged.connect(self._on_location_selected)
        
        return widget
    
    def _on_tab_changed(self, index):
        """Tab切换时处理"""
        # 切换到常用位置Tab时，取消选中并清空编辑框
        if index == 1:  # 常用位置Tab的索引
            self.location_list.blockSignals(True)
            self.location_list.setCurrentRow(-1)
            self.location_list.blockSignals(False)
            
            # 清空编辑框
            self.edit_name.clear()
            self.edit_lat.clear()
            self.edit_lng.clear()
            self.edit_range.setValue(300)
    
    def load_data_to_ui(self):
        """加载数据到UI"""
        # 暂时断开信号，避免添加item时自动触发选中
        self.location_list.blockSignals(True)
        
        # 加载常用位置
        for loc in self.location_data.get("commonLocations", []):
            item = QListWidgetItem(loc.get("name", ""))
            item.setData(Qt.ItemDataRole.UserRole, loc)
            self.location_list.addItem(item)
        
        # 不默认选中任何位置
        self.location_list.setCurrentRow(-1)
        
        # 恢复信号
        self.location_list.blockSignals(False)
        
        # 清空编辑框
        self.edit_name.clear()
        self.edit_lat.clear()
        self.edit_lng.clear()
        self.edit_range.setValue(300)
        
        # 加载模板配置
        template = self.location_data.get("locationTemplate", {})
        mode = template.get("mode", "weekly")
        
        if mode == "biweekly":
            self.radio_biweekly.setChecked(True)
        else:
            self.radio_weekly.setChecked(True)
        
        # 加载课次数量和位置配置
        # 使用主界面传入的课次数，而不是从模板中读取
        weekly_count = self.main_weekly_count
        odd_count = self.main_odd_count
        even_count = self.main_even_count
        
        weekly_slots = template.get("weeklySlots", [])
        odd_slots = template.get("oddSlots", [])
        even_slots = template.get("evenSlots", [])
        
        # 暂时阻塞信号，避免在设置值时触发 _update_slot_widgets
        self.weekly_slot_count.blockSignals(True)
        self.odd_slot_count.blockSignals(True)
        self.even_slot_count.blockSignals(True)
        
        self.weekly_slot_count.setValue(weekly_count)
        self.odd_slot_count.setValue(odd_count)
        self.even_slot_count.setValue(even_count)
        
        self.weekly_slot_count.blockSignals(False)
        self.odd_slot_count.blockSignals(False)
        self.even_slot_count.blockSignals(False)
        
        # 手动触发一次更新，确保下拉框被创建
        self._update_slot_widgets("weekly", weekly_count)
        self._update_slot_widgets("odd", odd_count)
        self._update_slot_widgets("even", even_count)
        
        # 恢复已选择的位置
        # 需要等待下拉框创建完成后再设置
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._restore_slot_selections("weekly", weekly_slots))
        QTimer.singleShot(100, lambda: self._restore_slot_selections("odd", odd_slots))
        QTimer.singleShot(100, lambda: self._restore_slot_selections("even", even_slots))
        
        # 根据模式显示对应的界面
        self._on_mode_changed()
    
    def _restore_slot_selections(self, week_type, slots_data):
        """恢复课次位置选择"""
        if week_type == "odd":
            widgets = self.odd_slots_widgets
        elif week_type == "even":
            widgets = self.even_slots_widgets
        else:  # weekly
            widgets = self.weekly_slots_widgets
        
        for i, combo in enumerate(widgets):
            if i < len(slots_data):
                slot_data = slots_data[i]
                # slot_data 可能是 None、位置名称或完整位置对象
                if slot_data is None:
                    combo.setCurrentIndex(0)  # "不限制位置"
                elif isinstance(slot_data, str):
                    # 是位置名称，查找匹配项
                    for j in range(combo.count()):
                        if combo.itemText(j) == slot_data:
                            combo.setCurrentIndex(j)
                            break
                elif isinstance(slot_data, dict):
                    # 是完整位置对象，查找匹配项
                    for j in range(combo.count()):
                        item_data = combo.itemData(j)
                        if item_data and item_data.get("name") == slot_data.get("name"):
                            combo.setCurrentIndex(j)
                            break
    
    def _on_location_selected(self, row):
        """选择位置项时填充编辑框"""
        if row < 0:
            return
        
        item = self.location_list.item(row)
        loc_data = item.data(Qt.ItemDataRole.UserRole)
        
        self.edit_name.setText(loc_data.get("name", ""))
        self.edit_lat.setText(str(loc_data.get("latitude", "")))
        self.edit_lng.setText(str(loc_data.get("longitude", "")))
        self.edit_range.setValue(loc_data.get("range", 300))
    
    def _on_add_location(self):
        """新增位置"""
        name = self.edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入位置名称")
            return
        
        try:
            lat = float(self.edit_lat.text())
            lng = float(self.edit_lng.text())
        except:
            QMessageBox.warning(self, "错误", "经纬度必须是数字")
            return
        
        loc_data = {
            "name": name,
            "latitude": lat,
            "longitude": lng,
            "range": self.edit_range.value()
        }
        
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, loc_data)
        self.location_list.addItem(item)
        
        # 清空编辑框
        self.edit_name.clear()
        self.edit_lat.clear()
        self.edit_lng.clear()
        self.edit_range.setValue(300)

        # 更新位置模板下拉框
        self._refresh_template_combos()
    
    def _on_update_location(self):
        """更新选中的位置"""
        row = self.location_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "错误", "请先选择要更新的位置")
            return
        
        name = self.edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入位置名称")
            return
        
        try:
            lat = float(self.edit_lat.text())
            lng = float(self.edit_lng.text())
        except:
            QMessageBox.warning(self, "错误", "经纬度必须是数字")
            return
        
        loc_data = {
            "name": name,
            "latitude": lat,
            "longitude": lng,
            "range": self.edit_range.value()
        }
        
        item = self.location_list.item(row)
        item.setText(name)
        item.setData(Qt.ItemDataRole.UserRole, loc_data)
        
        # 更新位置模板下拉框
        self._refresh_template_combos()
    
    def _on_delete_location(self):
        """删除选中的位置"""
        row = self.location_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "错误", "请先选择要删除的位置")
            return
        
        # 获取要删除的位置数据
        item = self.location_list.item(row)
        loc_data = item.data(Qt.ItemDataRole.UserRole)
        loc_name = loc_data.get("name", "")
        
        # 判断是否为内置位置
        built_in_names = {loc.get("name") for loc in DEFAULT_COMMON_LOCATIONS}
        is_built_in = loc_name in built_in_names
        
        if is_built_in:
            reply = QMessageBox.question(
                self, "确认删除",
                f"'{loc_name}' 是系统内置位置。\n\n删除后该位置将不再显示在列表中，但可以通过重置功能恢复。\n\n是否确定删除？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self, "确认删除",
                "确定要删除这个位置吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 如果是内置位置，添加到隐藏列表
            if is_built_in:
                hidden_list = self.location_data.get("hiddenBuiltInLocations", [])
                if loc_name not in hidden_list:
                    hidden_list.append(loc_name)
                    self.location_data["hiddenBuiltInLocations"] = hidden_list
            
            self.location_list.takeItem(row)
            # 更新位置模板下拉框
            self._refresh_template_combos()
    
    def _refresh_template_combos(self):
        """刷新位置模板的下拉框（当常用位置变化时）"""
        # 记录当前选择
        weekly_selections = []
        for combo in self.weekly_slots_widgets:
            weekly_selections.append(combo.currentData())
        
        odd_selections = []
        for combo in self.odd_slots_widgets:
            odd_selections.append(combo.currentData())
        
        even_selections = []
        for combo in self.even_slots_widgets:
            even_selections.append(combo.currentData())
        
        # 重新创建下拉框
        self._update_slot_widgets("weekly", self.weekly_slot_count.value())
        self._update_slot_widgets("odd", self.odd_slot_count.value())
        self._update_slot_widgets("even", self.even_slot_count.value())
        
        # 恢复选择
        for i, combo in enumerate(self.weekly_slots_widgets):
            if i < len(weekly_selections) and weekly_selections[i]:
                # 查找匹配项
                for j in range(combo.count()):
                    if combo.itemData(j) and combo.itemData(j).get("name") == weekly_selections[i].get("name"):
                        combo.setCurrentIndex(j)
                        break
        
        for i, combo in enumerate(self.odd_slots_widgets):
            if i < len(odd_selections) and odd_selections[i]:
                # 查找匹配项
                for j in range(combo.count()):
                    if combo.itemData(j) and combo.itemData(j).get("name") == odd_selections[i].get("name"):
                        combo.setCurrentIndex(j)
                        break
        
        for i, combo in enumerate(self.even_slots_widgets):
            if i < len(even_selections) and even_selections[i]:
                # 查找匹配项
                for j in range(combo.count()):
                    if combo.itemData(j) and combo.itemData(j).get("name") == even_selections[i].get("name"):
                        combo.setCurrentIndex(j)
                        break
    
    def _on_save(self):
        """保存配置"""
        # 保存常用位置（区分内置位置和用户自定义位置）
        built_in_names = {loc.get("name") for loc in DEFAULT_COMMON_LOCATIONS}
        custom_locations = []
        for i in range(self.location_list.count()):
            item = self.location_list.item(i)
            loc_data = item.data(Qt.ItemDataRole.UserRole)
            # 只保存用户自定义位置（不在内置列表中的）
            if loc_data.get("name") not in built_in_names:
                custom_locations.append(loc_data)
        
        self.location_data["customLocations"] = custom_locations
        
        # 保存模板配置
        template = self.location_data["locationTemplate"]
        mode = "biweekly" if self.radio_biweekly.isChecked() else "weekly"
        template["mode"] = mode
        template["weeklySlotCount"] = self.weekly_slot_count.value()
        template["oddSlotCount"] = self.odd_slot_count.value()
        template["evenSlotCount"] = self.even_slot_count.value()
        
        # 保存课次位置选择
        template["weeklySlots"] = []
        for combo in self.weekly_slots_widgets:
            loc_data = combo.currentData()
            template["weeklySlots"].append(loc_data)
        
        template["oddSlots"] = []
        for combo in self.odd_slots_widgets:
            loc_data = combo.currentData()
            template["oddSlots"].append(loc_data)
        
        template["evenSlots"] = []
        for combo in self.even_slots_widgets:
            loc_data = combo.currentData()
            template["evenSlots"].append(loc_data)
        
        # 检查是否有有效的课次配置，自动设置enabled标志
        all_slots = template.get("weeklySlots", []) + template.get("oddSlots", []) + template.get("evenSlots", [])
        has_valid_slot = any(slot is not None for slot in all_slots)
        template["enabled"] = has_valid_slot
        
        if self._save_location_data():
            QMessageBox.information(self, "成功", "位置配置已保存")
            self.accept()
        else:
            QMessageBox.warning(self, "错误", "保存失败")

    def _on_export(self):
        """导出用户自定义位置"""
        from PyQt6.QtWidgets import QFileDialog
        
        # 获取用户自定义位置
        custom_locations = self.location_data.get("customLocations", [])
        
        if not custom_locations:
            QMessageBox.information(self, "提示", "暂无用户自定义位置可导出")
            return
        
        # 选择保存路径
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出位置", "自定义位置.txt", "文本文件 (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for loc in custom_locations:
                    name = loc.get("name", "")
                    lat = loc.get("latitude", "")
                    lng = loc.get("longitude", "")
                    f.write(f"{name},{lat},{lng}\n")
            
            QMessageBox.information(self, "成功", f"已导出 {len(custom_locations)} 个位置")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导出失败: {e}")

    def _on_import(self):
        """导入位置"""
        from PyQt6.QtWidgets import QFileDialog
        
        # 选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入位置", "", "文本文件 (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            imported_count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split(',')
                    if len(parts) < 3:
                        continue
                    
                    name = parts[0].strip()
                    try:
                        lat = float(parts[1].strip())
                        lng = float(parts[2].strip())
                    except ValueError:
                        continue
                    
                    # 检查是否已存在
                    existing_names = {loc.get("name") for loc in self.location_data.get("customLocations", [])}
                    if name in existing_names:
                        continue
                    
                    # 添加新位置
                    loc_data = {
                        "name": name,
                        "latitude": lat,
                        "longitude": lng,
                        "range": 500
                    }
                    self.location_data["customLocations"].append(loc_data)
                    
                    # 添加到列表
                    item = QListWidgetItem(name)
                    item.setData(Qt.ItemDataRole.UserRole, loc_data)
                    self.location_list.addItem(item)
                    
                    imported_count += 1
            
            if imported_count > 0:
                # 刷新模板下拉框
                self._refresh_template_combos()
                QMessageBox.information(self, "成功", f"成功导入 {imported_count} 个位置")
            else:
                QMessageBox.information(self, "提示", "没有新的位置被导入")
        
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导入失败: {e}")


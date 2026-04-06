"""
多选下拉框组件 - 支持下拉面板内多选和折叠
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, 
    QLabel, QFrame, QScrollArea, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal


class MultiSelectCombo(QFrame):
    """多选下拉框组件"""
    
    selection_changed = pyqtSignal(list)  # 选中项变化信号
    
    def __init__(self, placeholder="请选择", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.items = {}  # {value: {"text": str, "count": int, "checked": bool, "is_parent": bool, "children": []}}
        self._is_open = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置界面"""
        self.setFixedHeight(35)
        self.setStyleSheet("""
            MultiSelectCombo {
                background-color: #1e1e1e;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
            MultiSelectCombo:hover {
                border: 1px solid #007acc;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 头部显示区域（点击展开下拉）
        self.header = QFrame()
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        
        self.display_label = QLabel(self.placeholder)
        self.display_label.setStyleSheet("color: #888888; font-size: 13px;")
        header_layout.addWidget(self.display_label)
        header_layout.addStretch()
        
        # 下拉箭头
        self.arrow_label = QLabel("▼")
        self.arrow_label.setStyleSheet("color: #888888; font-size: 10px;")
        header_layout.addWidget(self.arrow_label)
        
        main_layout.addWidget(self.header)
        
        # 下拉面板（默认隐藏）
        self.dropdown_panel = QFrame()
        self.dropdown_panel.setWindowFlags(Qt.WindowType.Popup)
        self.dropdown_panel.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
        """)
        
        # 处理下拉面板失去焦点事件
        self.dropdown_panel.installEventFilter(self)
        
        dropdown_layout = QVBoxLayout(self.dropdown_panel)
        dropdown_layout.setContentsMargins(0, 5, 0, 5)
        dropdown_layout.setSpacing(0)
        
        # 全选/全不选
        select_all_layout = QHBoxLayout()
        select_all_layout.setContentsMargins(10, 5, 10, 5)
        
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #005c99;
                text-decoration: underline;
            }
        """)
        self.select_all_btn.clicked.connect(self.select_all)
        select_all_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("全不选")
        self.select_none_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #cccccc;
                text-decoration: underline;
            }
        """)
        self.select_none_btn.clicked.connect(self.select_none)
        select_all_layout.addWidget(self.select_none_btn)
        select_all_layout.addStretch()
        
        dropdown_layout.addLayout(select_all_layout)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3e3e42; max-height: 1px;")
        dropdown_layout.addWidget(line)
        
        # 选项列表容器
        self.options_container = QWidget()
        self.options_layout = QVBoxLayout(self.options_container)
        self.options_layout.setContentsMargins(5, 5, 5, 5)
        self.options_layout.setSpacing(3)
        self.options_layout.addStretch()
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.options_container)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        scroll.setMaximumHeight(300)
        dropdown_layout.addWidget(scroll)
        
        # 为header添加点击事件
        self.header.mousePressEvent = lambda event: self.on_header_clicked(event)
        
    def add_group(self, text: str, indent: int = 0):
        """添加分组标题（不可选择）"""
        # 创建分组标题行
        group_widget = QFrame()
        group_widget.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        group_layout = QHBoxLayout(group_widget)
        group_layout.setContentsMargins(10 + indent * 15, 8, 10, 5)
        group_layout.setSpacing(0)
        
        # 分组标题文本
        label = QLabel(text)
        label.setStyleSheet("color: #007acc; font-size: 13px; font-weight: bold;")
        group_layout.addWidget(label)
        group_layout.addStretch()
        
        # 存储分组引用（使用特殊key避免与选项冲突）
        group_key = f"__group__{text}__"
        self.items[group_key] = {
            "text": text,
            "count": 0,
            "checked": False,
            "is_group": True,
            "widget": group_widget
        }
        
        # 插入到布局（在stretch之前）
        self.options_layout.insertWidget(self.options_layout.count() - 1, group_widget)
        
    def add_item(self, value: str, text: str, count: int = 0, checked: bool = True, indent: int = 0, is_parent: bool = False):
        """添加选项
        
        Args:
            value: 选项值
            text: 显示文本
            count: 题目数量
            checked: 是否选中
            indent: 缩进层级
            is_parent: 是否为父节点（可折叠）
        """
        # 创建选项行
        item_widget = QFrame()
        item_widget.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border-radius: 3px;
            }
            QFrame:hover {
                background-color: #2a2d2e;
            }
        """)
        item_widget.setCursor(Qt.CursorShape.PointingHandCursor if is_parent else Qt.CursorShape.ArrowCursor)
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(5 + indent * 20, 5, 5, 5)
        item_layout.setSpacing(5)
        
        # 如果是父节点，添加折叠图标
        if is_parent:
            fold_label = QLabel("▼")
            fold_label.setStyleSheet("color: #888888; font-size: 10px;")
            fold_label.setFixedWidth(12)
            item_layout.addWidget(fold_label)
        
        # 复选框
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 0px;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #888888;
                border-radius: 2px;
                background-color: transparent;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #007acc;
                border-radius: 2px;
                background-color: #007acc;
            }
            QCheckBox::indicator:checked::after {
                content: "✓";
                color: white;
                font-size: 8px;
            }
        """)
        checkbox.stateChanged.connect(lambda: self.on_item_changed(value))
        item_layout.addWidget(checkbox)
        
        # 文本标签（总是显示数量）
        display_text = f"{text} ({count})"
        label = QLabel(display_text)
        label.setStyleSheet("color: #cccccc; font-size: 13px;")
        if is_parent:
            label.setStyleSheet("color: #007acc; font-size: 13px; font-weight: bold;")
        item_layout.addWidget(label)
        item_layout.addStretch()
        
        # 存储引用
        self.items[value] = {
            "text": text,
            "count": count,
            "checked": checked,
            "checkbox": checkbox,
            "label": label,
            "widget": item_widget,
            "is_group": False,
            "is_parent": is_parent,
            "children": [],
            "fold_label": fold_label if is_parent else None,
            "is_expanded": True if is_parent else False,
            "indent": indent
        }
        
        # 如果是父节点，添加点击事件切换折叠状态
        if is_parent:
            item_widget.mousePressEvent = lambda event, v=value: self.toggle_fold(v, event)
        
        # 插入到布局（在stretch之前）
        self.options_layout.insertWidget(self.options_layout.count() - 1, item_widget)
        
        self.update_display()
    
    def set_parent_children(self, parent_value: str, child_values: list):
        """设置父节点的子节点列表
        
        Args:
            parent_value: 父节点值
            child_values: 子节点值列表
        """
        if parent_value in self.items:
            self.items[parent_value]["children"] = child_values
    
    def toggle_fold(self, parent_value: str, event):
        """切换父节点的折叠状态"""
        parent_item = self.items.get(parent_value)
        if not parent_item or not parent_item.get("is_parent"):
            return
        
        # 切换展开状态
        is_expanded = parent_item.get("is_expanded", True)
        parent_item["is_expanded"] = not is_expanded
        
        # 更新折叠图标
        fold_label = parent_item.get("fold_label")
        if fold_label:
            fold_label.setText("▼" if not is_expanded else "▶")
        
        # 显示/隐藏子节点
        self.toggle_children_visibility(parent_value, not is_expanded)
    
    def toggle_children_visibility(self, parent_value: str, visible: bool):
        """切换子节点的可见性"""
        parent_item = self.items.get(parent_value)
        if not parent_item:
            return
        
        for child_value in parent_item.get("children", []):
            child_item = self.items.get(child_value)
            if child_item:
                child_item["widget"].setVisible(visible)
                # 如果子节点也是父节点，递归处理
                if child_item.get("is_parent") and child_item.get("is_expanded"):
                    self.toggle_children_visibility(child_value, visible)
        
    def on_item_changed(self, value: str):
        """选项状态变化"""
        if value in self.items:
            self.items[value]["checked"] = self.items[value]["checkbox"].isChecked()
            self.update_display()
            self.emit_selection()
            
    def select_all(self):
        """全选"""
        for item in self.items.values():
            if not item.get("is_group", False):
                item["checkbox"].setChecked(True)
                item["checked"] = True
        self.update_display()
        self.emit_selection()
        
    def select_none(self):
        """全不选"""
        for item in self.items.values():
            if not item.get("is_group", False):
                item["checkbox"].setChecked(False)
                item["checked"] = False
        self.update_display()
        self.emit_selection()
        
    def get_selected_values(self) -> list:
        """获取选中的值列表"""
        return [v for v, item in self.items.items() if item.get("checked", False) and not item.get("is_group", False)]
        
    def get_selected_texts(self) -> list:
        """获取选中的文本列表"""
        return [item["text"] for item in self.items.values() if item.get("checked", False) and not item.get("is_group", False)]
        
    def update_display(self):
        """更新头部显示文本"""
        selected = self.get_selected_texts()
        # 计算非分组的选项总数
        total_count = sum(1 for item in self.items.values() if not item.get("is_group", False))
        
        if not selected:
            self.display_label.setText(self.placeholder)
            self.display_label.setStyleSheet("color: #888888; font-size: 13px;")
        elif len(selected) == total_count:
            # 全部选中时显示"全部X"（根据placeholder）
            if "题型" in self.placeholder:
                self.display_label.setText("全部题型")
            elif "知识点" in self.placeholder:
                self.display_label.setText("全部知识点")
            elif "难度" in self.placeholder:
                self.display_label.setText("全部难度")
            elif "课程" in self.placeholder:
                self.display_label.setText("全部课程")
            else:
                self.display_label.setText("全部")
            self.display_label.setStyleSheet("color: #ffffff; font-size: 13px;")
        else:
            # 部分选中时显示选中的项
            text = "，".join(selected)
            if len(text) > 15:
                text = text[:15] + "..."
            self.display_label.setText(text)
            self.display_label.setStyleSheet("color: #ffffff; font-size: 13px;")
            
    def emit_selection(self):
        """发送选中变化信号"""
        self.selection_changed.emit(self.get_selected_values())
        
    def on_header_clicked(self, event):
        """点击头部展开/收起下拉"""
        if self._is_open:
            self.close_dropdown()
        else:
            self.open_dropdown()
            
    def eventFilter(self, obj, event):
        """事件过滤器"""
        if obj == self.dropdown_panel:
            if event.type() == event.Type.MouseButtonPress:
                # 点击下拉面板外部时关闭
                if not self.dropdown_panel.rect().contains(event.pos()):
                    self.close_dropdown()
        return super().eventFilter(obj, event)
            
    def open_dropdown(self):
        """展开下拉面板"""
        # 定位下拉面板位置
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self.dropdown_panel.move(pos)
        self.dropdown_panel.setFixedWidth(self.width())
        self.dropdown_panel.show()
        self._is_open = True
        self.arrow_label.setText("▲")
        
    def close_dropdown(self):
        """收起下拉面板"""
        self.dropdown_panel.hide()
        self._is_open = False
        self.arrow_label.setText("▼")
        
    def update_item_count(self, value: str, count: int):
        """更新选项的数量显示"""
        if value in self.items:
            self.items[value]["count"] = count
            text = self.items[value]["text"]
            display_text = f"{text} ({count})" if count > 0 else text
            self.items[value]["label"].setText(display_text)
            
    def clear(self):
        """清空所有选项"""
        for item in self.items.values():
            item["widget"].deleteLater()
        self.items.clear()
        self.update_display()
        
    def set_selected(self, values: list, selected: bool = True):
        """设置指定值的选中状态"""
        for value in values:
            if value in self.items and not self.items[value].get("is_group", False):
                self.items[value]["checkbox"].setChecked(selected)
                self.items[value]["checked"] = selected
        self.update_display()

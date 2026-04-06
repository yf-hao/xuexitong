"""签到详情对话框。"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, 
    QHeaderView, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt
from models.attendance_record import AttendanceDetail
from models.activity import Activity


class AttendanceDetailDialog(QDialog):
    """签到详情对话框。"""
    
    def __init__(self, activity: Activity, detail: AttendanceDetail, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.detail = detail
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle(f"签到详情 - {self.activity.title}")
        self.resize(900, 600)
        
        # 设置对话框背景为暗色主题
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e0e0e0;
            }
            QTableWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                gridline-color: #404040;
                border: 1px solid #404040;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #007acc;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                color: #e0e0e0;
                padding: 5px;
                border: 1px solid #404040;
            }
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # 活动信息
        info_label = QLabel(
            f"<b style='color: #569cd6;'>活动名称：</b><span style='color: #e0e0e0;'>{self.activity.title}</span><br>"
            f"<b style='color: #569cd6;'>活动时间：</b><span style='color: #e0e0e0;'>{self.activity.time_range}</span><br>"
            f"<b style='color: #569cd6;'>创建时间：</b><span style='color: #e0e0e0;'>{self.activity.create_time}</span>"
        )
        info_label.setStyleSheet("padding: 10px; background: #2d2d2d; border-radius: 5px; border: 1px solid #404040;")
        layout.addWidget(info_label)
        
        # 统计信息
        stats = self.detail.get_statistics()
        stats_text = (
            f"<b style='color: #569cd6;'>签到统计：</b>"
            f"<span style='color: #e0e0e0;'>总人数：{stats['总人数']} | </span>"
            f"<span style='color: #4ec9b0;'>已签：{stats['已签']} | </span>"
            f"<span style='color: #f44747;'>未签：{stats['未签']} | </span>"
            f"<span style='color: #4ec9b0;'>代签：{stats['代签']} | </span>"
            f"<span style='color: #dcdcaa;'>迟到：{stats['迟到']} | </span>"
            f"<span style='color: #dcdcaa;'>早退：{stats['早退']} | </span>"
            f"<span style='color: #f44747;'>缺勤：{stats['缺勤']} | </span>"
            f"<span style='color: #9cdcfe;'>病假：{stats['病假']} | </span>"
            f"<span style='color: #9cdcfe;'>事假：{stats['事假']}</span>"
        )
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("padding: 10px; background: #2d2d2d; font-size: 13px; border-radius: 5px; border: 1px solid #404040;")
        stats_label.setWordWrap(True)
        layout.addWidget(stats_label)
        
        # 签到记录表格
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["姓名", "学号", "签到状态", "签到时间"])
        table.setRowCount(len(self.detail))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(2, 100)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        for row, record in enumerate(self.detail):
            # 姓名
            table.setItem(row, 0, QTableWidgetItem(record.name))
            
            # 学号
            table.setItem(row, 1, QTableWidgetItem(record.username))
            
            # 签到状态
            status_item = QTableWidgetItem(record.status_name)
            if record.is_normal or record.is_proxy:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif record.is_late or record.is_early_leave:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            elif record.is_absent or record.is_unsign:
                status_item.setForeground(Qt.GlobalColor.red)
            elif record.is_leave:
                status_item.setForeground(Qt.GlobalColor.blue)
            table.setItem(row, 2, status_item)
            
            # 签到时间
            table.setItem(row, 3, QTableWidgetItem(record.submit_time))
        
        layout.addWidget(table)
        
        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

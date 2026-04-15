"""缺勤统计对话框。"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QFileDialog, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from core.communication_manager import CommunicationManager
from core.exporters.absence_stats_exporter import build_absence_stats_filename
from ui.workers import AbsenceStatsExportWorker


class AbsenceStatsDialog(QDialog):
    """缺勤统计对话框。"""
    
    def __init__(
        self,
        absence_stats: dict,
        total_activities: int,
        course_id: str,
        class_id: str,
        teaching_class_name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.absence_stats = absence_stats
        self.total_activities = total_activities
        self.course_id = course_id
        self.class_id = class_id
        self.teaching_class_name = teaching_class_name
        self.communication_manager = CommunicationManager()
        self.table = None
        self.export_worker = None
        self.export_btn = None
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("缺勤统计")
        self.resize(800, 600)
        
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
        
        # 统计信息
        total_students = len(self.absence_stats)
        info_text = (
            f"<b style='color: #569cd6;'>统计信息：</b>"
            f"<span style='color: #e0e0e0;'>共 {self.total_activities} 次签到活动 | </span>"
            f"<span style='color: #f44747;'>{total_students} 名学生有缺勤记录</span>"
        )
        info_label = QLabel(info_text)
        info_label.setStyleSheet("padding: 10px; background: #2d2d2d; border-radius: 5px; border: 1px solid #404040;")
        layout.addWidget(info_label)
        
        # 缺勤学生表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["姓名", "学号", "班级", "缺勤次数", "总签到次数", "沟通情况"])
        
        # 按缺勤次数降序排序
        sorted_stats = sorted(
            self.absence_stats.items(), 
            key=lambda x: x[1]['absent_count'], 
            reverse=True
        )
        
        self.table.setRowCount(len(sorted_stats))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 100)  # 姓名
        self.table.setColumnWidth(1, 140)  # 学号
        self.table.setColumnWidth(3, 100)  # 缺勤次数
        self.table.setColumnWidth(4, 100)  # 总签到次数
        self.table.setColumnWidth(5, 80)   # 沟通情况
        
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # 连接单元格点击事件
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.table)
        self.copy_shortcut.activated.connect(self._copy_current_row)
        
        for row, (uid, stats) in enumerate(sorted_stats):
            # 姓名
            self.table.setItem(row, 0, QTableWidgetItem(stats['name']))
            
            # 学号
            self.table.setItem(row, 1, QTableWidgetItem(stats['username']))

            # 班级
            self.table.setItem(row, 2, QTableWidgetItem(stats.get('class_name', '')))
            
            # 缺勤次数
            absent_item = QTableWidgetItem(str(stats['absent_count']))
            absent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            absent_item.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 3, absent_item)
            
            # 总签到次数
            total_item = QTableWidgetItem(str(stats['total_count']))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, total_item)
            
            # 沟通情况 - 从文件加载已保存的状态
            person_id = int(uid)
            communicated = self.communication_manager.get_status(
                self.course_id, 
                self.class_id, 
                person_id
            )
            comm_item = QTableWidgetItem("☑" if communicated else "☐")
            comm_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 存储 person_id 到单元格数据中
            comm_item.setData(Qt.ItemDataRole.UserRole, person_id)
            if communicated:
                comm_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                comm_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 5, comm_item)
        
        layout.addWidget(self.table)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        self.export_btn = QPushButton("导出")
        self.export_btn.setFixedWidth(100)
        self.export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
    
    def _on_cell_clicked(self, row: int, column: int):
        """处理表格单元格点击事件。"""
        # 只处理"沟通情况"列（第5列）的点击
        if column != 5:
            return
        
        # 从单元格数据中获取 person_id
        comm_item = self.table.item(row, 5)
        if not comm_item:
            return
        
        person_id = comm_item.data(Qt.ItemDataRole.UserRole)
        if not person_id:
            return
        
        # 切换沟通状态
        new_status = self.communication_manager.toggle_status(
            self.course_id,
            self.class_id,
            person_id
        )
        
        # 更新表格显示
        comm_item.setText("☑" if new_status else "☐")
        if new_status:
            comm_item.setForeground(Qt.GlobalColor.darkGreen)
        else:
            comm_item.setForeground(Qt.GlobalColor.gray)
    
    def keyPressEvent(self, event):
        """处理键盘事件。"""
        # 检查是否按了 Enter 键
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            current_row = self.table.currentRow()
            if current_row >= 0:
                # 切换当前行的沟通状态
                self._on_cell_clicked(current_row, 5)
                return
        
        # 其他键盘事件交给父类处理
        super().keyPressEvent(event)

    def _copy_current_row(self):
        """复制当前选中行的数据。"""
        current_row = self.table.currentRow()
        if current_row < 0:
            return

        row_values = []
        for column in range(self.table.columnCount()):
            item = self.table.item(current_row, column)
            row_values.append(item.text().strip() if item else "")

        QApplication.clipboard().setText(",".join(row_values))

    def _on_export_clicked(self):
        """导出缺勤统计 Excel。"""
        default_name = build_absence_stats_filename(self.teaching_class_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出缺勤统计",
            default_name,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"

        self.export_btn.setEnabled(False)
        self.export_btn.setText("导出中...")
        self.export_worker = AbsenceStatsExportWorker(
            absence_stats=self.absence_stats,
            total_activities=self.total_activities,
            save_path=file_path,
            course_id=self.course_id,
            class_id=self.class_id,
        )
        self.export_worker.export_finished.connect(self._on_export_finished)
        self.export_worker.start()

    def _on_export_finished(self, success: bool, message: str):
        """处理导出完成。"""
        if self.export_btn:
            self.export_btn.setEnabled(True)
            self.export_btn.setText("导出")
        if success:
            QMessageBox.information(self, "导出完成", f"缺勤统计已导出到：\n{message}")
        else:
            QMessageBox.warning(self, "导出失败", message)
        self.export_worker = None

    def closeEvent(self, event):
        """导出中阻止关闭，避免线程对象提前销毁。"""
        if self.export_worker and self.export_worker.isRunning():
            QMessageBox.information(self, "导出中", "缺勤统计正在导出，请等待导出完成。")
            event.ignore()
            return
        super().closeEvent(event)

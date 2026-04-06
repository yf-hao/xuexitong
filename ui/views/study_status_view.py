from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLabel, QFrame, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from ui.styles import STAT_BUTTON_STYLE, STAT_CARD_CONTAINER_STYLE, STAT_CARD_STYLE
from ui.workers import AttendanceWorker, AttendanceDetailWorker, AbsenceStatsWorker, HomeworkWorker
from models.activity import Activity
from core.communication_manager import CommunicationManager


class StudyStatusView(QWidget):
    """学情视图 - 显示学生学习情况"""
    
    status_update = pyqtSignal(str)
    
    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.workers = []
        self.last_sub = None
        self.current_attendance_data = None  # 保存当前考勤数据
        self.current_course_id = None        # 当前课程 ID
        self.current_class_id = None         # 当前班级 ID
        self.communication_manager = CommunicationManager()  # 沟通状态管理器
        
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QGridLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.layout.setContentsMargins(10, 20, 10, 10)
        self.layout.setSpacing(25)
        
        # 功能按钮
        self.btn_attendance = QPushButton("📊 考勤情况")
        self.btn_homework = QPushButton("✍️ 作业情况")
        self.btn_quiz = QPushButton("📝 测验情况")
        self.btn_midterm = QPushButton("📋 期中考试")
        
        self.buttons = [self.btn_attendance, self.btn_homework, self.btn_quiz, self.btn_midterm]
        
        for btn in self.buttons:
            btn.setStyleSheet(STAT_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
        self.layout.addWidget(self.btn_attendance, 0, 0)
        self.layout.addWidget(self.btn_homework, 0, 1)
        self.layout.addWidget(self.btn_quiz, 0, 2)
        self.layout.addWidget(self.btn_midterm, 0, 3)
        
        # 结果区域
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet(STAT_CARD_CONTAINER_STYLE)
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setSpacing(10)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.content_frame)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.layout.addWidget(self.scroll_area, 1, 0, 1, 4)
        
        # 连接信号
        self.btn_attendance.clicked.connect(self.on_attendance_clicked)
        self.btn_homework.clicked.connect(self.on_homework_clicked)
        self.btn_quiz.clicked.connect(self.on_quiz_clicked)
        self.btn_midterm.clicked.connect(self.on_midterm_clicked)

    def clear_content(self):
        """清空内容区域"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_loading(self, message: str):
        """显示加载提示"""
        self.clear_content()
        loading_label = QLabel(message)
        loading_label.setStyleSheet("color: #007acc; padding: 20px;")
        self.content_layout.addWidget(loading_label)

    def _show_placeholder(self, message: str):
        """显示占位提示"""
        self.clear_content()
        label = QLabel(message)
        label.setStyleSheet("color: #888; font-size: 14px; padding: 20px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(label)

    def on_attendance_clicked(self):
        """考勤情况"""
        self.last_sub = "attendance"
        self._highlight_button(self.btn_attendance)
        self.status_update.emit("正在加载考勤情况...")
        
        self._show_loading("正在同步考勤情况数据，请稍候...")
        
        # 获取当前课程和班级 ID
        from ui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            course = main_window.course_box.currentData()
            class_id = main_window.clazz_box.currentData()
            if course and class_id:
                self.current_course_id = str(course.id)
                self.current_class_id = str(class_id)
        
        # 调用 API 获取考勤数据
        self.attendance_worker = AttendanceWorker(self.crawler)
        self.attendance_worker.attendance_ready.connect(self._display_attendance)
        self.attendance_worker.start()
    
    def _display_attendance(self, result):
        """显示考勤数据"""
        self.clear_content()
        
        if isinstance(result, str):
            # 错误信息
            error_label = QLabel(f"❌ {result}")
            error_label.setStyleSheet("color: #ff5252; padding: 20px; font-size: 14px;")
            self.content_layout.addWidget(error_label)
            self.status_update.emit("考勤情况加载失败")
            return
        
        if not result or len(result) == 0:
            # 无数据
            empty_label = QLabel("💡 未找到考勤活动记录")
            empty_label.setStyleSheet("color: #888; padding: 20px; font-size: 14px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(empty_label)
            self.status_update.emit("考勤情况加载完成（无数据）")
            return
        
        # 只显示已结束的签到活动
        ended_attendance = [
            activity for activity in result
            if activity.is_ended and activity.activity_type == 2
        ]
        
        if not ended_attendance:
            empty_label = QLabel("💡 未找到已结束的签到活动记录")
            empty_label.setStyleSheet("color: #888; padding: 20px; font-size: 14px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(empty_label)
            self.status_update.emit("考勤情况加载完成（无已结束的签到）")
            return
        
        # 保存当前数据
        self.current_attendance_data = ended_attendance
        
        # 创建表格显示考勤数据
        self.attendance_table = QTableWidget()
        self.attendance_table.setColumnCount(6)
        self.attendance_table.setHorizontalHeaderLabels(["活动名称", "活动类型", "创建时间", "活动时间", "状态", "操作"])
        self.attendance_table.setRowCount(len(ended_attendance))
        self.attendance_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.attendance_table.setAlternatingRowColors(True)
        self.attendance_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.attendance_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 连接双击事件
        self.attendance_table.doubleClicked.connect(self._on_attendance_double_clicked)
        
        for row, activity in enumerate(ended_attendance):
            # 活动名称
            self.attendance_table.setItem(row, 0, QTableWidgetItem(activity.title))
            
            # 活动类型
            self.attendance_table.setItem(row, 1, QTableWidgetItem(activity.type_name))
            
            # 创建时间
            self.attendance_table.setItem(row, 2, QTableWidgetItem(activity.create_time))
            
            # 活动时间
            self.attendance_table.setItem(row, 3, QTableWidgetItem(activity.time_range))
            
            # 状态
            status_item = QTableWidgetItem(activity.status_name)
            status_item.setForeground(Qt.GlobalColor.darkGray)
            self.attendance_table.setItem(row, 4, status_item)
            
            # 查看按钮
            view_btn = QPushButton("查看")
            view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #007acc;
                    border: 1px solid #007acc;
                    border-radius: 3px;
                    padding: 4px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #007acc;
                    color: white;
                }
            """)
            # 使用 lambda 捕获当前的 activity 和 row
            view_btn.clicked.connect(lambda checked, a=activity: self._view_attendance_detail(a))
            
            # 创建一个单元格 widget 来放置按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.addWidget(view_btn)
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.setContentsMargins(5, 2, 5, 2)
            
            self.attendance_table.setCellWidget(row, 5, btn_widget)
        
        # 设置操作列宽度
        self.attendance_table.setColumnWidth(5, 80)
        
        self.content_layout.addWidget(self.attendance_table)
        
        # 添加缺勤统计按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_absence_stats = QPushButton("📊 缺勤统计")
        self.btn_absence_stats.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_absence_stats.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        self.btn_absence_stats.clicked.connect(self._on_absence_stats_clicked)
        btn_layout.addWidget(self.btn_absence_stats)
        
        self.content_layout.addLayout(btn_layout)
        
        self.status_update.emit(f"考勤情况加载完成，共 {len(ended_attendance)} 条已结束的签到记录")
    
    def _on_attendance_double_clicked(self, index):
        """双击考勤记录时触发"""
        if not self.current_attendance_data:
            return
        
        row = index.row()
        if row < 0 or row >= len(self.current_attendance_data):
            return
        
        activity = self.current_attendance_data[row]
        self._view_attendance_detail(activity)
    
    def _view_attendance_detail(self, activity: Activity):
        """查看签到详情"""
        self.status_update.emit(f"正在加载 {activity.title} 的签到详情...")
        
        # 异步获取签到详情
        self.detail_worker = AttendanceDetailWorker(self.crawler, activity.active_id)
        self.detail_worker.detail_ready.connect(
            lambda detail: self._show_attendance_detail(activity, detail)
        )
        self.detail_worker.start()
    
    def _show_attendance_detail(self, activity: Activity, detail):
        """显示签到详情对话框"""
        if isinstance(detail, str):
            # 错误信息
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "加载失败", f"获取签到详情失败：\n{detail}")
            self.status_update.emit("签到详情加载失败")
            return
        
        # 导入并显示对话框
        from ui.dialogs.attendance_detail_dialog import AttendanceDetailDialog
        dialog = AttendanceDetailDialog(activity, detail, self)
        dialog.exec()
        
        self.status_update.emit("签到详情加载完成")
    
    def _on_absence_stats_clicked(self):
        """点击缺勤统计按钮"""
        if not self.current_attendance_data:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "无数据", "请先加载考勤情况数据")
            return
        
        self.status_update.emit("正在统计缺勤情况，请稍候...")
        
        # 异步统计缺勤数据
        self.absence_worker = AbsenceStatsWorker(self.crawler, self.current_attendance_data)
        self.absence_worker.stats_ready.connect(self._show_absence_stats)
        self.absence_worker.start()
    
    def _show_absence_stats(self, result):
        """显示缺勤统计对话框"""
        if isinstance(result, str):
            # 错误信息
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "统计失败", f"统计缺勤数据失败：\n{result}")
            self.status_update.emit("缺勤统计失败")
            return
        
        # 检查是否有课程和班级 ID
        if not self.current_course_id or not self.current_class_id:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "错误", "无法获取课程信息")
            self.status_update.emit("缺勤统计失败")
            return
        
        # 导入并显示对话框
        from ui.dialogs.absence_stats_dialog import AbsenceStatsDialog
        dialog = AbsenceStatsDialog(
            result, 
            len(self.current_attendance_data),
            self.current_course_id,
            self.current_class_id,
            self
        )
        dialog.exec()
        
        self.status_update.emit("缺勤统计完成")

    def on_homework_clicked(self):
        """作业情况"""
        self.last_sub = "homework"
        self._highlight_button(self.btn_homework)
        self.status_update.emit("正在加载作业情况...")
        
        self._show_loading("正在同步作业情况数据，请稍候...")
        
        # 获取当前课程和班级 ID
        from ui.main_window import MainWindow
        main_window = self.window()
        if not isinstance(main_window, MainWindow):
            self._show_placeholder("❌ 无法获取课程信息")
            self.status_update.emit("作业情况加载失败")
            return
        
        course = main_window.course_box.currentData()
        class_id = main_window.clazz_box.currentData()
        
        if not course or not class_id:
            self._show_placeholder("❌ 请先选择课程和班级")
            self.status_update.emit("作业情况加载失败")
            return
        
        # 保存当前课程和班级 ID
        self.current_course_id = str(course.id)
        self.current_class_id = str(class_id)
        
        # 异步获取作业数据
        self.homework_worker = HomeworkWorker(self.crawler, self.current_course_id, self.current_class_id)
        self.homework_worker.homework_ready.connect(self._display_homework)
        self.homework_worker.start()
    
    def _display_homework(self, result):
        """显示学生作业统计数据"""
        self.clear_content()
        
        if isinstance(result, str):
            # 错误信息
            error_label = QLabel(f"❌ {result}")
            error_label.setStyleSheet("color: #ff5252; padding: 20px; font-size: 14px;")
            self.content_layout.addWidget(error_label)
            self.status_update.emit("学生作业统计加载失败")
            return
        
        if not result or len(result) == 0:
            # 无数据
            empty_label = QLabel("💡 未找到学生作业统计记录")
            empty_label.setStyleSheet("color: #888; padding: 20px; font-size: 14px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(empty_label)
            self.status_update.emit("学生作业统计加载完成（无数据）")
            return
        
        # 创建表格显示学生作业统计数据
        self.homework_table = QTableWidget()
        self.homework_table.setColumnCount(10)
        self.homework_table.setHorizontalHeaderLabels(["学号", "姓名", "作业数", "已提交", "待批", "未提交", "平均分", "最低分", "最高分", "沟通情况"])
        self.homework_table.setRowCount(len(result))
        self.homework_table.setAlternatingRowColors(True)
        self.homework_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.homework_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 暂时禁用排序，填充数据时避免性能问题
        self.homework_table.setSortingEnabled(False)
        
        # 设置列宽
        self.homework_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # 学号
        self.homework_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # 姓名
        self.homework_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)         # 作业数
        self.homework_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)         # 已提交
        self.homework_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)         # 待批
        self.homework_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)         # 未提交
        self.homework_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)         # 平均分
        self.homework_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)         # 最低分
        self.homework_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)         # 最高分
        self.homework_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)         # 沟通情况
        
        self.homework_table.setColumnWidth(0, 120)  # 学号
        self.homework_table.setColumnWidth(1, 100)  # 姓名
        self.homework_table.setColumnWidth(2, 70)   # 作业数
        self.homework_table.setColumnWidth(3, 70)   # 已提交
        self.homework_table.setColumnWidth(4, 70)   # 待批
        self.homework_table.setColumnWidth(5, 70)   # 未提交
        self.homework_table.setColumnWidth(6, 70)   # 平均分
        self.homework_table.setColumnWidth(7, 70)   # 最低分
        self.homework_table.setColumnWidth(8, 70)   # 最高分
        self.homework_table.setColumnWidth(9, 80)   # 沟通情况
        
        # 连接单元格点击事件
        self.homework_table.cellClicked.connect(self._on_homework_cell_clicked)
        
        for row, stats in enumerate(result):
            # 学号
            self.homework_table.setItem(row, 0, QTableWidgetItem(stats.alias_name))
            
            # 姓名
            self.homework_table.setItem(row, 1, QTableWidgetItem(stats.user_name))
            
            # 作业数 - 居中对齐
            complete_item = QTableWidgetItem(str(stats.complete_num))
            complete_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.homework_table.setItem(row, 2, complete_item)
            
            # 已提交 - 居中对齐
            submitted_item = QTableWidgetItem(str(stats.work_submitted))
            submitted_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.homework_table.setItem(row, 3, submitted_item)
            
            # 待批 - 居中对齐
            pending_item = QTableWidgetItem(str(stats.pending_count))
            pending_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stats.pending_count > 0:
                pending_item.setForeground(Qt.GlobalColor.red)
            self.homework_table.setItem(row, 4, pending_item)
            
            # 未提交 - 居中对齐
            unsubmitted_item = QTableWidgetItem(str(stats.unsubmitted_count))
            unsubmitted_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stats.unsubmitted_count > 0:
                unsubmitted_item.setForeground(Qt.GlobalColor.red)
            self.homework_table.setItem(row, 5, unsubmitted_item)
            
            # 平均分 - 显示真实平均分（未交作业按0分计算）
            real_avg = stats.real_avg_score
            avg_item = QTableWidgetItem(f"{real_avg:.2f}")
            avg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 真实平均分低于60分标红
            if real_avg < 60:
                avg_item.setForeground(Qt.GlobalColor.red)
            self.homework_table.setItem(row, 6, avg_item)
            
            # 最低分
            min_item = QTableWidgetItem(f"{stats.min_score:.1f}")
            min_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.homework_table.setItem(row, 7, min_item)
            
            # 最高分
            max_item = QTableWidgetItem(f"{stats.max_score:.1f}")
            max_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.homework_table.setItem(row, 8, max_item)
            
            # 沟通情况 - 从文件加载已保存的状态
            communicated = self.communication_manager.get_status(
                self.current_course_id, 
                self.current_class_id, 
                stats.person_id
            )
            # 未沟通显示空心方框，已沟通显示打勾方框
            comm_item = QTableWidgetItem("☑" if communicated else "☐")
            comm_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 存储 person_id 到单元格数据中，确保排序后仍能正确关联
            comm_item.setData(Qt.ItemDataRole.UserRole, stats.person_id)
            if communicated:
                comm_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                comm_item.setForeground(Qt.GlobalColor.gray)
            self.homework_table.setItem(row, 9, comm_item)
        
        # 数据填充完成，启用排序功能
        self.homework_table.setSortingEnabled(True)
        
        # 默认按未提交数量降序排序（第5列）
        self.homework_table.sortItems(5, Qt.SortOrder.DescendingOrder)
        
        self.content_layout.addWidget(self.homework_table)
        self.status_update.emit(f"学生作业统计加载完成，共 {len(result)} 名学生")
    
    def _on_homework_cell_clicked(self, row: int, column: int):
        """处理作业表格单元格点击事件。"""
        # 只处理"沟通情况"列（第9列）的点击
        if column != 9:
            return
        
        # 从单元格数据中获取 person_id
        comm_item = self.homework_table.item(row, 9)
        if not comm_item:
            return
        
        person_id = comm_item.data(Qt.ItemDataRole.UserRole)
        if not person_id:
            return
        
        # 切换沟通状态
        new_status = self.communication_manager.toggle_status(
            self.current_course_id,
            self.current_class_id,
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
            # 检查当前是否在作业表格界面
            if hasattr(self, 'homework_table') and self.homework_table:
                current_row = self.homework_table.currentRow()
                if current_row >= 0:
                    # 切换当前行的沟通状态
                    self._on_homework_cell_clicked(current_row, 9)
                    return
        
        # 其他键盘事件交给父类处理
        super().keyPressEvent(event)

    def on_quiz_clicked(self):
        """测验情况"""
        self.last_sub = "quiz"
        self._highlight_button(self.btn_quiz)
        self.status_update.emit("正在加载测验情况...")
        
        self._show_loading("正在同步测验情况数据，请稍候...")
        
        # TODO: 调用API获取测验数据
        
        self.status_update.emit("测验情况加载完成")

    def on_midterm_clicked(self):
        """期中考试"""
        self.last_sub = "midterm"
        self._highlight_button(self.btn_midterm)
        self.status_update.emit("正在加载期中考试...")
        
        self._show_loading("正在同步期中考试数据，请稍候...")
        
        # TODO: 调用API获取期中考试数据
        
        self.status_update.emit("期中考试加载完成")

    def _highlight_button(self, active_btn):
        """高亮选中的按钮"""
        for btn in self.buttons:
            if btn == active_btn:
                btn.setStyleSheet(STAT_BUTTON_STYLE + "border: 2px solid #007acc;")
            else:
                btn.setStyleSheet(STAT_BUTTON_STYLE)

    def on_show(self):
        """视图显示时调用"""
        if self.last_sub:
            self.restore_sub_feature(self.last_sub)

    def restore_sub_feature(self, sub_name):
        """恢复子功能"""
        if sub_name == "attendance":
            self.on_attendance_clicked()
        elif sub_name == "homework":
            self.on_homework_clicked()
        elif sub_name == "quiz":
            self.on_quiz_clicked()
        elif sub_name == "midterm":
            self.on_midterm_clicked()
    
    def keyPressEvent(self, event):
        """处理键盘事件"""
        from PyQt6.QtCore import Qt
        
        # 如果按下回车键且当前有考勤表格
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if hasattr(self, 'attendance_table') and self.attendance_table:
                current_row = self.attendance_table.currentRow()
                if current_row >= 0:
                    # 创建一个模拟的索引对象
                    from PyQt6.QtCore import QModelIndex
                    index = self.attendance_table.model().index(current_row, 0)
                    self._on_attendance_double_clicked(index)
                    return
        
        # 其他键传递给父类处理
        super().keyPressEvent(event)

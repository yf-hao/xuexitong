import requests
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame, QScrollArea, QSpinBox,
    QCheckBox, QMessageBox, QInputDialog, QFileDialog, QApplication, QDialog, QListWidget, QListWidgetItem,
    QLineEdit, QTextEdit, QComboBox, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QCoreApplication, QUrl, QTimer, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImageReader, QPainter, QColor, QLinearGradient, QFont
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from ui.workers import (
    CreateCourseWorker, UpdateCourseDataWorker, CourseStateWorker, FullCourseInfoWorker,
    GetTeachersWorker, AddTeamTeacherWorker, RemoveTeamTeacherWorker,
    CloneVerifyWorker, CloneSubmitVerifyWorker, CloneActionWorker, ClazzManageWorker,
    RenameClazzWorker, ParseStudentExcelWorker, AddStudentsBatchWorker,
    GetWeightWorker, WeightWorker, DeleteClazzWorker
)
from ui.styles import STAT_BUTTON_STYLE, STAT_CARD_CONTAINER_STYLE, STAT_CARD_STYLE, MAIN_STYLE

class ImportCourseListWorker(QThread):
    finished = pyqtSignal(object, str)

    def __init__(self, session, url: str, headers: dict | None = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.url = url
        self.headers = headers or {}

    def run(self):
        try:
            print(f"DEBUG: ImportCourseListWorker fetching URL: {self.url}")
            resp = self.session.get(self.url, headers=self.headers, timeout=10)
            print(f"DEBUG: ImportCourseListWorker response status: {resp.status_code}")
            if resp.status_code != 200:
                self.finished.emit(None, f"HTTP {resp.status_code}")
            else:
                text = resp.text
                if "请先登录" in text or "login" in text.lower() and len(text) < 2000:
                    print("DEBUG: ImportCourseListWorker detected redirect to login or login prompt.")
                    self.finished.emit(None, "登录超时，请重新登录")
                else:
                    print(f"DEBUG: ImportCourseListWorker success, response length: {len(text)}")
                    self.finished.emit(text, None)
        except Exception as e:
            print(f"DEBUG: ImportCourseListWorker error: {e}")
            self.finished.emit(None, str(e))

class ImportProcessWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, session, url: str, headers: dict | None = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.url = url
        self.headers = headers or {}

    def run(self):
        try:
            resp = self.session.get(self.url, headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self.finished.emit(False, f"HTTP错误: {resp.status_code}")
                return
            
            try:
                data = resp.json()
                if data.get("status"):
                    self.finished.emit(True, data.get("msg", "操作成功"))
                else:
                    self.finished.emit(False, data.get("msg", "操作失败"))
            except Exception:
                self.finished.emit(False, f"解析返回内容失败: {resp.text[:100]}")
        except Exception as e:
            self.finished.emit(False, str(e))


class ManagementView(QWidget):
    def __init__(self, crawler, status_callback, get_classes_callback, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.status_callback = status_callback
        self.get_classes_callback = get_classes_callback # Callback to get list of class IDs for sync
        self.workers = []
        self.last_manage_sub = None
        self.grade_spinboxes = {}
        self.cover_network_manager = QNetworkAccessManager(self)
        
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QGridLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.layout.setContentsMargins(10, 20, 10, 10)
        self.layout.setSpacing(25)
        
        # Buttons
        self.btn_class_management = QPushButton("📁 班级管理")
        self.btn_grade_weight = QPushButton("⚖️ 成绩权重")
        self.btn_teacher_team = QPushButton("👥 教师团队管理")
        self.btn_course_management = QPushButton("⚙️ 课程管理")
        
        self.buttons = [
            self.btn_class_management, self.btn_grade_weight, 
            self.btn_teacher_team, self.btn_course_management
        ]
        
        for btn in self.buttons:
            btn.setStyleSheet(STAT_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
        self.layout.addWidget(self.btn_class_management, 0, 0)
        self.layout.addWidget(self.btn_grade_weight, 0, 1)
        self.layout.addWidget(self.btn_teacher_team, 0, 2)
        self.layout.addWidget(self.btn_course_management, 0, 3)
        
        # Result area
        self.management_scroll = QFrame()
        self.management_scroll.setStyleSheet(STAT_CARD_CONTAINER_STYLE)
        self.management_scroll_layout = QVBoxLayout(self.management_scroll)
        self.management_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.management_scroll_layout.setSpacing(10)
        
        self.management_scroll_area = QScrollArea()
        self.management_scroll_area.setWidgetResizable(True)
        self.management_scroll_area.setWidget(self.management_scroll)
        self.management_scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.layout.addWidget(self.management_scroll_area, 1, 0, 1, 4)
        
        # Connect signals
        self.btn_class_management.clicked.connect(self.on_class_management_clicked)
        self.btn_grade_weight.clicked.connect(self.on_grade_weight_clicked)
        self.btn_teacher_team.clicked.connect(self.on_teacher_team_clicked)
        self.btn_course_management.clicked.connect(self.on_course_management_clicked)

    def clear_management_list(self):
        """清空管理面板内容，包含嵌套的 layout 和 spacer。"""
        def _clear_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                w = child.widget()
                if w is not None:
                    w.deleteLater()
                    continue
                child_layout = child.layout()
                if child_layout is not None:
                    _clear_layout(child_layout)
                    continue
                # spacerItem 直接丢弃
        _clear_layout(self.management_scroll_layout)
        # 不再重建 layout，避免 Qt 对重复设置 layout 的警告；保持已有 layout 引用

    def on_class_management_clicked(self):
        self.last_manage_sub = "class_management"
        self.clear_management_list()
        
        loading_label = QLabel("正在同步班级管理列表，请稍候...")
        loading_label.setStyleSheet("color: #007acc; padding: 20px; font-size: 14px;")
        self.management_scroll_layout.addWidget(loading_label)
        
        params = self.crawler.session_manager.course_params
        course_id = params.get('courseid')
        clazz_id = params.get('clazzid')

        self.status_callback(f"DEBUG 班级管理请求 courseid={course_id}, clazzid={clazz_id}")
        
        if not course_id:
            self.status_callback("错误: 未找到当前课程ID")
            return
            
        worker = ClazzManageWorker(self.crawler, course_id, clazz_id or "")
        self.status_callback(f"DEBUG ClazzManageWorker start with courseid={course_id}, clazzid={clazz_id}")
        self.workers.append(worker)
        worker.classes_ready.connect(self._display_clazz_manage_results)
        worker.classes_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        self.status_callback("正在加载班级管理列表...")

    def _display_clazz_manage_results(self, class_list):
        self.clear_management_list()

        self.status_callback(f"DEBUG 班级列表返回数量: {len(class_list)}")
        
        # 顶部操作条：新建班级按钮（暂不实现点击逻辑）
        self._add_new_class_top_bar()
        
        if not class_list:
            error_label = QLabel("未找到班级数据或同步失败。")
            error_label.setStyleSheet("color: #ff4d4d; padding: 20px;")
            self.management_scroll_layout.addWidget(error_label)
            return
        
        for item in class_list:
            card = QFrame()

            card.setObjectName("stats_card") 
            card.setStyleSheet(STAT_CARD_STYLE)
            layout = QHBoxLayout(card)
            
            # Highlight current class if id matches
            current_clazz_id = self.crawler.session_manager.course_params.get('clazzid')
            is_current = str(item['id']) == str(current_clazz_id)
            
            name_text = f"🏢 {item['name']}"
            if is_current:
                name_text += " (当前)"
                
            name_label = QLabel(name_text)
            name_label.setStyleSheet(f"color: {'#00bfff' if is_current else '#ffffff'}; font-size: 15px; font-weight: bold;")
            
            id_label = QLabel(f"ID: {item['id']}")
            id_label.setStyleSheet("color: #888888; font-size: 12px;")
            
            layout.addWidget(name_label)
            layout.addStretch()
            
            # Action Buttons
            btn_add_student = QPushButton("➕ 添加学生")
            btn_distribute = QPushButton("分配")
            btn_rename = QPushButton("✏️ 重命名")
            btn_delete = QPushButton("📦 归档")
            
            btn_add_student.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_distribute.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
            
            common_btn_style = """
                QPushButton {
                    background-color: transparent;
                    color: #007acc;
                    border: 1px solid #007acc;
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: normal;
                    min-width: 60px;
                }
                QPushButton:hover {
                    background-color: #007acc;
                    color: white;
                }
            """
            delete_btn_style = common_btn_style.replace("#007acc", "#888888")
            
            btn_add_student.setStyleSheet(common_btn_style)
            btn_distribute.setStyleSheet(common_btn_style)
            btn_rename.setStyleSheet(common_btn_style)
            btn_delete.setStyleSheet(delete_btn_style)
            
            layout.addWidget(btn_add_student)
            layout.addWidget(btn_distribute)
            layout.addWidget(btn_rename)
            layout.addWidget(btn_delete)
            
            # Connect signals
            cid = str(item['id'])
            cname = item['name']
            btn_add_student.clicked.connect(lambda _, id=cid, name=cname: self._handle_clazz_add_student(id, name))
            btn_rename.clicked.connect(lambda _, id=cid, name=cname: self._handle_clazz_rename(id, name))
            btn_delete.clicked.connect(lambda _, id=cid, name=cname: self._handle_clazz_delete(id, name))
            btn_distribute.clicked.connect(lambda _, id=cid, name=cname: self._handle_clazz_distribute(id, name))

            layout.addWidget(id_label)
            
            self.management_scroll_layout.addWidget(card)

    def _handle_clazz_add_student(self, clazz_id, name):
        QMessageBox.information(self, "添加学生", "请上传从树维教务系统下载的【成绩登记册】。")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择成绩登记册", "", "Excel Files (*.xls *.xlsx);;All Files (*)"
        )

        if file_path:
            self.status_callback(f"正在解析文件: {file_path}")
            worker = ParseStudentExcelWorker(file_path)
            self.workers.append(worker)
            worker.parse_finished.connect(lambda success, msg, students: self._on_parse_finished(success, msg, students, clazz_id, name))
            worker.parse_finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_parse_finished(self, success, message, students, clazz_id, name):
        if success:
            student_count = len(students)
            student_list_text = "\n".join([f"{i+1}. {s['name']} (学号: {s['student_id']})" for i, s in enumerate(students[:10])])
            if student_count > 10:
                student_list_text += f"\n... 还有 {student_count - 10} 名学生"

            # 询问是否上传
            reply = QMessageBox.question(
                self,
                "确认上传",
                f"成功解析出 {student_count} 名学生。\n\n是否立即上传到班级 '{name}' ？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._start_upload_students(students, clazz_id, name)
            else:
                self.status_callback(f"解析成功，共 {student_count} 名学生（已取消上传）")
        else:
            QMessageBox.warning(self, "解析失败", message)
            self.status_callback(message)

    def _start_upload_students(self, students, clazz_id, name):
        # 获取course_id
        params = self.crawler.session_manager.course_params
        course_id = params.get('courseid')

        # 显示进度对话框
        self.progress_dialog = QMessageBox(self)
        self.progress_dialog.setWindowTitle("上传进度")
        self.progress_dialog.setText("准备上传学生...")
        self.progress_dialog.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self.progress_dialog.setWindowModality(Qt.WindowModality.NonModal)  # 非模态对话框
        self.progress_dialog.show()
        self.progress_dialog.raise_()  # 确保对话框显示在最前面

        self.status_callback(f"开始上传 {len(students)} 名学生到班级 '{name}'")

        worker = AddStudentsBatchWorker(self.crawler, students, clazz_id, course_id)
        self.workers.append(worker)
        worker.progress_updated.connect(self._on_upload_progress)
        worker.batch_finished.connect(self._on_upload_finished)
        worker.batch_finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def _on_upload_progress(self, current, total, name):
        self.status_callback(f"正在上传学生 {current}/{total}: {name}")
        self.progress_dialog.setText(f"正在上传...\n进度: {current}/{total}\n当前学生: {name}")
        QApplication.processEvents()  # 强制处理事件循环，防止卡死

    def _on_upload_finished(self, success_count, fail_count, failed_students, success, message):
        # 关闭进度对话框
        self.progress_dialog.hide()
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        # 确保对话框被完全释放
        self.progress_dialog.deleteLater()

        if fail_count == 0:
            QMessageBox.information(self, "上传成功", message)
        elif success_count == 0:
            QMessageBox.critical(self, "上传失败", message)
        else:
            # 部分成功，显示失败列表
            failed_list_text = "\n".join([
                f"{i+1}. {s['name']} ({s['student_id']})\n   错误: {s['error']}"
                for i, s in enumerate(failed_students[:10])
            ])
            if len(failed_students) > 10:
                failed_list_text += f"\n... 还有 {len(failed_students) - 10} 名学生失败"

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("部分成功")
            msg_box.setText(message)
            msg_box.setDetailedText(failed_list_text)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.exec()

        self.status_callback(message)

    def _handle_clazz_rename(self, clazz_id, current_name):
        new_name, ok = QInputDialog.getText(self, "重命名班级", "请输入新的班级名称:", text=current_name)
        if ok and new_name and new_name != current_name:
            self.status_callback(f"正在重命名班级: {current_name} -> {new_name}")
            worker = RenameClazzWorker(self.crawler, clazz_id, new_name)
            self.workers.append(worker)
            worker.rename_finished.connect(lambda success, msg: self._on_clazz_action_finished(success, msg, "重命名"))
            worker.start()

    def _handle_clazz_delete(self, clazz_id, name):
        reply = QMessageBox.question(
            self, "确认归档", 
            f"确定要归档班级 '{name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback(f"正在归档班级: {name}")
            worker = DeleteClazzWorker(self.crawler, clazz_id)
            self.workers.append(worker)
            worker.delete_finished.connect(lambda success, msg: self._on_clazz_action_finished(success, msg, "归档"))
            worker.start()

    def _handle_new_class(self):
        params = self.crawler.session_manager.course_params
        course_id = params.get('courseid')
        if not course_id:
            QMessageBox.warning(self, "提示", "未找到课程ID，无法新建班级")
            return
        name, ok = QInputDialog.getText(self, "新建班级", "请输入班级名称:", text="新建班级")
        if not ok or not name.strip():
            return
        name = name.strip()
        self.status_callback(f"正在新建班级: {name}")
        success, msg = self.crawler.create_clazz(course_id, name)
        if success:
            QMessageBox.information(self, "成功", msg)
            self.on_class_management_clicked()  # 刷新列表
        else:
            QMessageBox.warning(self, "失败", msg)
        self.status_callback(msg)

    def _add_new_class_top_bar(self):
        # 用 widget 包一层，便于 clear_management_list 统一清理
        bar = QWidget()
        top_bar = QHBoxLayout(bar)
        top_bar.setContentsMargins(5, 0, 5, 0)
        top_bar.setSpacing(10)
        top_bar.addStretch()
        btn_new_class = QPushButton("➕ 新建班级")
        btn_new_class.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_class.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: 1px solid #007acc;
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
        """)
        btn_new_class.clicked.connect(self._handle_new_class)
        top_bar.addWidget(btn_new_class)
        self.management_scroll_layout.addWidget(bar)

    def _handle_clazz_distribute(self, clazz_id, name):
        """处理班级分配给教师的功能"""
        params = self.crawler.session_manager.course_params
        course_id = params.get('courseid')
        
        # 获取教师列表
        self.status_callback(f"正在获取教师列表...")
        teachers = self.crawler.get_teachers_for_clazz(course_id, clazz_id)
        
        if not teachers:
            QMessageBox.warning(self, "警告", "未能获取教师列表，请检查网络连接或课程参数。")
            return
        
        # 创建分配对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"分配班级 - {name}")
        dialog.setMinimumSize(600, 400)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #121212;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        
        # 标题
        title_label = QLabel(f"请选择要分配班级 '{name}' 的教师：")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #cccccc; padding: 10px;")
        layout.addWidget(title_label)
        
        # 教师列表
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("border: none; background-color: transparent;")
        
        teachers_container = QWidget()
        teachers_layout = QVBoxLayout(teachers_container)
        teachers_layout.setSpacing(10)
        teachers_layout.setContentsMargins(5, 5, 5, 5)
        teachers_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.teacher_checkboxes = {}
        for teacher in teachers:
            # 创建教师卡片
            card = QFrame()
            card.setObjectName("teacher_card")
            card.setStyleSheet("""
                QFrame#teacher_card {
                    background-color: #252526;
                    border: 1px solid #333333;
                    border-radius: 10px;
                    padding: 10px;
                }
                QFrame#teacher_card:hover {
                    border: 1px solid #007acc;
                    background-color: #2a2d2e;
                }
            """)
            
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(10)
            
            # 复选框
            checkbox = QCheckBox()
            checkbox.setChecked(teacher.get("selected", False))
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #cccccc;
                    font-size: 13px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
                QCheckBox::indicator:unchecked {
                    border: 2px solid #3e3e42;
                    background-color: #1e1e1e;
                    border-radius: 4px;
                }
                QCheckBox::indicator:checked {
                    border: 2px solid #007acc;
                    background-color: #007acc;
                    border-radius: 4px;
                }
            """)
            self.teacher_checkboxes[teacher["id"]] = checkbox
            
            # 教师信息
            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            info_layout.setContentsMargins(0, 0, 0, 0)
            
            name_label = QLabel(teacher['name'])
            name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
            
            details_label = QLabel(f"工号: {teacher['workId']}  角色: {teacher['role']}  机构: {teacher.get('organization', '')}")
            details_label.setStyleSheet("font-size: 13px; color: #888888;")
            
            info_layout.addWidget(name_label)
            info_layout.addWidget(details_label)
            
            card_layout.addWidget(checkbox)
            card_layout.addLayout(info_layout)
            card_layout.addStretch()
            
            teachers_layout.addWidget(card)
        
        # 吃掉滚动区域的多余高度，避免卡片被拉伸导致行间距看起来很大
        teachers_layout.addStretch(1)
        
        scroll_area.setWidget(teachers_container)
        layout.addWidget(scroll_area)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # 确定和取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: #cccccc;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4a4a5a;
                color: white;
            }
        """)
        
        confirm_btn = QPushButton("确定")
        confirm_btn.setFixedWidth(80)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(confirm_btn)
        layout.addLayout(button_layout)
        
        # 连接按钮信号
        cancel_btn.clicked.connect(dialog.reject)
        confirm_btn.clicked.connect(lambda: self._confirm_assign_teachers(dialog, clazz_id, name, course_id))
        
        # 显示对话框
        dialog_result = dialog.exec()
        
    
    def _confirm_assign_teachers(self, dialog, clazz_id, name, course_id):
        """确认将班级分配给选中的教师"""
        # 获取选中的教师ID
        selected_teacher_ids = [
            teacher_id for teacher_id, checkbox in self.teacher_checkboxes.items()
            if checkbox.isChecked()
        ]
        
        if not selected_teacher_ids:
            QMessageBox.warning(dialog, "提示", "请至少选择一名教师")
            return
        
        # 执行分配
        self.status_callback(f"正在分配班级给 {len(selected_teacher_ids)} 名教师...")
        success, message = self.crawler.assign_clazz_to_teachers(course_id, clazz_id, selected_teacher_ids)
        
        if success:
            QMessageBox.information(dialog, "成功", message)
            dialog.accept()
            self.on_class_management_clicked()  # 刷新班级列表
        else:
            QMessageBox.critical(dialog, "失败", f"分配失败: {message}")
        self.status_callback(message)

    def _on_clazz_action_finished(self, success, message, action_name):
        if success:
            QMessageBox.information(self, "操作成功", f"班级{action_name}成功！")
            self.on_class_management_clicked() # Refresh list
        else:
            QMessageBox.warning(self, "操作失败", f"班级{action_name}失败: {message}")
        self.status_callback(message)

    def on_grade_weight_clicked(self):
        self.last_manage_sub = "grade_weight"
        self.clear_management_list()
        
        loading_label = QLabel("正在从学习通同步权重数据，请稍候...")
        loading_label.setStyleSheet("color: #007acc; padding: 20px; font-size: 14px;")
        self.management_scroll_layout.addWidget(loading_label)
        
        worker = GetWeightWorker(self.crawler)
        self.workers.append(worker)
        worker.weights_ready.connect(self._setup_weight_ui)
        worker.weights_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        
        self.status_callback("正在同步权重数据...")

    def _setup_weight_ui(self, current_weights: dict):
        self.clear_management_list()
        self.grade_spinboxes = {}
        
        container = QFrame()
        container.setStyleSheet("background-color: #252526; border-radius: 8px; padding: 10px;")
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        items_config = [
            ("章节任务点", 20), ("章节测验", 10), ("作业", 20),
            ("考试", 30), ("AI实践", 5), ("分组任务(PBL)", 5),
            ("签到", 5), ("课程积分", 0), ("讨论", 5)
        ]
        
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(5, 5, 5, 5)
        grid_layout.setHorizontalSpacing(20)
        grid_layout.setVerticalSpacing(8)
        
        for i, (name, default_val) in enumerate(items_config):
            row = i // 3
            col = i % 3
            
            current_val = current_weights.get(name, default_val)
            
            item_widget = QWidget()
            item_hbox = QHBoxLayout(item_widget)
            item_hbox.setContentsMargins(0, 0, 0, 0)
            item_hbox.setSpacing(10)
            
            label = QLabel(name)
            label.setStyleSheet("color: #cccccc; font-size: 13px;")
            
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setValue(current_val)
            spin.setSuffix("%")
            spin.setFixedWidth(70)
            spin.setStyleSheet("""
                QSpinBox {
                    background-color: #3e3e42;
                    color: white;
                    border: 1px solid #333333;
                    padding: 2px 5px;
                    border-radius: 3px;
                }
                QSpinBox:hover { border: 1px solid #444444; }
                QSpinBox:focus { background-color: #45454a; border: 1px solid #007acc; }
            """)
            spin.valueChanged.connect(self.update_total_weight)
            self.grade_spinboxes[name] = spin
            
            item_hbox.addWidget(label)
            item_hbox.addStretch()
            item_hbox.addWidget(spin)
            
            grid_layout.addWidget(item_widget, row, col)
            
        layout.addLayout(grid_layout)
        
        # Bottom bar
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        
        self.total_label = QLabel("总计: 0%")
        self.total_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #ff4d4d;")
        
        self.sync_all_classes_cb = QCheckBox("同步至当前课程所有班级")
        self.sync_all_classes_cb.setStyleSheet("color: #007acc; font-size: 12px; margin-right: 15px;")
        
        self.save_weight_btn = QPushButton("保存权重")
        self.save_weight_btn.setFixedWidth(100)
        self.save_weight_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                padding: 6px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:disabled { background-color: #3e3e42; color: #888888; }
        """)
        self.save_weight_btn.clicked.connect(self.save_grade_weights)
        
        bottom_layout.addWidget(self.total_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.sync_all_classes_cb)
        bottom_layout.addWidget(self.save_weight_btn)
        layout.addLayout(bottom_layout)
        
        self.management_scroll_layout.addWidget(container)
        self.update_total_weight()
        self.status_callback("同步完成，已加载当前权重配置")

    def update_total_weight(self):
        total = sum(spin.value() for spin in self.grade_spinboxes.values())
        self.total_label.setText(f"当前总计: {total} %")
        
        if total == 100:
            self.total_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #4ec9b0;") # Green
            self.save_weight_btn.setEnabled(True)
        else:
            self.total_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff4d4d;") # Red
            self.save_weight_btn.setEnabled(False)

    def save_grade_weights(self):
        weights = {name: spin.value() for name, spin in self.grade_spinboxes.items()}
        
        class_ids = None
        if self.sync_all_classes_cb.isChecked():
            class_ids = self.get_classes_callback()
            if not class_ids:
                # Fallback
                params = self.crawler.session_manager.course_params
                if params and params.get("clazzid"):
                    class_ids = [str(params.get("clazzid"))]
        
        self.save_weight_btn.setEnabled(False)
        self.save_weight_btn.setText("正在保存...")
        sync_txt = " (全班级同步)" if class_ids else ""
        self.status_callback(f"正在提交权重设置{sync_txt}...")
        
        worker = WeightWorker(self.crawler, weights, class_ids)
        self.workers.append(worker)
        worker.weight_saved.connect(self.handle_weight_save_result)
        worker.weight_saved.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def handle_weight_save_result(self, success, message):
        self.save_weight_btn.setEnabled(True)
        self.save_weight_btn.setText("保存权重")
        
        if success:
            QMessageBox.information(self, "操作成功", message)
            self.status_callback("权重保存成功")
        else:
            QMessageBox.critical(self, "操作失败", message)
            self.status_callback(f"保存失败: {message}")

    def on_teacher_team_clicked(self):
        self.last_manage_sub = "teacher_team"
        self.clear_management_list()

        # 1. 顶部导航按钮
        nav_container = QWidget()
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setSpacing(10)
        nav_layout.setContentsMargins(0, 0, 0, 16)

        # 管理教师按钮
        self.btn_manage_teachers = QPushButton("管理教师")
        self.btn_manage_teachers.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_teachers.setCheckable(True)
        self.btn_manage_teachers.setChecked(True) # 默认选中
        self.btn_manage_teachers.clicked.connect(self._render_manage_teachers_view)

        # 添加教师按钮
        self.btn_add_teacher = QPushButton("添加教师")
        self.btn_add_teacher.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_teacher.setCheckable(True)
        self.btn_add_teacher.clicked.connect(self._render_add_teacher_view)

        # 样式 update helper
        self._update_nav_btn_styles()
        self.btn_manage_teachers.clicked.connect(self._update_nav_btn_styles)
        self.btn_add_teacher.clicked.connect(self._update_nav_btn_styles)

        nav_layout.addWidget(self.btn_manage_teachers)
        nav_layout.addWidget(self.btn_add_teacher)
        nav_layout.addStretch()

        self.management_scroll_layout.addWidget(nav_container)

        # 2. 内容区域容器
        self.teacher_content_container = QWidget()
        self.teacher_content_layout = QVBoxLayout(self.teacher_content_container)
        self.teacher_content_layout.setContentsMargins(0, 0, 0, 0)
        self.management_scroll_layout.addWidget(self.teacher_content_container)

        # 默认加载管理教师视图
        self._render_manage_teachers_view()

    def _update_nav_btn_styles(self):
        # 简单样式切换
        base_style = """
            QPushButton {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
            }
        """
        checked_style = """
            QPushButton {
                background-color: #007acc;
                color: white;
                border: 1px solid #007acc;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
            }
        """
        
        self.btn_manage_teachers.setStyleSheet(checked_style if self.btn_manage_teachers.isChecked() else base_style)
        self.btn_add_teacher.setStyleSheet(checked_style if self.btn_add_teacher.isChecked() else base_style)

        # 互斥选中
        if self.sender() == self.btn_manage_teachers:
            self.btn_add_teacher.setChecked(False)
        elif self.sender() == self.btn_add_teacher:
            self.btn_manage_teachers.setChecked(False)

    def _render_manage_teachers_view(self):
        # 清空内容区域
        self._clear_teacher_content()
        
        # 确保互斥状态正确（如果是直接调用而非点击）
        self.btn_manage_teachers.setChecked(True)
        self.btn_add_teacher.setChecked(False)
        self._update_nav_btn_styles()

        self.status_callback("正在加载教师列表...")

        # 教师列表容器
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)

        # 创建表格
        self.manage_teachers_table = QTableWidget()
        self.manage_teachers_table.setColumnCount(4)
        self.manage_teachers_table.setHorizontalHeaderLabels(["工号", "姓名", "院系", "角色"])
        self.manage_teachers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.manage_teachers_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.manage_teachers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.manage_teachers_table.setAlternatingRowColors(True)
        self.manage_teachers_table.verticalHeader().setVisible(False)
        self.manage_teachers_table.horizontalHeader().setVisible(True)
        self.manage_teachers_table.setStyleSheet(self._get_table_style())
        
        layout.addWidget(self.manage_teachers_table)
        self.teacher_content_layout.addWidget(container)

        # 底部操作按钮区域
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        action_layout.setContentsMargins(0, 10, 0, 0) # Top margin relative to the table

        self.btn_remove_teacher = QPushButton("移除教师")
        self.btn_remove_teacher.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_teacher.setEnabled(False)
        self.btn_remove_teacher.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c9302c; }
            QPushButton:disabled { background-color: #3e3e42; color: #888888; }
        """)
        
        self.btn_transfer_course = QPushButton("转让课程")
        self.btn_transfer_course.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_transfer_course.setEnabled(False)
        self.btn_transfer_course.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #3e3e42; color: #888888; }
        """)

        action_layout.addStretch()
        action_layout.addWidget(self.btn_remove_teacher)
        action_layout.addWidget(self.btn_transfer_course)

        self.teacher_content_layout.addLayout(action_layout)

        # 表格选择变化信号
        self.manage_teachers_table.itemSelectionChanged.connect(self._update_manage_buttons_state)
        
        # 按钮事件连接
        self.btn_remove_teacher.clicked.connect(self._remove_selected_teachers)

        # 加载数据
        params = self.crawler.session_manager.course_params
        c_id = params.get('courseId') or params.get('courseid')
        cl_id = params.get('classId') or params.get('clazzid') or params.get('clazzId')
        
        if c_id and cl_id:
            worker = GetTeachersWorker(self.crawler, c_id, cl_id)
            self.workers.append(worker)
            worker.teachers_ready.connect(self._on_manage_teachers_loaded)
            worker.teachers_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _update_manage_buttons_state(self):
        """更新管理按钮状态"""
        has_selection = len(self.manage_teachers_table.selectedItems()) > 0
        self.btn_remove_teacher.setEnabled(has_selection)
        self.btn_transfer_course.setEnabled(has_selection)

    def _render_add_teacher_view(self):
        # 清空内容区域
        self._clear_teacher_content()

        self.status_callback("请输入教师姓名进行搜索...")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 搜索区域
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        
        search_input = QLineEdit()
        search_input.setPlaceholderText("请输入教师姓名或工号")
        search_input.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3a3f44;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                min-width: 200px;
            }
            QLineEdit:focus { border: 1px solid #007acc; }
        """)
        
        search_btn = QPushButton("搜索")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #005c99; }
        """)
        
        search_layout.addWidget(search_input)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        
        layout.addWidget(search_widget)

        # 搜索结果表格
        self.teachers_table = QTableWidget() # 复用变量名以便回调复用
        self.teachers_table.setColumnCount(3)
        self.teachers_table.setHorizontalHeaderLabels(["工号", "姓名", "院系"])
        self.teachers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.teachers_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.teachers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.teachers_table.setAlternatingRowColors(True)
        self.teachers_table.verticalHeader().setVisible(False)
        self.teachers_table.horizontalHeader().setVisible(True)
        self.teachers_table.setStyleSheet(self._get_table_style())

        layout.addWidget(self.teachers_table)

        # 添加选中教师按钮
        self.btn_confirm_add = QPushButton("添加选中教师")
        self.btn_confirm_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirm_add.setEnabled(False)
        self.btn_confirm_add.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #005c99; }
            QPushButton:disabled { background-color: #3e3e42; color: #888888; }
        """)
        self.btn_confirm_add.clicked.connect(self._add_selected_teacher)
        layout.addWidget(self.btn_confirm_add)

        self.teacher_content_layout.addWidget(container)

        # 连接信号
        search_btn.clicked.connect(lambda: self._handle_search_teacher(search_input.text()))
        search_input.returnPressed.connect(lambda: self._handle_search_teacher(search_input.text()))
        
        # 表格选择变化信号
        self.teachers_table.itemSelectionChanged.connect(lambda: self.btn_confirm_add.setEnabled(len(self.teachers_table.selectedItems()) > 0))

    def _clear_teacher_content(self):
        # Remove all widgets from content layout
        while self.teacher_content_layout.count():
            item = self.teacher_content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _get_table_style(self):
        return """
            QTableWidget {
                background-color: transparent;
                border: none;
                gridline-color: #3e3e42;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 10px;
                border-bottom: 1px solid #3e3e42;
            }
            QTableWidget::item:selected {
                background-color: #202531;
                color: white;
                border: 1px solid #007acc;
            }
            QHeaderView {
                background-color: transparent;
                border: none;
            }
            QHeaderView::section {
                background-color: #252526;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #007acc;
                font-weight: bold;
                color: #cccccc;
                min-height: 35px;
            }
        """

    def _on_manage_teachers_loaded(self, success, message, teachers):
        self.manage_teachers_table.setRowCount(0)
        if not success:
            self.status_callback(message)
            return
            
        self.status_callback(f"加载成功，当前班级共有 {len(teachers)} 名教师")
        
        for teacher in teachers:
            self._add_teacher_to_table(teacher, self.manage_teachers_table)


    def _add_teacher_to_table(self, teacher, table_widget=None):
        if table_widget is None:
            table_widget = self.teachers_table
            
        row = table_widget.rowCount()
        table_widget.insertRow(row)
        
        # 工号
        work_id = str(teacher.get("workId") or teacher.get("job_number") or "")
        work_item = QTableWidgetItem(work_id)
        work_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        work_item.setData(Qt.ItemDataRole.UserRole, teacher) # Store data in first col (now WorkID)
        table_widget.setItem(row, 0, work_item)
        
        # 姓名
        name = teacher.get("name", "")
        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table_widget.setItem(row, 1, name_item)
        
        # 院系
        dept_name = teacher.get("dept") or teacher.get("department") or ""
        dept_item = QTableWidgetItem(dept_name)
        dept_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table_widget.setItem(row, 2, dept_item)
        
        # 角色 (如果表格有第4列)
        if table_widget.columnCount() > 3:
            role = teacher.get("role", "")
            role_item = QTableWidgetItem(role)
            role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table_widget.setItem(row, 3, role_item)

    def _handle_search_teacher(self, query_name: str):
        """处理教师搜索"""
        query_name = query_name.strip()
        if not query_name:
            QMessageBox.warning(self, "提示", "请输入教师姓名")
            return

        self.status_callback(f"正在搜索教师: {query_name}")
        self.teachers_table.setRowCount(0)

        # 暂时不需要显示loading row，直接用status_callback提示
        
        # 调用搜索接口
        result = self.crawler.search_teacher(query_name)

        # 打印调试信息
        print(f"DEBUG: 搜索结果 - success={result.get('success')}, teachers数量={len(result.get('teachers', []))}")
        
        if not result.get("success"):
            QMessageBox.warning(self, "搜索失败", result.get("error", "未知错误"))
            self.status_callback("搜索教师失败")
            return

        teachers = result.get("teachers", [])
        if not teachers:
            # Add a "no results" row
            self.teachers_table.insertRow(0)
            item = QTableWidgetItem("未找到匹配的教师")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # Span across all 3 columns
            self.teachers_table.setItem(0, 0, item)
            self.teachers_table.setSpan(0, 0, 1, 3)
            
            self.status_callback(f"未找到匹配的教师: {query_name}")
            return

        # 显示搜索结果
        for idx, teacher in enumerate(teachers):
            self._add_teacher_to_table(teacher, self.teachers_table)
        
        self.status_callback(f"搜索完成，共找到 {len(teachers)} 名教师")

    def _add_selected_teacher(self):
        """添加选中的教师到团队"""
        selected_rows = self.teachers_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # 获取选中行的数据
        teachers_to_add = []
        names = []
        for index in selected_rows:
            # 数据存储在第0列的UserRole
            item = self.teachers_table.item(index.row(), 0)
            if item:
                teacher_data = item.data(Qt.ItemDataRole.UserRole)
                if teacher_data:
                    # Construct the dict expected by crawler: {"personId": "...", "enc": "..."}
                    # Note: crawler search result keys are 'id' (for personId) and 'enc'
                    t_info = {
                        "personId": teacher_data.get("id"),
                        "enc": teacher_data.get("enc")
                    }
                    teachers_to_add.append(t_info)
                    names.append(teacher_data.get("name", "未知"))

        if not teachers_to_add:
            return

        # 确认对话框
        names_str = ", ".join(names)
        reply = QMessageBox.question(self, "确认添加", f"确定要将以下教师添加到教学团队吗？\n\n{names_str}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback("正在添加教师...")
            params = self.crawler.session_manager.course_params
            course_id = params.get('courseId') or params.get('courseid')
            
            worker = AddTeamTeacherWorker(self.crawler, course_id, teachers_to_add)
            self.workers.append(worker)
            worker.finished.connect(self._on_teacher_added)
            worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_teacher_added(self, success, message):
        if success:
            QMessageBox.information(self, "成功", message)
            self.status_callback(message)
            # 可选: 自动切回管理视图并刷新? 或者留在当前页
            # self._render_manage_teachers_view() 
        else:
            QMessageBox.warning(self, "失败", message)
            self.status_callback(f"添加失败: {message}")

    def _remove_selected_teachers(self):
        """移除选中的教师"""
        selected_rows = self.manage_teachers_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # 获取选中行的数据 (personId)
        ids_to_remove = []
        names = []
        for index in selected_rows:
            # 数据存储在第0列的UserRole
            item = self.manage_teachers_table.item(index.row(), 0)
            if item:
                teacher_data = item.data(Qt.ItemDataRole.UserRole)
                if teacher_data:
                    # 获取ID，这里可能是 id 或 personId
                    tid = teacher_data.get("id") or teacher_data.get("personId")
                    if tid:
                        ids_to_remove.append(str(tid))
                        names.append(teacher_data.get("name", "未知"))

        if not ids_to_remove:
            return

        # 确认对话框
        names_str = ", ".join(names)
        confirm_msg = f"确定要从教学团队中移除以下教师吗？\n\n{names_str}\n\n移除后，该教师将无法再访问本课程。"
        reply = QMessageBox.question(self, "确认移除", confirm_msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback("正在移除教师...")
            params = self.crawler.session_manager.course_params
            course_id = params.get('courseId') or params.get('courseid')
            
            worker = RemoveTeamTeacherWorker(self.crawler, course_id, ids_to_remove)
            self.workers.append(worker)
            worker.finished.connect(self._on_teacher_removed)
            worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_teacher_removed(self, success, message):
        if success:
            QMessageBox.information(self, "成功", message)
            self.status_callback(message)
            # 刷新列表
            self._render_manage_teachers_view()
        else:
            QMessageBox.warning(self, "失败", message)
            self.status_callback(f"移除失败: {message}")

    def on_course_management_clicked(self):
        self.last_manage_sub = "course_management"
        self.clear_management_list()
        self._render_course_management_view()
        self.status_callback("课程管理界面已加载（界面示例，暂未接入接口）")

    def _render_course_management_view(self):
        # 先清空界面，避免重复内容
        self.clear_management_list()
        
        # 1. 顶部操作区（在卡片外部）
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 10)
        top_bar.addStretch()

        btn_new_course = QPushButton("➕ 新建课程")
        btn_new_course.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new_course.setFixedWidth(110)
        btn_new_course.setFixedHeight(34)
        btn_new_course.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: 1px solid #007acc;
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                min-width: 110px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
            """
        )
        btn_new_course.clicked.connect(self._open_new_course_dialog)
        top_bar.addWidget(btn_new_course)

        btn_clone_course = QPushButton("📂 克隆课程")
        btn_clone_course.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clone_course.setFixedWidth(110)
        btn_clone_course.setFixedHeight(34)
        btn_clone_course.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: 1px solid #007acc;
                padding: 6px 10px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                min-width: 110px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
            """
        )
        btn_clone_course.clicked.connect(self._handle_clone_course)
        top_bar.addWidget(btn_clone_course)
        self.management_scroll_layout.addLayout(top_bar)

        # 2. 课程信息区（卡片式）
        container = QFrame()
        container.setStyleSheet("background-color: #1e1f22; border-radius: 10px; padding: 16px;")
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 12)

        sample_data = {
            "id": self.crawler.session_manager.course_params.get("courseid", "示例ID"),
            "courseid": self.crawler.session_manager.course_params.get("courseid"),
            "cpi": self.crawler.session_manager.course_params.get("cpi"),
            "name": self.crawler.session_manager.course_params.get("name", "未知课程"),
            "english": "",
            "teacher": self.crawler.session_manager.course_params.get("teacher", "教师姓名"),
            "unit": "郑州西亚斯学院 (4311)",
            "dept": "校团委",
            "category": "无",
            "desc": "课程说明示例：在此填写教学目标、考核方式等。",
            "cover_url": self.crawler.session_manager.course_params.get("cover") or "https://p.ananas.chaoxing.com/star3/origin/669ca80d6a0c5f74835bb936a41aabca.jpg"
        }

        title_text = f"当前课程：📖 {sample_data['name']}"
        form_widget = self._create_course_form_widget(sample_data, readonly=True, title=title_text)
        layout.addWidget(form_widget)

        self.management_scroll_layout.addWidget(container)

    def _open_new_course_dialog(self):
        """弹出新建课程对话框 (直接打开，不进行服务器同步)。"""
        self._open_course_info_dialog(title="新建课程", is_edit=False)

    def _open_basic_info_dialog(self, data: dict):
        """弹出课程基本信息对话框 (异步获取数据)。"""
        self._start_course_info_fetch(title="课程基本信息", initial_data=data, is_edit=True)

    def _start_course_info_fetch(self, title, initial_data=None, is_edit=False):
        """显示加载提示并启动异步获取全量数据工作线程。"""
        loading = QMessageBox(self)
        loading.setWindowTitle("请稍候")
        loading.setText("正在同步服务器课程数据...")
        loading.setStandardButtons(QMessageBox.StandardButton.NoButton)
        loading.setWindowModality(Qt.WindowModality.ApplicationModal)
        loading.show()

        worker = FullCourseInfoWorker(self.crawler, is_edit=is_edit, initial_data=initial_data)
        self.workers.append(worker)
        worker.finished.connect(lambda res: self._on_course_info_ready(res, loading, title, is_edit))
        worker.start()

    def _on_course_info_ready(self, result, loading_dialog, title, is_edit):
        """数据拉取完成后的回调，关闭加载框并弹出真正的 UI 对话框。"""
        if loading_dialog:
            loading_dialog.hide()
            loading_dialog.deleteLater()

        if not result.get("success"):
            QMessageBox.warning(self, "错误", f"获取课程数据失败: {result.get('error', '未知错误')}")
            return

        # 弹出实际的对话框
        self._open_course_info_dialog(
            title=title, 
            initial_data=result.get("initial_data"), 
            is_edit=is_edit,
            prefetched_data=result
        )

    def _open_course_info_dialog(self, title: str, initial_data: dict = None, is_edit: bool = False, prefetched_data: dict = None):
        """弹出课程信息对话框，使用预取的数据填充 UI。"""
        if not prefetched_data:
            # 兜底：如果是新建课程或者预取未通过，则同步获取必要的基础数据（单位列表等）
            print(f"DEBUG: _open_course_info_dialog using synchronous fallback (is_edit={is_edit})")
            creation_data = self.crawler.get_course_creation_data()
        else:
            creation_data = prefetched_data.get("creation_data", {})

        print(f"DEBUG: _open_course_info_dialog buildup. is_edit={is_edit}, prefetched={prefetched_data is not None}")
        
        # 定义需要提取的字段，确保在所有路径下都已定义
        fetched_name = ""
        fetched_english = ""
        fetched_teacher = ""
        fetched_unit = ""
        fetched_unit_id = ""
        fetched_dept = ""
        fetched_dept_id = ""
        fetched_category = ""
        fetched_desc = ""
        
        if initial_data:
            fetched_name = initial_data.get("name", "")
            fetched_english = initial_data.get("english", "")
            fetched_teacher = initial_data.get("teacher", "")
            fetched_unit = initial_data.get("unit", "")
            fetched_unit_id = initial_data.get("unit_id", "")
            fetched_dept = initial_data.get("dept", "")
            fetched_dept_id = initial_data.get("dept_id", "")
            fetched_category = initial_data.get("category", "")
            fetched_desc = initial_data.get("desc", "")

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(600, 900)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #121212;
            }
        """)

        # 存储完整的单位信息（包括data和fid）到对话框对象中，供后续使用
        dialog.units_data = {}  # 映射：显示名称 -> {"name": "...", "data": "...", "fid": "..."}
        dialog.groups_data = {}  # 映射：显示名称 -> {"name": "...", "data": "..."}
        dialog.semesters_data = {}  # 映射：显示名称 -> {"name": "...", "data": "..."}

        # 如果有从服务器获取的 ID，预填到 data 中
        if is_edit and initial_data:
            if initial_data.get("unit") and initial_data.get("unit_id"):
                dialog.units_data[initial_data["unit"]] = {
                    "name": initial_data["unit"],
                    "fid": initial_data["unit_id"],
                    "data": ""
                }
            if initial_data.get("dept") and initial_data.get("dept_id"):
                dialog.groups_data[initial_data["dept"]] = {
                    "name": initial_data["dept"],
                    "data": initial_data["dept_id"]
                }

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # 课程封面区域
        cover_box = QFrame()
        cover_box.setStyleSheet("background-color: #1e1e1e; border: 1px dashed #3a3f44; border-radius: 10px; padding: 16px;")
        cover_box.setMinimumHeight(100)
        cover_layout = QHBoxLayout(cover_box)
        cover_layout.setContentsMargins(16, 16, 16, 16)
        cover_layout.setSpacing(16)

        # 封面图片标签
        cover_label = QLabel()
        cover_label.setFixedSize(320, 180)  # 16:9 比例
        cover_label.setStyleSheet("""
            QLabel {
                background-color: #2a2d2e;
                border-radius: 8px;
            }
        """)
        cover_label.setScaledContents(False)
        cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 封面图片
        default_cover = "https://p.ananas.chaoxing.com/star3/origin/669ca80d6a0c5f74835bb936a41aabca.jpg"
        cover_url = initial_data.get("cover_url", default_cover) if initial_data else default_cover
        self._load_cover_image(cover_label, cover_url)

        cover_btn = QPushButton("📷 上传封面")
        cover_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cover_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2f33;
                color: #80bfff;
                border: 1px solid #3d434a;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
        """)
        # 获取编辑模式的参数
        course_id = initial_data.get("courseid") or initial_data.get("courseId") if is_edit else ""
        cpi = initial_data.get("cpi") if is_edit else ""
        cover_btn.clicked.connect(lambda: self._handle_upload_cover(dialog, cover_label, is_edit, course_id, cpi))

        ai_cover_btn = QPushButton("✨ AI生成封面")
        ai_cover_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_cover_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2f33;
                color: #ff9f43;
                border: 1px solid #3d434a;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #ff9f43;
                color: white;
            }
        """)
        
        # 记下 cover_label 以便加载完成时重新缩放
        cover_label._target_size = (320, 180)

        # 表单区域
        form_container = QFrame()
        form_container.setStyleSheet("background-color: #1e1e1e; border-radius: 10px; padding: 16px;")
        form_layout = QGridLayout(form_container)
        form_layout.setHorizontalSpacing(20)
        form_layout.setVerticalSpacing(14)
        form_layout.setContentsMargins(8, 8, 8, 8)

        # 样式定义
        line_style = """
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3a3f44;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
        """
        combo_style = """
            QComboBox {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3a3f44;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                width: 26px;
                border-left: 1px solid #3a3f44;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e1e;
                border: 1px solid #3a3f44;
                selection-background-color: #007acc;
            }
        """
        label_style = "color: #bfc7d5; font-size: 13px;"

        # 课程名称
        name_label = QLabel("课程名称 *")
        name_label.setStyleSheet(label_style)
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("请输入课程名称")
        name_edit.setStyleSheet(line_style)
        if fetched_name:
            name_edit.setText(fetched_name)

        # 课程英文名称
        english_name_label = QLabel("课程英文名称")
        english_name_label.setStyleSheet(label_style)
        english_name_edit = QLineEdit()
        english_name_edit.setPlaceholderText("请输入课程英文名称")
        english_name_edit.setStyleSheet(line_style)
        if fetched_english:
            english_name_edit.setText(fetched_english)

        # 课程教师
        teacher_label = QLabel("课程教师 *")
        teacher_label.setStyleSheet(label_style)
        teacher_edit = QLineEdit()
        teacher_edit.setPlaceholderText("请输入课程教师")
        teacher_edit.setStyleSheet(line_style)

        # 连接AI生成封面按钮
        # 获取编辑模式的参数（与cover_btn使用相同的参数）
        ai_cover_btn.clicked.connect(lambda: self._handle_ai_generate_cover(dialog, cover_label, name_edit, ai_cover_btn, cover_btn, is_edit, course_id, cpi))

        cover_layout.addWidget(cover_label)
        cover_layout.addStretch()
        cover_layout.addWidget(cover_btn)
        cover_layout.addWidget(ai_cover_btn)

        # 填充教师姓名逻辑：优先使用 initial_data 中的教师名，但如果是“未知教师”或为空，则跟新建课程一样尝试从 API 或 session 获取
        teacher_name = fetched_teacher.strip()
        if teacher_name in ["未知教师", "教师姓名"]:
            teacher_name = ""

        if not teacher_name:
            if creation_data.get("success"):
                teacher_name = creation_data.get("teacher", "").strip()
            
            if not teacher_name:
                teacher_name = self.crawler.session_manager.course_params.get("teacher", "").strip()

        teacher_edit.setText(teacher_name)

        # 所属单位
        unit_label = QLabel("所属单位 *")
        unit_label.setStyleSheet(label_style)
        unit_combo = QComboBox()
        unit_combo.setStyleSheet(combo_style)

        if creation_data.get("success") and creation_data.get("units"):
            units_list = creation_data["units"]
            unit_display_names = []
            for unit_info in units_list:
                unit_display_names.append(unit_info["name"])
                dialog.units_data[unit_info["name"]] = unit_info
            
            # 如果 initial_data 中有单位，尝试匹配现有列表
            fetched_unit = fetched_unit.strip()
            matched_unit = None
            
            if fetched_unit:
                # 1. 优先尝试前缀匹配 (例如 "郑州西亚斯学院" 匹配 "郑州西亚斯学院 (4311)")
                for name in unit_display_names:
                    if name.startswith(fetched_unit) or fetched_unit.startswith(name):
                        matched_unit = name
                        break
                
                # 2. 如果没匹配到，则添加新选项
                if not matched_unit:
                    unit_display_names.insert(0, fetched_unit)
                    matched_unit = fetched_unit
                    if fetched_unit not in dialog.units_data:
                        dialog.units_data[fetched_unit] = {
                            "name": fetched_unit,
                            "fid": initial_data.get("unit_id", ""),
                            "data": ""
                        }

            unit_combo.addItems(unit_display_names)

            # 设置初始值（在绑定事件前设置，避免触发刷新）
            if matched_unit:
                unit_combo.setCurrentText(matched_unit)
            elif "郑州西亚斯学院 (4311)" in unit_display_names:
                unit_combo.setCurrentText("郑州西亚斯学院 (4311)")
            elif unit_display_names:
                unit_combo.setCurrentIndex(0)
        else:
            default_units = ["郑州西亚斯学院 (4311)", "郑州西亚斯学院", "其他单位"]
            fetched_unit = fetched_unit.strip()
            matched_unit = None
            
            if fetched_unit:
                for name in default_units:
                    if name.startswith(fetched_unit) or fetched_unit.startswith(name):
                        matched_unit = name
                        break
                
                if not matched_unit:
                    default_units.insert(0, fetched_unit)
                    matched_unit = fetched_unit
                    if fetched_unit not in dialog.units_data:
                        dialog.units_data[fetched_unit] = {
                            "name": fetched_unit,
                            "fid": initial_data.get("unit_id", ""),
                            "data": ""
                        }
            
            unit_combo.addItems(default_units)
            if matched_unit:
                unit_combo.setCurrentText(matched_unit)
            else:
                unit_combo.setCurrentText("郑州西亚斯学院 (4311)")
        unit_combo.setEditable(True)

        # 获取默认选中的单位的fid和data，用于获取院系列表
        default_unit_name = unit_combo.currentText()
        default_unit_info = dialog.units_data.get(default_unit_name, {})
        default_unit_fid = default_unit_info.get("fid", "")
        default_unit_cpi = default_unit_info.get("data", "")  # cpi 就是单位的 data 值

        # 所属院系（先创建占位，后面填充数据）
        dept_label = QLabel("所属院系 *")
        dept_label.setStyleSheet(label_style)
        dept_combo = QComboBox()
        dept_combo.setStyleSheet(combo_style)

        # 添加单位切换事件：自动刷新院系列表（在dept_combo创建后定义）
        def on_unit_changed(text):
            """切换单位时刷新院系列表"""
            unit_info = dialog.units_data.get(text, {})
            new_fid = unit_info.get("fid", "")
            new_cpi = unit_info.get("data", "")
            if new_fid and new_cpi:
                print(f"DEBUG: 单位切换为 {text}, fid={new_fid}, cpi={new_cpi}, 刷新院系列表...")
                groups_data = self.crawler.get_group_list(new_fid, new_cpi, "0")
                if groups_data and groups_data.get("success") and groups_data.get("groups"):
                    groups_list = groups_data["groups"]
                    dept_combo.clear()
                    group_names = [g["name"] for g in groups_list]
                    dept_combo.addItems(group_names)
                    # 更新 dialog.groups_data
                    dialog.groups_data.clear()
                    for group_info in groups_list:
                        dialog.groups_data[group_info["name"]] = group_info
                    # 默认选中第一个
                    if group_names:
                        dept_combo.setCurrentIndex(0)
                    print(f"DEBUG: 院系列表已刷新，共 {len(group_names)} 个院系")
                else:
                    print(f"DEBUG: 刷新院系列表失败: {groups_data.get('error', '未知错误')}")

        # 绑定单位切换事件（在设置初始值前绑定）
        unit_combo.currentTextChanged.connect(on_unit_changed)

        # 院系列表填充：使用预取的数据
        groups_data = prefetched_data.get("groups_data", {}) if prefetched_data else None
        
        if default_unit_fid:
            if not groups_data:
                # 兜底：如果预取失败，尝试同步获取一次（不推荐但为了健壮性）
                groups_data = self.crawler.get_group_list(default_unit_fid, default_unit_cpi, "0")
            
            if groups_data and groups_data.get("success") and groups_data.get("groups"):
                groups_list = groups_data["groups"]
                group_display_names = []
                for group_info in groups_list:
                    group_display_names.append(group_info["name"])
                    dialog.groups_data[group_info["name"]] = group_info
                
                if fetched_dept and fetched_dept not in group_display_names:
                    group_display_names.insert(0, fetched_dept)
                    if fetched_dept not in dialog.groups_data:
                        dialog.groups_data[fetched_dept] = {
                            "name": fetched_dept,
                            "data": initial_data.get("dept_id", "")
                        }
                
                dept_combo.addItems(group_display_names)
                if fetched_dept:
                    dept_combo.setCurrentText(fetched_dept)
                else:
                    dept_combo.setCurrentText("工学部")
            else:
                default_groups = ["校团委", "教务处", "工学部", "信息工程学院", "商学院", "体育学院", "文理学院", "其他院系"]
                if fetched_dept and fetched_dept not in default_groups:
                    default_groups.insert(0, fetched_dept)
                    if fetched_dept not in dialog.groups_data:
                        dialog.groups_data[fetched_dept] = {
                            "name": fetched_dept,
                            "data": initial_data.get("dept_id", "")
                        }
                dept_combo.addItems(default_groups)
                if fetched_dept:
                    dept_combo.setCurrentText(fetched_dept)
                else:
                    dept_combo.setCurrentText("工学部")
        else:
            default_groups = ["校团委", "教务处", "工学部", "信息工程学院", "商学院", "体育学院", "文理学院", "其他院系"]
            if fetched_dept and fetched_dept not in default_groups:
                default_groups.insert(0, fetched_dept)
                if fetched_dept not in dialog.groups_data:
                    dialog.groups_data[fetched_dept] = {
                        "name": fetched_dept,
                        "data": initial_data.get("dept_id", "")
                    }
            dept_combo.addItems(default_groups)
            if fetched_dept:
                dept_combo.setCurrentText(fetched_dept)
            else:
                dept_combo.setCurrentText("工学部")
        dept_combo.setEditable(True)

        # 获取课程分类 (调用新接口)
        category_label = QLabel("课程分类 *")
        category_label.setStyleSheet(label_style)
        category_combo = QComboBox()
        category_combo.setStyleSheet(combo_style)

        # 获取 courseId 和 cpi 用于分类接口
        params = self.crawler.session_manager.course_params or {}
        course_id = params.get("courseid") or params.get("courseId") or "0"
        cpi = params.get("cpi", "")

        if default_unit_fid:
            # 分类列表填充：使用预取的数据
            categories_data = prefetched_data.get("categories_data", {}) if prefetched_data else None
            if not categories_data or not categories_data.get("success"):
                # 兜底
                print(f"DEBUG: UI buildup fallback - fetching categories synchronously")
                categories_data = self.crawler.get_course_category_list(course_id, default_unit_fid, cpi)
            
            if categories_data.get("success") and categories_data.get("categories"):
                cat_list = categories_data["categories"]
                default_cat_from_api = categories_data.get("default_category", "")
                
                category_display_names = []
                for info in cat_list:
                    category_display_names.append(info["name"])
                    # 重用 semesters_data 结构存储分类ID
                    dialog.semesters_data[info["name"]] = {"name": info["name"], "data": info["id"]}
                category_combo.addItems(category_display_names)
                
                # 优先级：1. API返回的默认分类 (最高准确度) 2. 初始数据中的分类 3. "本校课程" 4. "无"
                if default_cat_from_api and default_cat_from_api != "无" and default_cat_from_api in category_display_names:
                    category_combo.setCurrentText(default_cat_from_api)
                    print(f"DEBUG: 使用API默认分类: {default_cat_from_api}")
                elif fetched_category and fetched_category != "无" and fetched_category in category_display_names:
                    category_combo.setCurrentText(fetched_category)
                    print(f"DEBUG: 使用初始数据分类: {fetched_category}")
                elif "本校课程" in category_display_names:
                    category_combo.setCurrentText("本校课程")
                elif "无" in category_display_names:
                    category_combo.setCurrentText("无")
            else:
                print(f"DEBUG 分类接口失败，使用备用列表")
                categories = ["尔雅通识课", "本校课程", "形式与政策", "无", "其他分类"]
                category_combo.addItems(categories)
                for c_name in categories:
                    dialog.semesters_data[c_name] = {"name": c_name, "data": ""}
                cat_val = initial_data.get("category")
                if cat_val and cat_val != "无":
                    category_combo.setCurrentText(cat_val)
                else:
                    category_combo.setCurrentText("本校课程")
        else:
            categories = ["尔雅通识课", "本校课程", "形式与政策", "无", "其他分类"]
            category_combo.addItems(categories)
            for c_name in categories:
                dialog.semesters_data[c_name] = {"name": c_name, "data": ""}
            cat_val = initial_data.get("category")
            if cat_val and cat_val != "无":
                category_combo.setCurrentText(cat_val)
            else:
                category_combo.setCurrentText("本校课程")

        # 选择学期 (仅在新建课程界面显示)
        semester_label = None
        semester_combo = None
        if not is_edit:
            semester_label = QLabel("选择学期 *")
            semester_label.setStyleSheet(label_style)
            semester_combo = QComboBox()
            semester_combo.setStyleSheet(combo_style)
            
            # 存储实际学期数据
            dialog.actual_semesters_data = {} 
            
            sem_data = prefetched_data.get("semesters_data", {}) if prefetched_data else None
            if not sem_data or not sem_data.get("success"):
                 sem_data = self.crawler.get_semester_list(default_unit_fid, "0")
            
            if sem_data.get("success") and sem_data.get("semesters"):
                sem_list = sem_data["semesters"]
                sem_display_names = []
                for s_info in sem_list:
                    sem_display_names.append(s_info["name"])
                    dialog.actual_semesters_data[s_info["name"]] = s_info
                semester_combo.addItems(sem_display_names)
                if sem_display_names:
                    semester_combo.setCurrentIndex(0)
            else:
                 fallback_sems = ["2025-2026学年 第一学期", "2024-2025学年 第二学期"]
                 semester_combo.addItems(fallback_sems)
                 for s_name in fallback_sems:
                     dialog.actual_semesters_data[s_name] = {"name": s_name, "data": ""}

        # 课程说明 (仅在编辑模式显示)
        desc_label = None
        desc_edit = None
        if is_edit:
            desc_label = QLabel("课程说明")
            desc_label.setStyleSheet(label_style)
            desc_edit = QTextEdit()
            desc_edit.setPlaceholderText("请输入课程说明...")
            desc_edit.setFixedHeight(80)
            desc_edit.setStyleSheet("""
                QTextEdit {
                    background-color: #252526;
                    color: #ffffff;
                    border: 1px solid #3a3f44;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QTextEdit:focus {
                    border: 1px solid #007acc;
                }
            """)
            if fetched_desc:
                desc_edit.setText(fetched_desc)

        # 添加到表单布局
        form_layout.addWidget(name_label, 0, 0)
        form_layout.addWidget(name_edit, 0, 1)

        if is_edit:
            form_layout.addWidget(english_name_label, 1, 0)
            form_layout.addWidget(english_name_edit, 1, 1)

        form_layout.addWidget(teacher_label, 2, 0)
        form_layout.addWidget(teacher_edit, 2, 1)

        form_layout.addWidget(unit_label, 3, 0)
        form_layout.addWidget(unit_combo, 3, 1)

        form_layout.addWidget(dept_label, 4, 0)
        form_layout.addWidget(dept_combo, 4, 1)

        if not is_edit and semester_label and semester_combo:
            form_layout.addWidget(semester_label, 5, 0)
            form_layout.addWidget(semester_combo, 5, 1)

        if is_edit:
            form_layout.addWidget(category_label, 5, 0)
            form_layout.addWidget(category_combo, 5, 1)

        if is_edit and desc_label and desc_edit:
            form_layout.addWidget(desc_label, 6, 0)
            form_layout.addWidget(desc_edit, 6, 1)

        # 底部按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(90)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3f44;
                color: #d1d5db;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4a4f55;
            }
        """)

        save_btn_text = "保存修改" if is_edit else "创建课程"
        save_btn = QPushButton(save_btn_text)
        save_btn.setFixedWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 22px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)

        # 连接信号
        cancel_btn.clicked.connect(dialog.reject)
        
        if is_edit:
            save_btn.clicked.connect(lambda: self._handle_edit_course_save(
                dialog, initial_data, name_edit, teacher_edit, english_name_edit, unit_combo, dept_combo, category_combo, desc_edit
            ))
        else:
            save_btn.clicked.connect(lambda: self._handle_new_course_save(
                dialog, name_edit, teacher_edit, unit_combo, dept_combo, category_combo, cover_label, semester_combo
            ))

        # 添加到主布局
        layout.addWidget(cover_box)
        layout.addWidget(form_container)
        layout.addStretch()
        layout.addLayout(button_layout)

        # 使用QTimer延迟加载图片
        def load_cover_after_show():
            target_url = initial_data.get("cover_url", default_cover) if initial_data else default_cover
            cover_label._last_url = target_url
            self._load_cover_image(cover_label, target_url)

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(load_cover_after_show)
        timer.start(100)

        # 显示对话框
        dialog.exec()

    def _handle_new_course_save(self, dialog, name_edit, teacher_edit, unit_combo, dept_combo, category_combo, cover_label, semester_combo=None):
        """处理新建课程的保存操作，调用接口创建课程。"""
        name = name_edit.text().strip()
        teacher = teacher_edit.text().strip()
        unit_name = unit_combo.currentText().strip()
        dept_name = dept_combo.currentText().strip()
        category_name = category_combo.currentText().strip()
        semester_name = semester_combo.currentText().strip() if semester_combo else ""
        cover_url = getattr(cover_label, "_last_url", "https://p.ananas.chaoxing.com/star3/origin/669ca80d6a0c5f74835bb936a41aabca.jpg")

        # 1. 课程分类ID
        category_info = dialog.semesters_data.get(category_name, {"name": category_name, "data": "33219"})
        category_id = category_info.get("data") or "33219"

        # 2. 学期ID (优先从 actual_semesters_data 获取)
        semester_id = "0"
        if hasattr(dialog, "actual_semesters_data") and semester_name in dialog.actual_semesters_data:
            semester_id = dialog.actual_semesters_data[semester_name].get("data") or "0"

        # 3. 院系ID (从 dialog.groups_data 获取)
        dept_id = ""
        if hasattr(dialog, "groups_data") and dept_name in dialog.groups_data:
            dept_id = dialog.groups_data[dept_name].get("data", "")
            print(f"DEBUG: 获取到院系ID - 名称: {dept_name}, ID: {dept_id}")

        # 4. 单位ID (从 dialog.units_data 获取data属性，作为personId提交)
        unit_person_id = ""
        if hasattr(dialog, "units_data") and unit_name in dialog.units_data:
            unit_person_id = dialog.units_data[unit_name].get("data", "")
            print(f"DEBUG: 获取到单位ID - 名称: {unit_name}, data={unit_person_id}")

        if not name:
            QMessageBox.warning(dialog, "验证失败", "请输入课程名称")
            return
        if not teacher:
            QMessageBox.warning(dialog, "验证失败", "请输入课程教师")
            return
        if not unit_name:
            QMessageBox.warning(dialog, "验证失败", "请选择或输入所属单位")
            return
        if not dept_name:
            QMessageBox.warning(dialog, "验证失败", "请选择或输入所属院系")
            return
        if not category_name and category_combo.isVisible():
            QMessageBox.warning(dialog, "验证失败", "请选择分类")
            return
        if not semester_name and semester_combo and semester_combo.isVisible():
            QMessageBox.warning(dialog, "验证失败", "请选择学期")
            return

        payload = {
            "name": name,
            "teacher": teacher,
            "cover_url": cover_url,
            "semester_name": semester_name or category_name,
            "semester_id": semester_id or category_id,
            "course_type": "0",
            "catalog_id": "0",
            "semester_type": "0",
            "unit_id": dept_id,  # 院系ID (groupId)
            "unit_person_id": unit_person_id,  # 单位ID (作为personId提交)
        }
        self.status_callback(f"正在创建课程: {name}")
        worker = CreateCourseWorker(self.crawler, payload)
        self.workers.append(worker)
        worker.course_created.connect(lambda success, msg: self._on_course_created(dialog, success, msg))
        worker.course_created.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        dialog.setEnabled(False)

    def _on_course_created(self, dialog, success: bool, message: str):
        """创建课程完成后的回调，展示提示并刷新界面。"""
        # 重新启用对话框
        dialog.setEnabled(True)

        if success:
            info = message or "课程创建成功"
            QMessageBox.information(dialog, "创建成功", info)
            try:
                dialog.accept()
            except Exception:
                dialog.close()

            # 刷新课程列表（保持当前导航项）
            self._refresh_course_dropdown(preserve_nav=True)
            # 刷新课程管理视图
            self._render_course_management_view()
            self.status_callback(info)
        else:
            err = message or "创建课程失败，请稍后重试"
            QMessageBox.warning(dialog, "创建失败", err)
            self.status_callback(err)

    def _handle_edit_course_save(self, dialog, initial_data, name_edit, teacher_edit, english_name_edit, unit_combo, dept_combo, category_combo, desc_edit=None):
        """处理课程基本信息的修改保存。"""
        name = name_edit.text().strip()
        teacher = teacher_edit.text().strip()
        english_name = english_name_edit.text().strip() if english_name_edit else ""  # 获取英文名称
        unit_name = unit_combo.currentText().strip()
        dept_name = dept_combo.currentText().strip()
        category_name = category_combo.currentText().strip()
        description = desc_edit.toPlainText().strip() if desc_edit else ""

        if not name:
            QMessageBox.warning(dialog, "验证失败", "请输入课程名称")
            return
        if not teacher:
            QMessageBox.warning(dialog, "验证失败", "请输入课程教师")
            return

        # 1. 尝试从 groups_data 获取真实的院系ID (dept_id)
        dept_id = ""
        if hasattr(dialog, "groups_data") and dept_name in dialog.groups_data:
            dept_id = dialog.groups_data[dept_name].get("data") or ""
        
        # 如果没找到，尝试使用 initial_data 里的兜底
        if not dept_id:
            dept_id = initial_data.get("dept_id", "")

        # 2. 尝试获取单位的 fid
        unit_fid = ""
        if hasattr(dialog, "units_data") and unit_name in dialog.units_data:
            unit_fid = dialog.units_data[unit_name].get("fid", "")
        
        if not unit_fid:
            unit_fid = initial_data.get("unit_id", "4311")

        # 3. 尝试获取课程分类ID (subject_id)
        subject_id = ""
        print(f"DEBUG: Saving course. Category name selected: '{category_name}'")
        if hasattr(dialog, "semesters_data"):
            # print(f"DEBUG: dialog.semesters_data keys: {list(dialog.semesters_data.keys())}")
            if category_name in dialog.semesters_data:
                subject_id = dialog.semesters_data[category_name].get("data") or ""
        
        print(f"DEBUG: Resolved subject_id: '{subject_id}'")

        payload = {
            "courseid": initial_data.get("courseid") or initial_data.get("courseId"),
            "cpi": initial_data.get("cpi"),
            "name": name,
            "teacher": teacher,
            "english_name": english_name,  # 添加英文名称
            "unit_id": dept_id,  # 接口中的 group1 对应院系ID
            "unit_fid": unit_fid,
            "subject_id": subject_id,
            "description": description
        }
        print(f"DEBUG: Update Course Payload: {payload}")

        if not payload["courseid"] or not payload["cpi"]:
             QMessageBox.critical(dialog, "错误", "缺失关键参数 (courseid/cpi)，无法保存修改")
             return

        self.status_callback(f"正在保存修改: {name}")
        worker = UpdateCourseDataWorker(self.crawler, payload)
        self.workers.append(worker)
        worker.course_updated.connect(lambda success, msg: self._on_course_updated(dialog, success, msg))
        worker.course_updated.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        dialog.setEnabled(False)

    def _on_course_updated(self, dialog, success: bool, message: str):
        """课程修改完成后的回调。"""
        dialog.setEnabled(True)
        if success:
            QMessageBox.information(dialog, "修改成功", message or "课程信息已更新")
            try:
                dialog.accept()
            except Exception:
                dialog.close()
            # 刷新课程列表（保持当前导航项）
            self._refresh_course_dropdown(preserve_nav=True)
            # 刷新课程管理界面
            self._render_course_management_view()
            self.status_callback("修改成功")
        else:
            QMessageBox.critical(dialog, "修改失败", message or "未知错误")
            self.status_callback("修改失败")

    def _refresh_course_dropdown(self, preserve_nav: bool = False):
        """
        向上找到主窗口调用 load_courses() 以重新请求课程列表。
        Args:
            preserve_nav: 是否保持当前选中的导航项（不自动跳转到统计）
        """
        parent = self.parent()
        while parent:
            if hasattr(parent, "load_courses"):
                try:
                    parent.load_courses(preserve_nav=preserve_nav)
                    return
                except Exception:
                    break
            parent = parent.parent()
        window_obj = self.window()
        if window_obj and hasattr(window_obj, "load_courses"):
            try:
                window_obj.load_courses(preserve_nav=preserve_nav)
            except Exception:
                pass

    def _load_cover_image(self, label, url):
        """异步加载网络图片到指定的QLabel，带调试输出。"""
        label.setText("封面加载中…")
        request = QNetworkRequest(QUrl(url))
        # Qt6 没有 FollowRedirectsAttribute，使用 RedirectPolicyAttribute 允许安全重定向
        try:
            request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        except Exception:
            pass
        request.setRawHeader(b"User-Agent", b"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        def on_finished():
            reply = self.sender()
            try:
                if reply.error() == QNetworkReply.NetworkError.NoError:
                    image_data = reply.readAll()
                    pixmap = QPixmap()
                    if pixmap.loadFromData(image_data):
                        tw, th = getattr(label, "_target_size", (label.width(), label.height()))
                        scaled_pixmap = pixmap.scaled(
                            tw if tw > 0 else 320,
                            th if th > 0 else 180,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        label.setPixmap(scaled_pixmap)
                        return
                    else:
                        self.status_callback("封面加载失败：数据无法解析为图片")
                else:
                    self.status_callback(f"封面加载失败：{reply.error()} {reply.errorString()} url={url}")
                label.setText("加载失败")
            finally:
                reply.deleteLater()

        reply = self.cover_network_manager.get(request)
        reply.finished.connect(on_finished)

    def _handle_upload_cover(self, dialog, cover_label, is_edit=False, course_id="", cpi=""):
        """处理上传封面操作"""
        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            dialog,
            "选择封面图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp);;所有文件 (*)"
        )

        if not file_path:
            return

        self.status_callback(f"正在上传图片: {file_path}")

        # 同步上传图片（可以使用worker改为异步）
        result = self.crawler.upload_cover_image(file_path)

        if result.get("success"):
            image_url = result.get("url", "")
            if image_url:
                # 加载上传后的图片
                self._load_cover_image(cover_label, image_url)
                # 保存URL到label属性中，供后续使用
                cover_label._last_url = image_url
                self.status_callback("封面上传成功")
                QMessageBox.information(dialog, "成功", "封面上传成功！")

                # 如果是编辑模式，更新课程封面
                if is_edit and course_id and cpi:
                    print(f"DEBUG: 编辑模式，更新课程封面: course_id={course_id}, cpi={cpi}, url={image_url}")
                    success, msg = self.crawler.update_course_logo(course_id, cpi, image_url)
                    if not success:
                        QMessageBox.warning(dialog, "提示", f"封面上传成功但更新课程失败: {msg}")
            else:
                QMessageBox.warning(dialog, "失败", "上传成功但未获取到图片URL")
        else:
            error_msg = result.get("error", "上传失败")
            QMessageBox.warning(dialog, "失败", f"上传失败: {error_msg}")
            self.status_callback(error_msg)

    def _handle_ai_generate_cover(self, dialog, cover_label, name_edit, ai_btn, upload_btn, is_edit=False, course_id="", cpi=""):
        """处理AI生成封面操作"""
        course_name = name_edit.text().strip()

        if not course_name:
            QMessageBox.warning(dialog, "提示", "请先输入课程名称")
            return

        # 保存原始鼠标指针和按钮状态
        original_cursor = dialog.cursor()
        original_ai_text = ai_btn.text()
        original_cover_text = cover_label.text() if hasattr(cover_label, 'text') else ""

        try:
            # 1. 禁用按钮防止重复点击
            ai_btn.setEnabled(False)
            upload_btn.setEnabled(False)

            # 2. 改变鼠标指针为等待状态
            dialog.setCursor(Qt.CursorShape.WaitCursor)

            # 3. 更新按钮文本提示用户正在处理
            ai_btn.setText("🔄 生成中...")

            # 4. 在封面区域显示加载信息
            cover_label.setText("✨ AI正在生成封面\n请稍候，这可能需要几秒钟...")
            cover_label.setStyleSheet("color: #ff9f43; font-size: 13px; padding: 40px;")

            # 5. 强制刷新UI
            QApplication.processEvents()

            # 6. 提示用户
            self.status_callback(f"正在使用AI生成封面: {course_name}（约需5-10秒）")

            # 调用AI生成接口
            result = self.crawler.generate_ai_cover(course_name)

            if result.get("success"):
                image_url = result.get("url", "")
                if image_url:
                    # 加载生成的图片
                    self._load_cover_image(cover_label, image_url)
                    # 恢复封面标签的样式
                    cover_label.setStyleSheet("background-color: #2a2d31; border-radius: 6px;")
                    # 保存URL到label属性中，供后续使用
                    cover_label._last_url = image_url
                    self.status_callback("AI封面生成成功")

                    # 如果是编辑模式，更新课程封面
                    if is_edit and course_id and cpi:
                        print(f"DEBUG: 编辑模式，更新课程封面: course_id={course_id}, cpi={cpi}, url={image_url}")
                        success, msg = self.crawler.update_course_logo(course_id, cpi, image_url)
                        if not success:
                            QMessageBox.warning(dialog, "提示", f"AI生成成功但更新课程失败: {msg}")
                else:
                    cover_label.setText("生成失败")
                    cover_label.setStyleSheet("")
                    QMessageBox.warning(dialog, "失败", "AI生成成功但未获取到图片URL")
            else:
                error_msg = result.get("error", "生成失败")
                cover_label.setText("生成失败\n请重试")
                cover_label.setStyleSheet("color: #ff4d4d;")
                QMessageBox.warning(dialog, "失败", f"AI生成失败: {error_msg}")
                self.status_callback(f"AI生成失败: {error_msg}")

        finally:
            # 恢复UI状态
            dialog.setCursor(original_cursor)
            ai_btn.setEnabled(True)
            upload_btn.setEnabled(True)
            ai_btn.setText(original_ai_text)


    def _create_course_form_widget(self, data: dict, parent=None, readonly: bool = False, title: str = "课程信息"):
        """卡片式按钮区：导入课程、基本信息、结课、删除。"""
        frame = QFrame(parent)
        frame.setStyleSheet("background-color: transparent; border: none;")

        outer_layout = QVBoxLayout(frame)
        outer_layout.setSpacing(14)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header = QLabel(title)
        header.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer_layout.addWidget(header)

        btn_row_layout = QHBoxLayout()
        btn_row_layout.setSpacing(14)
        btn_row_layout.setContentsMargins(6, 6, 6, 6)
        btn_row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_style = (
            " QPushButton {"
            "  background-color: #2d2f33;"
            "  color: #e4e9f0;"
            "  border: none;"
            "  border-radius: 10px;"
            "  padding: 12px 14px;"
            "  font-size: 15px;"
            "  font-weight: bold;"
            "  min-height: 80px;"
            "  text-align: center;"
            " }"
            " QPushButton:hover { background-color: #3a3f44; }"
            " QPushButton:pressed { background-color: #2a2d31; }"
            " QPushButton:disabled { color: #555555; }"
        )

        buttons = [
            ("📥 导入课程", "导入已有课程资源(不含章节)", self._handle_import_course),
            ("📄 基本信息", "查看或编辑课程基本信息", lambda: self._open_basic_info_dialog(data)),
            ("✅ 结课", "停止后续学习数据统计", lambda: self._handle_delete_course(data, "archive")),
            ("🗑️ 删除", "学生将不能继续参与课程学习", lambda: self._handle_delete_course(data, "delete")),
        ]

        for idx, (title_text, subtitle, handler) in enumerate(buttons):
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(btn_style)

            # 使用布局和标签实现富文本（主标题大字体，副标题小字体）
            btn_layout = QVBoxLayout(btn)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(2)

            # 这里的 HTML 样式可以让主标题大一点，副标题保持较小且颜色淡一些
            content_label = QLabel(
                f'<div style="text-align: center; margin: 0;">'
                f'  <div style="font-size: 17px; font-weight: bold; color: #ffffff; margin-bottom: 8px;">{title_text}</div>'
                f'  <div style="font-size: 14px; font-weight: normal; color: #a0a7b5; line-height: 1.2;">{subtitle}</div>'
                f'</div>'
            )
            content_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            btn_layout.addWidget(content_label)

            if handler:
                btn.clicked.connect(handler)
            else:
                btn.setEnabled(False if readonly else True)
            btn_row_layout.addWidget(btn)

        outer_layout.addLayout(btn_row_layout)
        outer_layout.addStretch()

        return frame

    def _handle_import_course(self):
        """拉取可导入课程列表并弹窗展示（异步，减少卡顿）。"""
        params = self.crawler.session_manager.course_params or {}
        course_id = params.get("courseid") or params.get("courseId")
        cpi = params.get("cpi", "")
        clazz_id = params.get("clazzid") or params.get("classId") or ""

        if not course_id:
            QMessageBox.warning(self, "提示", "缺少 courseid，无法获取导入列表。")
            return

        print(f"DEBUG: Fetching import list for course_id={course_id}, cpi={cpi}")
        url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/course/getimportlist?courseId={course_id}&cpi={cpi}&require="
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&clazzid={clazz_id}&courseId={course_id}&classId={clazz_id}&clazzId={clazz_id}&cpi={cpi}&ut=t&loadContentType=0",
            "X-Requested-With": "XMLHttpRequest",
        }

        loading = QMessageBox(self)
        loading.setWindowTitle("请稍候")
        loading.setText("正在加载可导入课程…")
        loading.setStandardButtons(QMessageBox.StandardButton.NoButton)
        loading.setWindowModality(Qt.WindowModality.ApplicationModal)
        loading.show()

        session = getattr(self.crawler, "session_manager", None)
        sess = getattr(session, "session", None)
        worker = ImportCourseListWorker(sess, url, headers, self)
        self.workers.append(worker)
        worker.finished.connect(lambda html, err: self._on_import_courses_ready(html, err, loading, worker))
        worker.start()

    def _on_import_courses_ready(self, html: str | None, err: str | None, loading_dialog: QMessageBox, worker):
        try:
            if err:
                if loading_dialog: loading_dialog.hide()
                print(f"DEBUG: Fetch import list failed. err={err}")
                QMessageBox.warning(self, "失败", f"获取导入列表失败: {err}")
                return

            if not html:
                if loading_dialog: loading_dialog.hide()
                print("DEBUG: Fetch import list failed. html is empty")
                QMessageBox.warning(self, "失败", "获取导入列表失败: 服务器返回内容为空")
                return

            print(f"DEBUG: Processing HTML for import list. Length: {len(html)}")
            items = self._parse_import_course_html(html)
            print(f"DEBUG: Parsed {len(items)} items from HTML")


            if not items:
                # 记录 HTML 以便调试选择器
                snippet = html[:500] + "..." if len(html) > 500 else html
                print(f"DEBUG: No items found. HTML Snippet: {snippet}")
                QMessageBox.information(self, "提示", "未找到可导入课程。如果该课程是新建的，可能暂时没有可复用的老课程。")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("选择导入课程")
            dialog.setMinimumSize(800, 600)
            dialog.setStyleSheet("QDialog { background-color: #121212; }")

            layout = QVBoxLayout(dialog)
            layout.setSpacing(12)
            layout.setContentsMargins(12, 12, 12, 12)

            list_widget = QListWidget()
            list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
            list_widget.setSpacing(8)
            list_widget.setStyleSheet(
                "QListWidget { background-color: transparent; border: none; padding: 4px; }"
                "QListWidget::item { margin: 6px 2px; }"
                "QListWidget::item:selected { background: transparent; }"
            )

            def set_card_selected(card: QFrame, selected: bool):
                if selected:
                    card.setStyleSheet(
                        "QFrame { background-color: #202531; border: 2px solid #007acc; border-radius: 10px; }"
                    )
                else:
                    card.setStyleSheet(
                        "QFrame { background-color: #1f1f24; border: 1px solid #2f2f36; border-radius: 10px; }"
                        "QFrame:hover { border: 1px solid #3a3f44; }"
                    )

            total = len(items)
            for idx, item in enumerate(items):
                if loading_dialog:
                    loading_dialog.setText(f"正在准备课程列表 ({idx+1}/{total})…")
                    QApplication.processEvents()
                list_item = QListWidgetItem()
                list_item.setSizeHint(QSize(0, 110))
                list_item.setData(Qt.ItemDataRole.UserRole, item)

                card = QFrame()
                set_card_selected(card, False)
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(12, 10, 12, 10)
                card_layout.setSpacing(12)

                cover_label = QLabel()
                cover_label.setFixedSize(96, 64)
                cover_label.setStyleSheet("background-color: #2a2d31; border-radius: 6px;")
                pm = self._load_cover_pixmap(item.get("cover"), width=96, height=64)
                cover_label.setPixmap(pm.scaled(96, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

                info_layout = QVBoxLayout()
                info_layout.setSpacing(4)
                info_layout.setContentsMargins(0, 0, 0, 0)

                name_label = QLabel(item.get("name", ""))
                name_label.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold;")

                num_term = QLabel(f"编号: {item.get('number','')} · 学期: {item.get('term','')}")
                num_term.setStyleSheet("color: #a0a7b5; font-size: 12px;")

                created = QLabel(f"建课时间: {item.get('created','')}")
                created.setStyleSheet("color: #7f8695; font-size: 12px;")

                info_layout.addWidget(name_label)
                info_layout.addWidget(num_term)
                info_layout.addWidget(created)

                card_layout.addWidget(cover_label)
                card_layout.addLayout(info_layout)
                card_layout.addStretch()

                list_item.setData(Qt.ItemDataRole.UserRole + 1, card)
                list_widget.addItem(list_item)
                list_widget.setItemWidget(list_item, card)

            def on_selection_changed():
                for i in range(list_widget.count()):
                    item_i = list_widget.item(i)
                    card_i = item_i.data(Qt.ItemDataRole.UserRole + 1)
                    set_card_selected(card_i, item_i.isSelected())
                import_btn.setEnabled(bool(list_widget.selectedItems()))

            list_widget.itemSelectionChanged.connect(on_selection_changed)

            layout.addWidget(list_widget)

            btn_bar = QHBoxLayout()
            btn_bar.addStretch()

            close_btn = QPushButton("取消")
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.setStyleSheet(
                "QPushButton { background:#3a3f44; color:#d1d5db; border:none; border-radius:6px; padding:10px 16px; font-size:13px; }"
                "QPushButton:hover { background-color: #4a4f55; }"
            )
            close_btn.clicked.connect(dialog.reject)

            import_btn = QPushButton("导入所选")
            import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            import_btn.setEnabled(False)
            import_btn.setStyleSheet(
                "QPushButton { background-color: #007acc; color: white; border: none; border-radius: 6px; padding: 10px 18px; font-weight: bold; font-size: 13px; }"
                "QPushButton:disabled { background-color: #2f3540; color: #8d96a8; }"
                "QPushButton:hover:!disabled { background-color: #005c99; }"
            )

            btn_bar.addWidget(close_btn)
            btn_bar.addWidget(import_btn)
            layout.addLayout(btn_bar)

            def handle_import():
                sel = list_widget.selectedItems()
                if not sel:
                    QMessageBox.information(dialog, "提示", "请选择要导入的课程")
                    return

                course = sel[0].data(Qt.ItemDataRole.UserRole)
                import_course_id = course.get("id")

                params = self.crawler.session_manager.course_params or {}
                course_id = params.get("courseid") or params.get("courseId")
                cpi = params.get("cpi", "")

                if not import_course_id or not course_id:
                    QMessageBox.warning(dialog, "错误", "缺少必要的课程ID，无法继续。")
                    return

                import_url = (
                    f"https://mooc2-gray.chaoxing.com/mooc2-ans/course/importprocess?"
                    f"importCourseId={import_course_id}&courseId={course_id}&cpi={cpi}&"
                    f"importBank=1&importExam=1&importChapter=0&importWork=1&importCourseTopic=1&"
                    f"copyModelIdStr=&importProblemMap=1&importTargetMap=1&importData=1&"
                    f"importAIAssistant=1&importPracticeLibrary=1"
                )

                headers = {
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}"
                }

                self.status_callback(f"正在从课程 {course.get('name')} 导入资源...")
                import_btn.setEnabled(False)
                import_btn.setText("正在导入...")

                session_manager = getattr(self.crawler, "session_manager", None)
                sess = getattr(session_manager, "session", None)

                import_worker = ImportProcessWorker(sess, import_url, headers, self)
                self.workers.append(import_worker)

                def on_import_finished(success, message):
                    if import_worker in self.workers:
                        self.workers.remove(import_worker)

                    import_btn.setEnabled(True)
                    import_btn.setText("导入所选")

                    if success:
                        QMessageBox.information(dialog, "成功", f"资源导入成功：{message}")
                        dialog.accept()
                        # 刷新课程管理界面（不刷新课程列表，避免跳转到统计）
                        self._render_course_management_view()
                    else:
                        QMessageBox.warning(dialog, "失败", f"导入资源失败：{message}")

                    self.status_callback(message)

                import_worker.finished.connect(on_import_finished)
                import_worker.start()

            import_btn.clicked.connect(handle_import)
            if loading_dialog:
                loading_dialog.hide()
                loading_dialog.deleteLater()

            dialog.exec()

            if worker in self.workers:
                self.workers.remove(worker)

        except Exception as e:
            import traceback
            traceback.print_exc()
            if loading_dialog: loading_dialog.hide()
            QMessageBox.critical(self, "致命错误", f"展示导入列表时出现异常:\n{str(e)}")
            if worker in self.workers:
                self.workers.remove(worker)

    def _handle_delete_course(self, course_data, mode="delete"):
        """处理删除或结课操作。 mode: 'delete' 或 'archive'"""
        course_id = course_data.get("id")
        course_name = course_data.get("name", "未知课程")

        title = "确认删除" if mode == "delete" else "确认结课"
        msg = f"您确定要{ '删除' if mode == 'delete' else '结束' }课程【{course_name}】吗？"

        reply = QMessageBox.question(self, title, msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        self.status_callback(f"正在{'删除' if mode == 'delete' else '结课'}课程: {course_name}")
        worker = CourseStateWorker(self.crawler, course_id, mode=mode)
        self.workers.append(worker)

        def on_finished(success, message):
            if worker in self.workers:
                self.workers.remove(worker)
            if success:
                QMessageBox.information(self, "操作成功", message)
                # 刷新课程列表（保持当前导航项）
                self._refresh_course_dropdown(preserve_nav=True)
                # 刷新课程管理界面
                self._render_course_management_view()
            else:
                QMessageBox.warning(self, "操作失败", message)
            self.status_callback(message)

        worker.finished.connect(on_finished)
        worker.start()

    def _parse_import_course_html(self, html: str):
        soup = BeautifulSoup(html, "lxml")
        results = []
        for box in soup.select("div.c_new_choose_bg.radio-list-box"):
            course_id = box.get("data") or ""
            img = box.select_one(".list-img img")
            name_el = box.select_one("p.list-name")
            number_el = box.select_one("span.number")
            term_text = ""
            created_text = ""
            for span in box.select("span.list-cont-info"):
                text = span.get_text(strip=True)
                if text.startswith("学期"):
                    term_text = text.replace("学期：", "").strip()
                if text.startswith("建课时间"):
                    created_text = text.replace("建课时间：", "").strip()
            results.append({
                "id": course_id,
                "name": name_el.get_text(strip=True) if name_el else "",
                "number": number_el.get_text(strip=True).replace("编号:", "").strip() if number_el else "",
                "term": term_text,
                "created": created_text,
                "cover": img["src"] if img and img.has_attr("src") else "",
            })
        return results

    def _load_cover_pixmap(self, path: str | None, width: int = 320, height: int = 180) -> QPixmap:
        """同步获取封面图片，优先使用登录 session 以携带 cookie，失败则返回占位图。"""
        pm = QPixmap()
        if path:
            try:
                if str(path).startswith("http"):
                    session = getattr(self.crawler, "session_manager", None)
                    sess = getattr(session, "session", None)
                    client = sess or requests
                    resp = client.get(path, timeout=8, headers={"Referer": "https://mooc2-gray.chaoxing.com/"})
                    if resp.status_code == 200:
                        pm.loadFromData(resp.content)
                else:
                    pm.load(path)
            except Exception as e:
                self.status_callback(f"封面加载失败: {e}")
        if pm.isNull():
            pm = self._generate_placeholder_cover(width, height)
        return pm

    def _generate_placeholder_cover(self, width: int, height: int) -> QPixmap:
        pm = QPixmap(width, height)
        pm.fill(QColor("#111111"))
        painter = QPainter(pm)
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0.0, QColor("#1f2a44"))
        gradient.setColorAt(1.0, QColor("#0c1a2b"))
        painter.fillRect(0, 0, width, height, gradient)
        painter.setPen(QColor("#7fb3ff"))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "课程封面预览")
        painter.end()
        return pm

    def restore_sub_feature(self, sub_type):
        mapping = {
            "class_management": self.on_class_management_clicked,
            "grade_weight": self.on_grade_weight_clicked,
            "teacher_team": self.on_teacher_team_clicked,
            "course_management": self.on_course_management_clicked
        }
        if sub_type in mapping:
            mapping[sub_type]()

    def on_show(self):
        # 切回管理时仅清空界面并重置状态，避免自动出现班级列表/新建班级
        self.last_manage_sub = None
        self.clear_management_list()

    def _handle_clone_course(self):
        """开始克隆课程的校验流程"""
        params = self.crawler.session_manager.course_params
        course_id = params.get('courseId') or params.get('courseid')
        clazz_id = params.get('clazzId') or params.get('clazzid')
        cpi = params.get('cpi')
        
        if not course_id or not cpi:
            QMessageBox.warning(self, "提示", "请先选择一个课程。")
            return
            
        self.status_callback("正在进行克隆前校验（身份验证/滑块）...")
        
        worker = CloneVerifyWorker(self.crawler, str(course_id), str(cpi), str(clazz_id or ""))
        self.workers.append(worker)
        worker.code_required.connect(self._prompt_for_verify_code)
        worker.verification_done.connect(self._on_clone_verification_done)
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def _on_clone_verification_done(self, success, message, tokens):
        """处理校验完成（可能跳过验证码直接完成，或滑块失败）"""
        if not success:
            QMessageBox.warning(self, "校验失败", message)
            self.status_callback(f"校验失败: {message}")
            return
            
        if tokens:
            self._show_clone_options_dialog(tokens)

    def _prompt_for_verify_code(self, verify_data):
        """弹出对话框请求短信验证码"""
        msg = verify_data.get("msg", "请输入发送到您手机的验证码")
        code, ok = QInputDialog.getText(self, "身份验证", msg)
        if ok and code:
            self.status_callback("正在提交验证码...")
            params = self.crawler.session_manager.course_params
            course_id = params.get('courseId') or params.get('courseid')
            cpi = params.get('cpi')
            
            worker = CloneSubmitVerifyWorker(self.crawler, str(course_id), str(cpi), code)
            self.workers.append(worker)
            worker.submit_finished.connect(self._on_final_verification_done)
            worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def _on_final_verification_done(self, success, message, tokens):
        """验证码校验完成"""
        if success:
            self.status_callback("校验成功")
            self._show_clone_options_dialog(tokens)
        else:
            QMessageBox.warning(self, "验证失败", message)
            self.status_callback(f"验证失败: {message}")

    def _show_clone_options_dialog(self, tokens):
        """显示克隆选项选择对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("选择克隆方式")
        dialog.setFixedWidth(400)
        dialog.setStyleSheet("background-color: #1e1f22; color: #ffffff;")
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        label = QLabel("校验通过！请选择克隆目标：")
        label.setStyleSheet("font-size: 15px; font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(label)
        
        btn_style = """
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: 1px solid #007acc;
                padding: 10px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
        """
        
        btn_self = QPushButton("📁 克隆给自己")
        btn_self.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_self.setStyleSheet(btn_style)
        btn_self.setFixedHeight(46)
        btn_self.clicked.connect(lambda: [dialog.done(1), self._perform_clone(tokens, "self")])
        layout.addWidget(btn_self)
        
        btn_others = QPushButton("👥 克隆给他人")
        btn_others.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_others.setStyleSheet(btn_style)
        btn_others.setFixedHeight(46)
        btn_others.clicked.connect(lambda: self._handle_clone_to_others(dialog, tokens))
        layout.addWidget(btn_others)
        
        dialog.exec()

    def _handle_clone_to_others(self, dialog, tokens):
        """处理点击克隆给他人的逻辑"""
        target_user, ok = QInputDialog.getText(self, "克隆给他人", "请输入目标用户的工号或手机号：")
        if ok and target_user:
            dialog.done(2)
            self._perform_clone(tokens, "other", input_content=target_user)

    def _perform_clone(self, tokens, target_type, input_content=""):
        """执行最终的克隆操作"""
        target_name = "他人" if target_type == "other" else "自己"
        self.status_callback(f"正在准备克隆到 {target_name} ({input_content if input_content else '本人'})...")
        
        params = self.crawler.session_manager.course_params
        
        # 准备 payload (严格遵循用户 snippet 提供字段名)
        payload = {
            "courseId": params.get("courseid") or params.get("courseId"),
            "clazzId": params.get("clazzid") or params.get("clazzId"),
            "copyObject": target_type, # self 或 other
            "schoolId": params.get("fid", "4311"), 
            "cpi": params.get("cpi"),
            "inputContent": input_content,
            
            "cloneCourseImg": params.get("cover_url") or params.get("cover", ""),
            "courseName": params.get("name", ""),
            "teachers": params.get("teacher", ""),
            
            # --- 关键签名 (对标用户 snippet / curl) ---
            "enc": params.get("enc") or "",      # course-manage 页的 enc
            "manageopenc": params.get("openc") or "", # 提示：snippet 中是 manageopenc，curl 中是 openc
            "copymapenc": tokens.get("copymapenc"),
            "copymaptime": tokens.get("copymaptime"),
            "t": tokens.get("copymaptime"),       # curl 中有 t=时间戳
            
            # 浏览器固定参数
            "copyDiscussTopic": 0,
            "notIncludeReply": 0,
            "copyProblemMap": 1,
            "copyTargetMap": 1,
            "copyDefaultTopic": 1,
            "copyCrossCourseRelation": 0,
            "copyModelIdStr": "",
        }
        
        worker = CloneActionWorker(self.crawler, payload)
        self.workers.append(worker)
        worker.finished.connect(lambda s, m: QMessageBox.information(self, "提示", m) if s else QMessageBox.warning(self, "失败", m))
        worker.finished.connect(lambda s, m: self.status_callback(m))
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QPushButton, QLabel, QFrame, QScrollArea, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from ui.workers import StatsWorker, DownloadWorker, DeleteStatsWorker
from ui.styles import STAT_BUTTON_STYLE, STAT_CARD_CONTAINER_STYLE, STAT_CARD_STYLE, STAT_CARD_HIGHLIGHT_STYLE
from core.config import STATS_TYPES
from core.stats_history import StatsHistory

class StatsView(QWidget):
    def __init__(self, crawler, status_callback, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.status_callback = status_callback
        self.stats_history = StatsHistory()
        self.workers = []
        self.last_stats_sub = None
        
        self.setup_ui()
        
    def setup_ui(self):
        self.layout = QGridLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.layout.setContentsMargins(10, 20, 10, 10)
        self.layout.setSpacing(25)
        
        # Buttons
        self.btn_attendance = QPushButton("📊 考勤")
        self.btn_homework = QPushButton("✍️ 作业")
        self.btn_quiz = QPushButton("📝 测验")
        self.btn_final_score = QPushButton("🎓 综合成绩")
        
        self.buttons = [self.btn_attendance, self.btn_homework, self.btn_quiz, self.btn_final_score]
        
        for btn in self.buttons:
            btn.setStyleSheet(STAT_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
        self.layout.addWidget(self.btn_attendance, 0, 0)
        self.layout.addWidget(self.btn_homework, 0, 1)
        self.layout.addWidget(self.btn_quiz, 0, 2)
        self.layout.addWidget(self.btn_final_score, 0, 3)
        
        # Result area
        self.stats_scroll = QFrame()
        self.stats_scroll.setStyleSheet(STAT_CARD_CONTAINER_STYLE)
        self.stats_scroll_layout = QVBoxLayout(self.stats_scroll)
        self.stats_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.stats_scroll_layout.setSpacing(10)
        
        self.stats_scroll_area = QScrollArea()
        self.stats_scroll_area.setWidgetResizable(True)
        self.stats_scroll_area.setWidget(self.stats_scroll)
        self.stats_scroll_area.setStyleSheet("border: none; background: transparent;")
        
        self.layout.addWidget(self.stats_scroll_area, 1, 0, 1, 4)
        
        # Connect signals
        self.btn_attendance.clicked.connect(self.on_attendance_clicked)
        self.btn_homework.clicked.connect(self.on_homework_clicked)
        self.btn_quiz.clicked.connect(self.on_quiz_clicked)
        self.btn_final_score.clicked.connect(self.on_final_score_clicked)

    def on_attendance_clicked(self):
        self._load_stats("attendance", self.btn_attendance, "考勤")

    def on_homework_clicked(self):
        self._load_stats("homework", self.btn_homework, "作业")

    def on_quiz_clicked(self):
        self._load_stats("quiz", self.btn_quiz, "测验")

    def on_final_score_clicked(self):
        self._load_stats("final_score", self.btn_final_score, "综合成绩")

    def _load_stats(self, stats_type, btn, display_name, trigger_export=True):
        self.last_stats_sub = stats_type
        click_time = datetime.now().replace(microsecond=0)
        
        self.clear_stats_list()
        loading_label = QLabel(f"正在同步{display_name}数据列表，请稍候...")
        loading_label.setStyleSheet("color: #007acc; padding: 20px;")
        self.stats_scroll_layout.addWidget(loading_label)
        
        btn.setEnabled(False)
        worker = StatsWorker(self.crawler, stats_type, click_time=click_time, trigger_export=trigger_export)
        self.workers.append(worker)
        worker.stats_ready.connect(lambda result: self._display_stats_results(result, stats_type))
        worker.stats_ready.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def clear_stats_list(self):
        while self.stats_scroll_layout.count():
            item = self.stats_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _enable_all_stats_buttons(self):
        for btn in self.buttons:
            btn.setEnabled(True)

    def _display_stats_results(self, result, stats_type: str):
        self._enable_all_stats_buttons()
        self.clear_stats_list()
        
        if isinstance(result, str):
            error_label = QLabel(result)
            error_label.setStyleSheet("color: #ff4d4d; padding: 20px;")
            self.stats_scroll_layout.addWidget(error_label)
            return

        config = STATS_TYPES.get(stats_type, {})
        icon = config.get("icon", "📊")
        display_suffix = config.get("display_suffix", "数据表")

        self.stats_scroll.hide()
        self.stats_scroll.setUpdatesEnabled(False)
        
        try:
            for item in result:
                card = QFrame()
                card.setObjectName("stats_card")
                card.setStyleSheet(STAT_CARD_STYLE)
                card_layout = QHBoxLayout(card)
                
                info_layout = QVBoxLayout()
                original_name = item['name']
                report_id = item.get('id')
                is_new = item.get('is_new', False)
                
                # Naming Logic:
                # 1. Check if we have a stored name for this ID
                stored_name = self.stats_history.get_name(report_id)
                
                if stored_name:
                    display_name = stored_name
                elif is_new and "统计一键导出" in original_name:
                    # 2. If it's a new generic item, rename it based on current context and save
                    display_name = original_name.replace("统计一键导出", display_suffix)
                    if report_id:
                        self.stats_history.save_info(report_id, display_name, item.get('time'))
                else:
                    # 3. Fallback to original name
                    display_name = original_name
                
                name_label = QLabel(f"{icon} {display_name}")
                name_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 13px;")
                meta_label = QLabel(f"🕒 时间: {item['time']}   |   ✨ 状态: {item['status']}")
                meta_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
                info_layout.addWidget(name_label)
                info_layout.addWidget(meta_label)
                
                card_layout.addLayout(info_layout)
                card_layout.addStretch()
                
                if item.get('url'):
                    dl_btn = QPushButton("下载数据")
                    dl_btn.setFixedWidth(90)
                    dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    dl_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #007acc;
                            color: white;
                            border-radius: 4px;
                            padding: 6px;
                            font-weight: bold;
                            font-size: 12px;
                        }
                        QPushButton:hover { background-color: #005a9e; }
                    """)
                    target_url = item['url']
                    dl_btn.clicked.connect(lambda checked, u=target_url, n=display_name: self.on_download_stats_clicked(u, n))
                    card_layout.addWidget(dl_btn)

                # Add Delete button for all stats types
                del_btn = QPushButton("删除")
                del_btn.setFixedWidth(90)
                del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                del_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #442222;
                        color: #ff8888;
                        border: 1px solid #ff4d4d;
                        border-radius: 4px;
                        padding: 6px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                    QPushButton:hover { 
                        background-color: #ff4d4d; 
                        color: white; 
                    }
                """)
                report_id = item.get('id')
                if report_id:
                    del_btn.clicked.connect(lambda checked, i=report_id, n=display_name, c=card: self.on_delete_stats_clicked(i, n, c))
                else:
                    del_btn.setEnabled(False)
                    del_btn.setToolTip("无法找到该记录的 ID")
                card_layout.addWidget(del_btn)
                
                self.stats_scroll_layout.addWidget(card)
        finally:
            self.stats_scroll.setUpdatesEnabled(True)
            self.stats_scroll.show()
        
        self.status_callback(f"列表同步完成: 共 {len(result)} 条记录")

    def on_download_stats_clicked(self, url, name):
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存数据", f"{safe_name}.xls", "Excel Files (*.xls *.xlsx);;All Files (*)"
        )
        
        if filename:
            self.status_callback(f"正在下载: {name}...")
            worker = DownloadWorker(self.crawler, url, filename)
            self.workers.append(worker)
            worker.download_finished.connect(self.on_download_finished)
            worker.download_finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()

    def on_download_finished(self, success, message):
        if success:
            self.status_callback("下载完成")
            QMessageBox.information(self, "下载结果", message)
        else:
            self.status_callback("下载失败")
            QMessageBox.critical(self, "下载错误", message)

    def on_delete_stats_clicked(self, report_id, name, card_widget):
        # Highlight the card being deleted
        card_widget.setStyleSheet(STAT_CARD_HIGHLIGHT_STYLE)
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"您确定要删除记录: {name} 吗？\n删除后将无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.status_callback(f"正在删除: {name}...")
            worker = DeleteStatsWorker(self.crawler, report_id)
            self.workers.append(worker)
            worker.stats_deleted.connect(lambda s, m, rid=report_id: self.on_delete_finished(s, m, rid))
            worker.stats_deleted.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
            worker.start()
        else:
            # Revert highlight if cancelled
            card_widget.setStyleSheet(STAT_CARD_STYLE)

    def on_delete_finished(self, success, message, report_id=None):
        if success:
            if report_id:
                self.stats_history.delete_info(report_id)
            self.status_callback("删除成功")
            QMessageBox.information(self, "删除结果", message)
            # Refresh the list WITHOUT triggering a new export
            if self.last_stats_sub:
                self.restore_sub_feature(self.last_stats_sub, trigger_export=False)
        else:
            self.status_callback("删除失败")
            QMessageBox.critical(self, "删除错误", message)

    def restore_sub_feature(self, sub_type, trigger_export=True):
        mapping = {
            "attendance": lambda: self._load_stats("attendance", self.btn_attendance, "考勤", trigger_export),
            "homework": lambda: self._load_stats("homework", self.btn_homework, "作业", trigger_export),
            "quiz": lambda: self._load_stats("quiz", self.btn_quiz, "测验", trigger_export),
            "final_score": lambda: self._load_stats("final_score", self.btn_final_score, "综合成绩", trigger_export)
        }
        if sub_type in mapping:
            mapping[sub_type]()
    
    def on_show(self):
        """Called when this view is shown"""
        self._enable_all_stats_buttons()
        self.clear_stats_list()

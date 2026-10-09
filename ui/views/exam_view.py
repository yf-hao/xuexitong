from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.theme import apply_theme_stylesheet, bind_theme_tree


class ExamListLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    URL = "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test"

    def __init__(self, session, course_params, class_id, request_id, parent=None):
        super().__init__(parent)
        self.session = session
        self.course_params = dict(course_params or {})
        self.class_id = str(class_id)
        self.request_id = request_id

    def run(self):
        try:
            course_id = str(
                self.course_params.get("courseid")
                or self.course_params.get("courseId")
                or ""
            )
            cpi = str(self.course_params.get("cpi") or "")
            if not course_id or not cpi or not self.class_id:
                raise RuntimeError("课程、班级或考试页面参数缺失")

            query = {
                "courseid": course_id,
                "ut": str(self.course_params.get("ut") or ""),
                "cpi": cpi,
            }
            form_data = {
                "courseid": course_id,
                "cpi": cpi,
                "ut": str(self.course_params.get("ut") or ""),
                "status": "-1",
                "recyle": "0",
                "clazzid": self.class_id,
                "sw": "",
                "size": "12",
                "pageNum": "1",
                "topicid": "0",
                "perspectiveType": "0",
            }
            referer = f"{self.URL}?{urlencode(query)}"
            response = self.session.post(
                self.URL,
                params=query,
                data=form_data,
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://mooc2-gray.chaoxing.com",
                    "Pragma": "no-cache",
                    "Referer": referer,
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/154.0.0.0 Safari/537.36"
                    ),
                },
                timeout=20,
            )
            response.raise_for_status()
            response_url = str(getattr(response, "url", "") or "").lower()
            if "passport2.chaoxing.com" in response_url:
                raise RuntimeError("登录状态已失效，请重新登录")

            soup = BeautifulSoup(response.text or "", "lxml")
            exams = []
            for item in soup.select("div.taskList ul > li[data]"):
                title_node = item.select_one(".list_li_tit")
                class_node = item.select_one(".list_class")
                time_node = item.select_one("p.list_li_time span")
                progress_node = item.select_one(".piyuePcon")
                marking_node = item.select_one("a.piyueBtn[href]")
                title = title_node.get_text(" ", strip=True) if title_node else ""
                task_id = str(item.get("data") or "").strip()
                if not task_id and not title:
                    continue
                exams.append({
                    "id": task_id,
                    "title": title or "未命名考试",
                    "class_name": (
                        str(class_node.get("title") or "").strip()
                        or class_node.get_text(" ", strip=True)
                        if class_node else ""
                    ),
                    "exam_time": (
                        time_node.get_text(" ", strip=True) if time_node else ""
                    ),
                    "progress": (
                        " / ".join(
                            node.get_text(" ", strip=True)
                            for node in progress_node.find_all("span", recursive=False)
                        )
                        if progress_node else ""
                    ),
                    "marking_url": (
                        urljoin(self.URL, marking_node.get("href", ""))
                        if marking_node else ""
                    ),
                })

            self.loaded.emit(self.request_id, exams)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class ExamMarkingRequestWorker(QThread):
    completed = pyqtSignal(str, str, bool, str)

    def __init__(self, session, exam, parent=None):
        super().__init__(parent)
        self.session = session
        self.task_id = str(exam.get("id") or "")
        self.title = str(exam.get("title") or "未命名考试")
        self.url = str(exam.get("marking_url") or "")

    def run(self):
        try:
            if not self.url:
                raise RuntimeError("该考试没有可用的批阅入口")
            response = self.session.get(
                self.url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": ExamListLoadWorker.URL,
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/154.0.0.0 Safari/537.36"
                    ),
                },
                timeout=20,
            )
            response.raise_for_status()
            response_url = str(getattr(response, "url", "") or "").lower()
            if "passport2.chaoxing.com" in response_url:
                raise RuntimeError("登录状态已失效，请重新登录")
            self.completed.emit(
                self.task_id,
                self.title,
                True,
                f"HTTP {response.status_code}",
            )
        except Exception as exc:
            self.completed.emit(self.task_id, self.title, False, str(exc))


class ExamView(QWidget):
    def __init__(
        self, crawler, get_class_id_callback, get_class_name_callback, parent=None
    ):
        super().__init__(parent)
        self.crawler = crawler
        self.get_class_id_callback = get_class_id_callback
        self.get_class_name_callback = get_class_name_callback
        self._exam_request_id = 0
        self._exam_workers = []
        self._marking_workers = []
        self._marking_pending = set()
        self._marking_buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.status_label = QLabel("选择班级后进入考试以查看考试信息")
        self.status_label.setObjectName("exam_status")
        layout.addWidget(self.status_label)

        self.exam_table = QTableWidget(0, 5)
        self.exam_table.setHorizontalHeaderLabels(
            ["考试名称", "班级", "考试时间", "提交进度", "操作"]
        )
        self.exam_table.verticalHeader().setVisible(False)
        self.exam_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.exam_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.exam_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.exam_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for column in range(1, 5):
            self.exam_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.exam_table, 1)

        apply_theme_stylesheet(self, lambda palette: f"""
            QWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QTableWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                gridline-color: {palette.border};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QPushButton {{
                background-color: {palette.accent};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {palette.accent_hover};
            }}
            QPushButton:pressed {{
                background-color: {palette.accent_focus};
            }}
            QPushButton:disabled {{
                background-color: {palette.disabled_bg};
                color: {palette.disabled_text};
                border: 1px solid {palette.border};
            }}
            QHeaderView::section {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: none;
                border-bottom: 1px solid {palette.border};
                padding: 7px;
            }}
            QLabel#exam_status {{
                color: {palette.text_muted};
            }}
        """)
        bind_theme_tree(self)

    def on_show(self):
        self._exam_request_id += 1
        request_id = self._exam_request_id
        class_id = str(self.get_class_id_callback() or "").strip()
        if not class_id:
            self._marking_buttons = {}
            self.exam_table.setRowCount(0)
            self.status_label.setText("请先在顶部选择班级")
            return

        session_manager = getattr(self.crawler, "session_manager", None)
        course_params = getattr(session_manager, "course_params", {}) or {}
        if not (course_params.get("courseid") or course_params.get("courseId")):
            self.status_label.setText("请先选择课程")
            return

        self._load_exam_list(class_id, course_params, request_id)

    def _load_exam_list(self, class_id, course_params, request_id):
        self._marking_buttons = {}
        self.exam_table.setRowCount(0)
        class_name = str(self.get_class_name_callback() or "").strip()
        loading_text = (
            f"正在加载“{class_name}”的考试列表..."
            if class_name else "正在加载考试列表..."
        )
        self.status_label.setText(loading_text)

        worker = ExamListLoadWorker(
            self.crawler.session,
            course_params,
            class_id,
            request_id,
            self,
        )
        self._exam_workers.append(worker)
        worker.loaded.connect(self._on_exam_list_loaded)
        worker.failed.connect(self._on_exam_list_failed)
        worker.finished.connect(self._on_exam_worker_finished)
        worker.start()

    def _on_exam_list_loaded(self, request_id, exams):
        if request_id != self._exam_request_id:
            return
        self.exam_table.setRowCount(len(exams))
        for row, exam in enumerate(exams):
            values = (
                exam["title"],
                exam["class_name"],
                exam["exam_time"],
                exam["progress"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, exam["id"])
                self.exam_table.setItem(row, column, item)
            marking_button = QPushButton("批阅")
            marking_button.setEnabled(bool(exam["marking_url"]))
            if not exam["marking_url"]:
                marking_button.setToolTip("该考试没有可用的批阅入口")
            elif exam["id"] in self._marking_pending:
                marking_button.setEnabled(False)
                marking_button.setText("请求中...")
            marking_button.clicked.connect(
                lambda checked=False, entry=exam: self._request_marking(entry)
            )
            self.exam_table.setCellWidget(row, 4, marking_button)
            self._marking_buttons[exam["id"]] = marking_button
        self.status_label.setText(
            f"已加载 {len(exams)} 场考试" if exams else "该班级暂无考试"
        )

    def _on_exam_list_failed(self, request_id, message):
        if request_id != self._exam_request_id:
            return
        self.status_label.setText(f"考试列表加载失败: {message}")

    def _request_marking(self, exam):
        task_id = str(exam.get("id") or "")
        if not task_id or task_id in self._marking_pending:
            return

        button = self._marking_buttons.get(task_id)
        if button:
            button.setEnabled(False)
            button.setText("请求中...")
        self._marking_pending.add(task_id)
        self.status_label.setText(f"正在请求“{exam['title']}”的批阅接口...")

        worker = ExamMarkingRequestWorker(self.crawler.session, exam, self)
        self._marking_workers.append(worker)
        worker.completed.connect(self._on_marking_request_completed)
        worker.finished.connect(self._on_marking_worker_finished)
        worker.start()

    def _on_marking_request_completed(self, task_id, title, success, message):
        self._marking_pending.discard(task_id)
        button = self._marking_buttons.get(task_id)
        if button:
            button.setEnabled(True)
            button.setText("批阅")
        if success:
            self.status_label.setText(
                f"已请求“{title}”的批阅接口（{message}），未打开网页"
            )
        else:
            self.status_label.setText(f"批阅接口请求失败: {message}")

    def _on_marking_worker_finished(self):
        worker = self.sender()
        if worker in self._marking_workers:
            self._marking_workers.remove(worker)
            worker.deleteLater()

    def _on_exam_worker_finished(self):
        worker = self.sender()
        if worker in self._exam_workers:
            self._exam_workers.remove(worker)
            worker.deleteLater()

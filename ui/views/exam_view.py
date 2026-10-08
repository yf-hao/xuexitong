import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.theme import apply_theme_stylesheet, bind_theme_tree


class ExamClassLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    URL = "https://mooc2-gray.chaoxing.com/mooc2-ans/exam/test"

    def __init__(self, session, course_params, request_id, parent=None):
        super().__init__(parent)
        self.session = session
        self.course_params = dict(course_params or {})
        self.request_id = request_id

    def run(self):
        try:
            course_id = str(
                self.course_params.get("courseid")
                or self.course_params.get("courseId")
                or ""
            )
            cpi = str(self.course_params.get("cpi") or "")
            if not course_id or not cpi:
                raise RuntimeError("当前课程缺少考试页面所需参数")

            timestamp = str(int(time.time() * 1000))
            params = {
                "courseid": course_id,
                "cpi": cpi,
            }
            params["ut"] = ""

            referer_params = {
                "courseid": course_id,
                "clazzid": str(self.course_params.get("clazzid") or "-1"),
                "cpi": cpi,
                "t": timestamp,
                "pageHeader": "7",
                "v": "2",
                "hideHead": "0",
                "perspectiveType": "",
            }
            if self.course_params.get("enc"):
                referer_params["enc"] = str(self.course_params["enc"])

            response = self.session.get(
                self.URL,
                params=params,
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Referer": (
                        "https://mooc2-gray.chaoxing.com/mooc2-ans/mycourse/tch?"
                        f"{urlencode(referer_params)}"
                    ),
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
            classes = []
            seen_ids = set()
            for item in soup.select("li.classli.inShow[data][title]"):
                class_id = str(item.get("data") or "").strip()
                title = str(item.get("title") or "").strip()
                if class_id and title and class_id not in seen_ids:
                    classes.append({"id": class_id, "title": title})
                    seen_ids.add(class_id)

            self.loaded.emit(self.request_id, classes)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


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
                })

            self.loaded.emit(self.request_id, exams)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class ExamView(QWidget):
    class_selected = pyqtSignal(str, str)

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.selected_class_id = ""
        self._request_id = 0
        self._load_worker = None
        self._exam_request_id = 0
        self._exam_workers = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        class_row = QHBoxLayout()
        class_label = QLabel("考试班级:")
        self.class_combo = QComboBox()
        self.class_combo.setMinimumWidth(280)
        self.class_combo.addItem("打开考试页面后加载班级", None)
        self.class_combo.setEnabled(False)
        self.class_combo.currentIndexChanged.connect(self._on_class_selected)
        class_row.addWidget(class_label)
        class_row.addWidget(self.class_combo)
        class_row.addStretch()
        layout.addLayout(class_row)

        self.status_label = QLabel("请选择课程功能中的“考试”以加载班级")
        self.status_label.setObjectName("exam_status")
        layout.addWidget(self.status_label)

        self.exam_table = QTableWidget(0, 4)
        self.exam_table.setHorizontalHeaderLabels(
            ["考试名称", "班级", "考试时间", "提交进度"]
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
        for column in range(1, 4):
            self.exam_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.exam_table, 1)

        apply_theme_stylesheet(self, lambda palette: f"""
            QWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QComboBox {{
                background-color: {palette.input_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 6px 8px;
            }}
            QComboBox:hover, QComboBox:focus {{
                border: 1px solid {palette.accent};
            }}
            QComboBox QAbstractItemView {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
            }}
            QTableWidget {{
                background-color: {palette.panel_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                gridline-color: {palette.border};
                selection-background-color: {palette.accent};
                selection-color: #ffffff;
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
        if self._load_worker and self._load_worker.isRunning():
            return

        session_manager = getattr(self.crawler, "session_manager", None)
        course_params = getattr(session_manager, "course_params", {}) or {}
        if not (course_params.get("courseid") or course_params.get("courseId")):
            self.status_label.setText("请先选择课程")
            return

        self._request_id += 1
        request_id = self._request_id
        self.selected_class_id = ""
        self.class_combo.clear()
        self.class_combo.addItem("正在加载班级...", None)
        self.class_combo.setEnabled(False)
        self.status_label.setText("正在获取考试班级...")

        worker = ExamClassLoadWorker(
            self.crawler.session,
            course_params,
            request_id,
            self,
        )
        self._load_worker = worker
        worker.loaded.connect(self._on_classes_loaded)
        worker.failed.connect(self._on_classes_failed)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _on_classes_loaded(self, request_id, classes):
        if request_id != self._request_id:
            return

        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_combo.addItem("请选择班级", None)
        for item in classes:
            self.class_combo.addItem(item["title"], item["id"])
        self.class_combo.blockSignals(False)
        self.class_combo.setEnabled(bool(classes))
        self.selected_class_id = ""
        self.exam_table.setRowCount(0)
        self.status_label.setText(
            f"已获取 {len(classes)} 个班级" if classes else "未找到可选班级"
        )

    def _on_classes_failed(self, request_id, message):
        if request_id != self._request_id:
            return
        self.class_combo.clear()
        self.class_combo.addItem("班级加载失败", None)
        self.class_combo.setEnabled(False)
        self.status_label.setText(f"考试班级加载失败: {message}")

    def _on_class_selected(self, index):
        class_id = str(self.class_combo.itemData(index) or "")
        title = self.class_combo.itemText(index)
        self.selected_class_id = class_id
        if class_id:
            self.status_label.setText(f"已选择: {title}")
            self.class_selected.emit(class_id, title)
            self._load_exam_list(class_id)

    def _load_exam_list(self, class_id):
        session_manager = getattr(self.crawler, "session_manager", None)
        course_params = getattr(session_manager, "course_params", {}) or {}
        self._exam_request_id += 1
        request_id = self._exam_request_id
        self.exam_table.setRowCount(0)
        self.status_label.setText("正在加载考试列表...")

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
        self.status_label.setText(
            f"已加载 {len(exams)} 场考试" if exams else "该班级暂无考试"
        )

    def _on_exam_list_failed(self, request_id, message):
        if request_id != self._exam_request_id:
            return
        self.status_label.setText(f"考试列表加载失败: {message}")

    def _on_exam_worker_finished(self):
        worker = self.sender()
        if worker in self._exam_workers:
            self._exam_workers.remove(worker)
            worker.deleteLater()

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is self._load_worker:
            self._load_worker = None
        if worker is not None:
            worker.deleteLater()
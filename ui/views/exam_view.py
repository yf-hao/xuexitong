import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup
from PyQt6.QtCore import QEvent, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.theme import apply_theme_stylesheet, bind_theme_tree


def _extract_progress_counts(progress_node):
    labels = ("待批", "已交", "未交")
    counts = {label: "—" for label in labels}
    if not progress_node:
        return counts

    spans = progress_node.find_all("span", recursive=False)
    for index, span in enumerate(spans[:len(labels)]):
        text = span.get_text(" ", strip=True)
        match = re.search(r"\d+", text)
        count = match.group(0) if match else "0"
        label = next((candidate for candidate in labels if candidate in text), None)
        if label is None:
            label = labels[index]
        counts[label] = count
    return counts


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
                    "course_id": course_id,
                    "class_id": self.class_id,
                    "cpi": cpi,
                    "class_name": (
                        str(class_node.get("title") or "").strip()
                        or class_node.get_text(" ", strip=True)
                        if class_node else ""
                    ),
                    "exam_time": (
                        time_node.get_text(" ", strip=True) if time_node else ""
                    ),
                    "progress_counts": _extract_progress_counts(progress_node),
                    "marking_url": (
                        urljoin(self.URL, marking_node.get("href", ""))
                        if marking_node else ""
                    ),
                })

            self.loaded.emit(self.request_id, exams)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class ExamView(QWidget):
    review_requested = pyqtSignal(object)

    def __init__(
        self, crawler, get_class_id_callback, get_class_name_callback, parent=None
    ):
        super().__init__(parent)
        self.crawler = crawler
        self.get_class_id_callback = get_class_id_callback
        self.get_class_name_callback = get_class_name_callback
        self._exam_request_id = 0
        self._exam_workers = []
        self._marking_buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.status_label = QLabel("选择班级后进入考试以查看考试信息")
        self.status_label.setObjectName("exam_status")
        layout.addWidget(self.status_label)

        self.exam_table = QTableWidget(0, 7)
        self.exam_table.setHorizontalHeaderLabels(
            ["考试名称", "班级", "考试时间", "待批", "已交", "未交", "操作"]
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
        self.exam_table.setWordWrap(True)
        self.exam_table.setAlternatingRowColors(True)
        self.exam_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.exam_table.viewport().installEventFilter(self)
        header = self.exam_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._resize_exam_columns()
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
            QTableWidget::item {{
                padding: 6px;
            }}
            QTableWidget::item:alternate {{
                background-color: {palette.panel_alt_bg};
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_exam_columns)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._resize_exam_columns)

    def eventFilter(self, watched, event):
        if (
            hasattr(self, "exam_table")
            and watched is self.exam_table.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            QTimer.singleShot(0, self._resize_exam_columns)
        return super().eventFilter(watched, event)

    def _resize_exam_columns(self):
        if not hasattr(self, "exam_table"):
            return

        available_width = self.exam_table.viewport().width()
        if available_width <= 0:
            available_width = self.exam_table.width()

        min_widths = (240, 150, 170, 76, 76, 76, 90)
        if available_width < sum(min_widths):
            widths = min_widths
        else:
            action_width = 90
            extra_width = available_width - sum(min_widths)
            title_width = 240 + min(int(extra_width * 0.35), 180)
            count_width = 76 + min(int(extra_width * 0.10), 34)
            metadata_extra = extra_width - (title_width - 240) - 3 * (count_width - 76)
            class_extra = int(metadata_extra * 0.45)
            class_width = 150 + class_extra
            time_width = 170 + metadata_extra - class_extra
            widths = (
                title_width,
                class_width,
                time_width,
                count_width,
                count_width,
                count_width,
                action_width,
            )

        for column, width in enumerate(widths):
            self.exam_table.setColumnWidth(column, width)

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
        self.status_label.show()
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
                exam["progress_counts"]["待批"],
                exam["progress_counts"]["已交"],
                exam["progress_counts"]["未交"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (
                        Qt.AlignmentFlag.AlignLeft
                        if column == 0
                        else Qt.AlignmentFlag.AlignCenter
                    )
                )
                item.setData(Qt.ItemDataRole.UserRole, exam["id"])
                self.exam_table.setItem(row, column, item)
            marking_button = QPushButton("批阅")
            marking_button.setMinimumHeight(36)
            marking_button.setEnabled(bool(exam["marking_url"]))
            if not exam["marking_url"]:
                marking_button.setToolTip("该考试没有可用的批阅入口")
            marking_button.clicked.connect(
                lambda checked=False, entry=exam: self.review_requested.emit(entry)
            )
            self.exam_table.setCellWidget(row, 6, marking_button)
            self._marking_buttons[exam["id"]] = marking_button
        self.exam_table.resizeRowsToContents()
        for row in range(len(exams)):
            self.exam_table.setRowHeight(
                row, max(self.exam_table.rowHeight(row), 44)
            )
        if exams:
            self.status_label.clear()
            self.status_label.hide()
        else:
            self.status_label.setText("该班级暂无考试")
            self.status_label.show()

    def _on_exam_list_failed(self, request_id, message):
        if request_id != self._exam_request_id:
            return
        self.status_label.show()
        self.status_label.setText(f"考试列表加载失败: {message}")

    def _on_exam_worker_finished(self):
        worker = self.sender()
        if worker in self._exam_workers:
            self._exam_workers.remove(worker)
            worker.deleteLater()

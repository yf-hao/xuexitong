"""笔记列表视图。"""

import re
import json
from datetime import datetime

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QTextDocument
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QMessageBox, QSpinBox, QTabWidget, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)

from core.coop_resource_encoder import CoopResourceEncoder
from ui.theme import apply_theme_stylesheet, bind_theme_tree


class NotesLoadThread(QThread):
    """在后台请求笔记列表，避免阻塞主界面。"""

    loaded = pyqtSignal(int, list)
    failed = pyqtSignal(int, str)

    def __init__(self, crawler, index, user_id, notebook_id, parent_id):
        super().__init__()
        self.crawler = crawler
        self.index = index
        self.user_id = user_id
        self.notebook_id = notebook_id
        self.parent_id = parent_id

    def run(self):
        try:
            session = self.crawler.session
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://noteyd.chaoxing.com/pc/note_notebook/myNotebooksLatest",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            }
            if self.index == 2:
                response = session.get(
                    "https://noteyd.chaoxing.com/pc/cooperate/getCooperateNotes",
                    params={
                        "kw": "", "lastValue": "", "maxW": 80,
                        "pageSize": 30, "_t": datetime.now().day,
                    }, headers=headers, timeout=15,
                )
                response.raise_for_status()
                payload = response.json()
                notes = self._extract_notes(payload)
                if notes is None:
                    raise RuntimeError(self._response_error(payload))
                self._hydrate_cooperate_notes(session, notes, headers)
                self.loaded.emit(self.index, notes)
                return

            category_id = (
                f"gongkaibiji{self.user_id}"
                if self.index == 0
                else f"gerenbiji{self.user_id}"
            )
            endpoint_candidates = [
                "https://noteyd.chaoxing.com/pc/note_note/myNotesLatest"
            ]
            query_ids = []
            for query_id in (category_id, self.parent_id, "root"):
                if query_id and query_id not in query_ids:
                    query_ids.append(query_id)

            last_payload = None
            for endpoint in endpoint_candidates:
                for query_id in query_ids:
                    params = {
                        "notebookCid": query_id, "kw": "", "_t": datetime.now().day,
                    }
                    params.update({
                        "offsetValue": "", "top": 0, "maxW": 80,
                        "pageSize": 30, "showCollection": 0,
                    })
                    response = session.get(endpoint, params=params, headers=headers, timeout=15)
                    response.raise_for_status()
                    last_payload = response.json()
                    notes = self._extract_notes(last_payload)
                    if notes is not None:
                        self._hydrate_cooperate_notes(session, notes, headers)
                        self.loaded.emit(self.index, notes)
                        return

            raise RuntimeError(self._response_error(last_payload))
        except Exception as exc:
            self.failed.emit(self.index, str(exc))

    @staticmethod
    def _response_error(payload):
        if isinstance(payload, dict):
            return f"接口未返回成功数据(result={payload.get('result')}, msg={payload.get('msg')})"
        return "接口返回格式异常"

    @staticmethod
    def _extract_notes(payload):
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        if result not in (1, True, "1", "true", "True"):
            return None

        message = payload.get("msg")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                message = None

        candidates = [message, payload.get("data")]
        for candidate in candidates:
            if isinstance(candidate, list):
                return candidate
            if isinstance(candidate, dict):
                notes = candidate.get("list") or candidate.get("notes")
                if isinstance(notes, list):
                    return notes
        return []

    @classmethod
    def _hydrate_cooperate_notes(cls, session, notes, headers):
        """补充资源笔记的正文，列表接口通常只返回 coopResource。"""
        for note in notes:
            if not isinstance(note, dict):
                continue
            if not (note.get("coopResource") or str(note.get("isCooperate", 0)).lower() in ("1", "true")):
                continue
            if note.get("content") or note.get("contentTxt") or note.get("rtf_content"):
                continue
            note_id = cls._note_id(note)
            if not note_id:
                continue
            try:
                response = session.get(
                    "https://noteyd.chaoxing.com/pc/note_note/getNoteDetail",
                    params={"cid": note_id, "needCoopResource": 1},
                    headers=headers,
                    timeout=15,
                )
                response.raise_for_status()
                payload = response.json()
                message = payload.get("msg") if isinstance(payload, dict) else None
                detail = message.get("note") if isinstance(message, dict) else None
                if isinstance(detail, dict):
                    for key in ("content", "contentTxt", "rtf_content", "coopResource"):
                        if detail.get(key):
                            note[key] = detail[key]
            except Exception:
                continue

    @staticmethod
    def _note_id(note):
        for key in ("noteCid", "note_id", "noteId", "uuid", "cid", "id"):
            value = note.get(key)
            if value:
                return str(value)
        return ""


class NoteCard(QWidget):
    """可点击的笔记卡片。"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class NotesView(QWidget):
    """直接请求超星笔记接口并在应用内展示列表。"""

    NOTE_HOME_URL = "https://noteyd.chaoxing.com/pc/note_notebook/myNotebooksLatest"
    NOTEBOOK_ID_FALLBACK = "bb551915d9e7d5a86071cdfeb91dc755"
    TAB_NAMES = ("公开笔记", "个人笔记", "推荐")

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.user_id = ""
        self.notebook_id = ""
        self.parent_id = "root"
        self.load_thread = None
        self._resource_encoder = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 10)

        header = QHBoxLayout()
        title = QLabel("笔记")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_current)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.lists = []
        for name in self.TAB_NAMES:
            note_list = QListWidget()
            apply_theme_stylesheet(note_list, self._note_list_stylesheet)
            note_list.setWordWrap(True)
            note_list.setSpacing(6)
            note_list.currentItemChanged.connect(
                lambda current, _previous, current_list=note_list:
                self._sync_note_selection(current_list, current)
            )
            self.lists.append(note_list)
            self.tabs.addTab(note_list, name)
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(self.load_current)
        layout.addWidget(self.tabs)
        bind_theme_tree(self)

    @staticmethod
    def _note_list_stylesheet(palette):
        return f"""
            QListWidget {{
                background-color: {palette.card_bg};
                color: {palette.text_secondary};
                border: 1px solid {palette.border};
                border-radius: 8px;
                outline: none;
                padding: 8px;
            }}
            QListWidget::item {{
                background-color: transparent;
                border: none;
                padding: 0;
                margin: 3px 0;
            }}
            QListWidget::item:hover {{
                background-color: {palette.hover_bg};
            }}
            QListWidget::item:selected {{
                background-color: {palette.hover_bg};
            }}
            QScrollBar:vertical {{
                background-color: {palette.panel_alt_bg};
                width: 10px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {palette.border_strong};
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {palette.accent};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """

    @staticmethod
    def _note_card_stylesheet(palette):
        return f"""
            QWidget#note_card {{
                background-color: {palette.panel_bg};
                border: 1px solid {palette.border};
                border-radius: 6px;
            }}
            QWidget#note_card[selected="true"] {{
                background-color: {palette.hover_bg};
                border: 2px solid {palette.accent};
            }}
            QLabel#note_title {{
                color: {palette.text};
                font-size: 16px;
                font-weight: bold;
            }}
            QLabel#note_content {{
                color: {palette.text_secondary};
                font-size: 14px;
            }}
            QLabel#note_meta {{
                color: {palette.text_muted};
                font-size: 12px;
            }}
        """

    def _get_note_home_html(self):
        response = self.crawler.session.get(
            self.NOTE_HOME_URL,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://groupyd2.chaoxing.com/pc/activity/activityList",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            },
            timeout=10,
        )
        if response.status_code == 403:
            return ""
        response.raise_for_status()
        return response.text

    def _prepare_context(self):
        cookies = self.crawler.session.cookies
        self.user_id = cookies.get("UID") or cookies.get("_uid") or ""
        html = self._get_note_home_html()
        if not self.user_id:
            match = re.search(r'"puid"\s*:\s*"?(\d+)', html)
            self.user_id = match.group(1) if match else ""
        match = re.search(r"\bnotebookCid\s*:\s*['\"]([^'\"]+)", html)
        if match:
            self.notebook_id = match.group(1)
        else:
            match = re.search(r"\bdes\s*:\s*['\"]([^'\"]+)", html)
            self.notebook_id = match.group(1) if match else self.NOTEBOOK_ID_FALLBACK
        match = re.search(r"\bpCid\s*:\s*['\"]([^'\"]+)", html)
        self.parent_id = match.group(1) if match else "root"

    def on_show(self):
        self.refresh_current()

    def refresh_current(self):
        self.load_current(self.tabs.currentIndex())

    def load_current(self, index):
        if self.load_thread and self.load_thread.isRunning():
            return
        self.lists[index].clear()
        self.lists[index].addItem("正在加载笔记...")
        try:
            self._prepare_context()
        except Exception as exc:
            self._show_error(index, f"无法获取笔记配置: {exc}")
            return

        self.load_thread = NotesLoadThread(
            self.crawler, index, self.user_id, self.notebook_id, self.parent_id
        )
        self.load_thread.loaded.connect(self._on_notes_loaded)
        self.load_thread.failed.connect(self._on_notes_failed)
        self.load_thread.finished.connect(self._clear_load_thread)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.start()

    def _clear_load_thread(self):
        self.load_thread = None

    def _on_notes_loaded(self, index, notes):
        note_list = self.lists[index]
        note_list.clear()
        if not notes:
            note_list.addItem("暂无笔记")
            return
        for note in notes:
            item = QListWidgetItem()
            item.setData(32, note)
            note_list.addItem(item)
            note_widget = self._create_note_widget(note)
            note_widget.clicked.connect(lambda current_item=item: note_list.setCurrentItem(current_item))
            note_widget.double_clicked.connect(lambda current=note: self._show_note_detail(current))
            item.setSizeHint(note_widget.sizeHint())
            note_list.setItemWidget(item, note_widget)

    def _on_notes_failed(self, index, message):
        self._show_error(index, f"笔记加载失败: {message}")

    def _show_error(self, index, message):
        self.lists[index].clear()
        self.lists[index].addItem(message)

    @staticmethod
    def _sync_note_selection(note_list, selected_item):
        for index in range(note_list.count()):
            item = note_list.item(index)
            card = note_list.itemWidget(item)
            if card is None:
                continue
            card.setProperty("selected", item is selected_item)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    def _show_note_detail(self, note):
        try:
            note = self._fetch_note_detail(note)
        except Exception as exc:
            QMessageBox.warning(self, "加载失败", f"无法加载笔记详情: {exc}")
            return

        title = str(note.get("title") or "无标题").strip()
        content = str(
            note.get("rtf_content") or note.get("content") or note.get("contentTxt") or ""
        ).strip()
        if self._uses_resource_note(note):
            self._prepare_resource_encoder(note)
        time_text = str(note.get("ftime") or note.get("createTime") or "")
        read_count = note.get("readCount", note.get("s_readcount", 0))

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(680, 480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("note_detail_title")
        layout.addWidget(title_label)

        meta_label = QLabel(f"{time_text}  ·  阅读 {read_count}")
        meta_label.setObjectName("note_detail_meta")
        layout.addWidget(meta_label)

        content_view = QTextEdit()
        content_view.setAcceptRichText(True)
        if re.search(r"<[a-zA-Z][^>]*>", content):
            content_view.setHtml(content)
        else:
            content_view.setPlainText(content)
        content_view.setObjectName("note_detail_content")
        markdown_action = QAction("Markdown 源码", dialog)
        markdown_action.setCheckable(True)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setObjectName("note_edit_toolbar")
        markdown_action.toggled.connect(
            lambda checked: self._toggle_markdown_mode(content_view, checked)
        )
        bold_action = QAction("加粗", toolbar)
        bold_action.setCheckable(True)
        bold_action.toggled.connect(lambda checked: content_view.setFontWeight(700 if checked else 400))
        toolbar.addAction(bold_action)
        italic_action = QAction("斜体", toolbar)
        italic_action.setCheckable(True)
        italic_action.toggled.connect(content_view.setFontItalic)
        toolbar.addAction(italic_action)
        underline_action = QAction("下划线", toolbar)
        underline_action.setCheckable(True)
        underline_action.toggled.connect(content_view.setFontUnderline)
        toolbar.addAction(underline_action)
        toolbar.addSeparator()
        toolbar.addAction(markdown_action)
        toolbar.addSeparator()
        size_box = QSpinBox()
        size_box.setRange(8, 48)
        size_box.setValue(14)
        size_box.setSuffix(" px")
        size_box.valueChanged.connect(lambda value: content_view.setFontPointSize(value))
        toolbar.addWidget(size_box)
        layout.addWidget(toolbar)
        layout.addWidget(content_view)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        save_button = QPushButton("保存")
        save_button.setObjectName("note_save_button")
        save_button.clicked.connect(
            lambda: self._save_note_content(note, content_view, dialog, markdown_action.isChecked())
        )
        action_layout.addWidget(save_button)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(dialog.reject)
        action_layout.addWidget(cancel_button)
        layout.addLayout(action_layout)

        apply_theme_stylesheet(dialog, self._note_detail_stylesheet)
        dialog.exec()

    def _prepare_resource_encoder(self, note):
        note_id = self._note_id(note)
        if not note_id:
            return
        if self._resource_encoder is None:
            self._resource_encoder = CoopResourceEncoder(self.crawler.session, note_id, self)
        else:
            self._resource_encoder.set_note_cid(note_id)
        self._resource_encoder.prepare()

    def _fetch_note_detail(self, note):
        note_id = self._note_id(note)
        if not note_id:
            raise RuntimeError("笔记数据中缺少笔记 ID")

        response = self.crawler.session.get(
            "https://noteyd.chaoxing.com/pc/note_note/getNoteDetail",
            params={"cid": note_id, "needCoopResource": 1},
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": f"https://noteyd.chaoxing.com/pc/{note_id}?isEdit=1&type=1",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("msg") if isinstance(payload, dict) else None
        detail = message.get("note") if isinstance(message, dict) else None
        if payload.get("result") not in (1, True, "1", "true", "True") or not isinstance(detail, dict):
            raise RuntimeError("详情接口未返回有效笔记数据")

        merged = dict(note)
        merged.update(detail)
        resources = detail.get("coopResource")
        if isinstance(resources, list):
            for resource in resources:
                value = resource.get("value") if isinstance(resource, dict) else None
                if isinstance(value, dict) and value.get("data"):
                    merged["coopResource"] = value["data"]
                    break
        return merged

    @staticmethod
    def _toggle_markdown_mode(content_view, enabled):
        if enabled:
            content_view.setPlainText(content_view.document().toMarkdown())
        else:
            content_view.document().setMarkdown(content_view.toPlainText())

    def _save_note_content(self, note, content_view, dialog, markdown_mode=False):
        if markdown_mode:
            content = content_view.toPlainText()
            markdown_document = QTextDocument()
            markdown_document.setMarkdown(content)
            rtf_content = markdown_document.toHtml()
            plain_content = markdown_document.toPlainText()
        else:
            content = content_view.toPlainText()
            rtf_content = content_view.toHtml()
            plain_content = content
        resource_html = self._resource_editor_html(rtf_content)
        note_id = self._note_id(note)
        if not note_id:
            QMessageBox.warning(dialog, "保存失败", "笔记数据中缺少笔记 ID")
            return
        if not self._uses_resource_note(note):
            self._save_plain_note_content(
                note, content, rtf_content, plain_content, dialog
            )
            return
        if self._resource_encoder is None:
            self._resource_encoder = CoopResourceEncoder(self.crawler.session, note_id, self)
        else:
            self._resource_encoder.set_note_cid(note_id)
        encoder = self._resource_encoder
        encoder.encode(
            resource_html,
            str(note.get("title") or ""),
            on_encoded=lambda resource: self._save_note_content_with_resource(
                note, content, rtf_content, plain_content, resource, dialog, encoder
            ),
            on_failed=lambda message: QMessageBox.warning(dialog, "保存失败", message),
        )

    @staticmethod
    def _is_cooperate_note(note):
        return (
            str(note.get("isCooperate", 0)).lower() in ("1", "true")
        )

    @staticmethod
    def _uses_resource_note(note):
        return NotesView._is_cooperate_note(note) or bool(note.get("coopResource"))

    @staticmethod
    def _resource_editor_html(html):
        match = re.search(r"<body[^>]*>(.*?)</body>", str(html or ""), re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else str(html or "").strip()

    def _save_plain_note_content(self, note, content, rtf_content, plain_content, dialog):
        try:
            self._save_note_draft(note, content, rtf_content)
            self._save_note_remote(note, content, rtf_content)
            saved_note = self._fetch_note_detail(note)
            saved_content = str(
                saved_note.get("content") or saved_note.get("contentTxt") or ""
            ).strip()
            if saved_content != plain_content.strip():
                raise RuntimeError("服务器返回成功，但重新读取的正文仍未更新。")
        except Exception as exc:
            QMessageBox.warning(dialog, "保存失败", str(exc))
            return

        note["content"] = content
        note["contentTxt"] = content
        note["rtf_content"] = rtf_content
        self._refresh_note_card(note, plain_content)
        dialog.accept()

    def _save_note_content_with_resource(
        self, note, content, rtf_content, plain_content, resource, dialog, encoder
    ):
        original_resource = str(note.get("coopResource") or "")
        note["coopResource"] = resource
        try:
            draft_payload = self._save_note_draft(note, content, rtf_content)
            if original_resource and resource == original_resource:
                raise RuntimeError(
                    "网页编辑器生成的 coopResource 未发生变化；"
                    "当前编辑器尚未生成编辑后的学习通专用资源。"
                )
            note["coopResource"] = resource
            self._save_note_remote(note, content, rtf_content)
            saved_note = self._fetch_note_detail(note)
            saved_content = str(saved_note.get("content") or "").strip()
            saved_resource = str(saved_note.get("coopResource") or "")
            if note.get("coopResource"):
                if saved_resource and saved_resource != str(note["coopResource"]):
                    raise RuntimeError(
                        "正式接口返回成功，但服务器回读的 coopResource 与新正文不一致。"
                    )
                if not saved_resource and saved_content != plain_content.strip():
                    raise RuntimeError(
                        "草稿或正式接口返回成功，但学习通正文仍未更新；"
                        "服务器没有回读新的 coopResource。"
                    )
            elif saved_content != plain_content.strip():
                raise RuntimeError("服务器返回成功，但重新读取的正文仍未更新。")
        except Exception as exc:
            QMessageBox.warning(dialog, "保存失败", str(exc))
            return

        note["content"] = content
        note["contentTxt"] = content
        note["rtf_content"] = rtf_content
        self._refresh_note_card(note, plain_content)
        dialog.accept()

    def _save_note_draft(self, note, content, rtf_content):
        note_id = self._note_id(note)
        if not note_id:
            raise RuntimeError("笔记数据中缺少笔记 ID，无法保存草稿")

        notebook_id = str(
            note.get("notebookCid") or note.get("notebookId") or self.notebook_id
        )
        resource_only = self._is_cooperate_note(note) and bool(note.get("coopResource"))
        response = self.crawler.session.post(
            "https://noteyd.chaoxing.com/pc/note_draft/addOrUpdateNoteDraft",
            params={"cid": note_id},
            data={
                "draftCid": note_id,
                "noteCid": note_id,
                "title": str(note.get("title") or "").strip(),
                "content": "" if resource_only else content,
                "files_url": note.get("files_url") or note.get("filesUrl") or "",
                "attachment": note.get("attachment") or "",
                "rtf_content": "" if resource_only else rtf_content,
                "encode": 0,
                "isRichText": 1,
                "isCooperate": 0,
                "notebookCid": notebook_id,
                "extension": note.get("extension") or json.dumps({
                    "cooperateVersion": 1,
                    "storeType": "2",
                    "useMySQL": True,
                }, ensure_ascii=False),
                "isNewNote": note.get("isNewNote", 1),
                "coopResource": (
                    note.get("coopResource") or ""
                    if self._uses_resource_note(note) else ""
                ),
                "sort": note.get("sort") or "",
                "cooperatorPuids": note.get("cooperatorPuids") or "",
                "openInviteSign": note.get("openInviteSign", 0),
                "isCover": 1,
            },
            headers=self._note_request_headers(
                f"https://noteyd.chaoxing.com/pc/{note_id}"
                "?isEdit=1&type=2&from=fetchAdjacent"
            ),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("result") not in (1, True, "1", "true", "True"):
            raise RuntimeError(payload.get("msg") or "草稿保存失败")
        return payload

    @staticmethod
    def _extract_coop_resource(payload):
        if not isinstance(payload, dict):
            return ""
        message = payload.get("msg")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                message = None
        candidates = [message, payload.get("data")]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            resources = candidate.get("coopResource")
            if isinstance(resources, str) and resources:
                return resources
            if isinstance(resources, list):
                for resource in resources:
                    value = resource.get("value") if isinstance(resource, dict) else None
                    if isinstance(value, dict) and value.get("data"):
                        return value["data"]
        return ""

    @staticmethod
    def _note_request_headers(referer):
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://noteyd.chaoxing.com",
            "Pragma": "no-cache",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                "Safari/537.36"
            ),
        }

    def _save_note_remote(self, note, content, rtf_content=None):
        note_id = self._note_id(note)
        if not note_id:
            raise RuntimeError("笔记数据中缺少笔记 ID，无法保存")

        coop_resource = note.get("coopResource") or ""
        if not self._uses_resource_note(note):
            coop_resource = ""
        if self._uses_resource_note(note) and not coop_resource:
            raise RuntimeError(
                "该公开笔记使用协作富文本格式，但列表数据没有返回 coopResource；"
                "仅提交 content 不会更新学习通中的正文。"
            )
        is_cooperate = 1 if self._is_cooperate_note(note) else 0

        title = str(note.get("title") or "").strip()
        notebook_id = str(
            note.get("notebookCid") or note.get("notebookId") or self.notebook_id
        )
        form_data = {
            "title": title,
            "encode": 0,
            "content": "" if self._is_cooperate_note(note) else content,
            "files_url": note.get("files_url") or note.get("filesUrl") or "",
            "attachment": note.get("attachment") or "",
            "rtf_content": (
                "" if self._is_cooperate_note(note) else (
                    rtf_content if rtf_content is not None else content
                )
            ),
            "_t": int(datetime.now().timestamp() * 1000),
            "isRichText": 1,
            "isCooperate": is_cooperate,
            "notebookCid": notebook_id,
            "extension": note.get("extension") or json.dumps({
                "cooperateVersion": 1,
                "storeType": "2",
                "useMySQL": True,
            }, ensure_ascii=False),
            "isNewNote": note.get("isNewNote", 1),
            "coopResource": coop_resource,
            "sort": note.get("sort") or "",
            "cooperatorPuids": note.get("cooperatorPuids") or "",
            "openInviteSign": note.get("openInviteSign", 0),
        }
        response = self.crawler.session.post(
            f"https://noteyd.chaoxing.com/pc/note_note/{note_id}/noteEditLatest",
            data=form_data,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://noteyd.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": (
                    f"https://noteyd.chaoxing.com/pc/{note_id}"
                    "?isEdit=1&type=2&from=fetchAdjacent"
                ),
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            },
            timeout=15,
        )
        if response.status_code == 403:
            raise RuntimeError(
                "服务器拒绝保存请求(403)，请确认当前登录会话仍有效，"
                "且笔记 ID 为 UUID。"
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("result") not in (1, True, "1", "true", "True"):
            raise RuntimeError(payload.get("msg") or "服务器未确认保存成功")

    @staticmethod
    def _note_id(note):
        candidates = []
        for key in ("noteCid", "note_id", "noteId", "uuid", "cid", "id"):
            value = note.get(key)
            if value:
                candidates.append(str(value))
        for value in candidates:
            if re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value
            ):
                return value
        for value in candidates:
            if not value.isdigit():
                return value
        return candidates[0] if candidates else ""

    def _refresh_note_card(self, note, plain_content=None):
        content = " ".join(str(plain_content if plain_content is not None else note.get("content") or "").split())
        if len(content) > 180:
            content = content[:180] + "..."
        for note_list in self.lists:
            for index in range(note_list.count()):
                item = note_list.item(index)
                if NotesView._note_id(item.data(32) or {}) != NotesView._note_id(note):
                    continue
                card = note_list.itemWidget(item)
                if card is None:
                    continue
                content_label = card.findChild(QLabel, "note_content")
                if content_label is not None:
                    content_label.setText(content)
                return

    @staticmethod
    def _note_detail_stylesheet(palette):
        return f"""
            QDialog {{
                background-color: {palette.panel_bg};
            }}
            QLabel#note_detail_title {{
                color: {palette.text};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#note_detail_meta {{
                color: {palette.text_muted};
                font-size: 12px;
            }}
            QTextEdit#note_detail_content {{
                background-color: {palette.card_bg};
                color: {palette.text_secondary};
                border: 1px solid {palette.border};
                border-radius: 6px;
                padding: 10px;
                font-size: 14px;
            }}
            QPushButton#note_save_button {{
                background-color: {palette.accent};
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 8px 22px;
                font-weight: bold;
            }}
            QPushButton#note_save_button:hover {{
                background-color: {palette.accent_hover};
            }}
        """

    @staticmethod
    def _create_note_widget(note):
        title = str(note.get("title") or "无标题").strip()
        content = str(
            note.get("content") or note.get("contentTxt") or note.get("rtf_content") or ""
        ).strip()
        content = " ".join(content.split())
        if len(content) > 180:
            content = content[:180] + "..."
        time_text = str(note.get("ftime") or note.get("createTime") or "")
        read_count = note.get("readCount", note.get("s_readcount", 0))

        card = NoteCard()
        card.setObjectName("note_card")
        card.setMinimumHeight(92)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("note_title")
        title_label.setWordWrap(True)
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        card_layout.addWidget(title_label)

        if content:
            content_label = QLabel(content)
            content_label.setObjectName("note_content")
            content_label.setWordWrap(True)
            content_label.setMaximumHeight(42)
            content_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            card_layout.addWidget(content_label)

        if time_text or read_count:
            meta_label = QLabel(f"{time_text}  ·  阅读 {read_count}")
            meta_label.setObjectName("note_meta")
            meta_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            card_layout.addWidget(meta_label)

        apply_theme_stylesheet(card, NotesView._note_card_stylesheet)
        return card

    def stop_workers(self):
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.requestInterruption()
            self.load_thread.quit()
            self.load_thread.wait(3000)
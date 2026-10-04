"""笔记列表视图。"""

import re
import json
import uuid
from datetime import datetime
from html import unescape

from PyQt6.QtCore import (
    QBuffer, QIODevice, QPoint, QThread, QTimer, QSize, Qt, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QColor, QFont, QFontMetrics, QImage, QPainter, QPalette, QPen,
    QTextCharFormat, QTextCursor, QTextDocument, QTextImageFormat,
)
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QButtonGroup, QFrame, QLineEdit, QMessageBox, QSpinBox, QTabWidget, QTextEdit,
    QMenu, QToolBar, QVBoxLayout, QWidget,
)

from core.coop_resource_encoder import CoopResourceEncoder
from ui.theme import apply_theme_stylesheet, bind_theme_tree


class NotesLoadThread(QThread):
    """在后台请求笔记列表，避免阻塞主界面。"""

    loaded = pyqtSignal(int, list, dict, dict)
    failed = pyqtSignal(int, str)

    def __init__(self, crawler, index, user_id, notebook_id, parent_id, folder_cid):
        super().__init__()
        self.crawler = crawler
        self.index = index
        self.user_id = user_id
        self.notebook_id = notebook_id
        self.parent_id = parent_id
        self.folder_cid = folder_cid

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
                self.loaded.emit(self.index, notes, {}, {})
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
            for query_id in (
                self.folder_cid, self.parent_id, category_id, "root"
            ):
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
                        folder_paths, folder_counts, folder_ids = self._load_folder_paths(
                            session, self.folder_cid, headers
                        )
                        for note in notes:
                            if not isinstance(note, dict):
                                continue
                            note_id = self._note_id(note)
                            folder_id = str(
                                note.get("notebookCid") or note.get("pcid") or ""
                            )
                            note["folder_name"] = (
                                folder_paths.get(note_id)
                                or folder_paths.get(folder_id)
                                or "未分类"
                            )
                        self._hydrate_cooperate_notes(session, notes, headers)
                        self.loaded.emit(
                            self.index, notes, folder_counts, folder_ids
                        )
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

    @classmethod
    def _load_folder_paths(cls, session, notebook_cid, headers):
        paths = {}
        folder_counts = {}
        folder_ids = {}
        visited = set()

        def load_folder(folder_cid, parent_path=""):
            if not folder_cid or folder_cid in visited:
                return
            visited.add(folder_cid)
            try:
                response = session.get(
                    "https://noteyd.chaoxing.com/pc/note_notebook/getNotebooksLatest",
                    params={
                        "querySubFolder": 0,
                        "notebookCid": folder_cid,
                        "kw": "",
                        "offsetValue": "",
                        "top": 0,
                        "pageSize": 100,
                        "showCollection": 0,
                        "_t": datetime.now().day,
                    },
                    headers=headers,
                    timeout=15,
                )
                response.raise_for_status()
                payload = response.json()
                message = payload.get("msg") if isinstance(payload, dict) else None
                if not isinstance(message, dict):
                    return
                current = message.get("curNoteBook") or {}
                current_name = str(current.get("name") or folder_cid)
                current_path = (
                    f"{parent_path} / {current_name}" if parent_path else current_name
                )
                paths[str(folder_cid)] = current_path
                folder_ids[current_path] = str(folder_cid)
                folder_counts[current_path] = int(current.get("note_count") or 0)
                for item in message.get("list") or []:
                    if not isinstance(item, dict):
                        continue
                    item_cid = str(item.get("cid") or "")
                    if item_cid:
                        item_name = str(item.get("name") or item_cid)
                        item_path = f"{current_path} / {item_name}"
                        paths[item_cid] = item_path
                        folder_ids[item_path] = item_cid
                        folder_counts[item_path] = int(item.get("count") or 0)
                    if item_cid:
                        load_folder(item_cid, current_path)
            except Exception:
                return

        load_folder(str(notebook_cid))
        return paths, folder_counts, folder_ids

    @staticmethod
    def _note_id(note):
        for key in ("noteCid", "note_id", "noteId", "uuid", "cid", "id"):
            value = note.get(key)
            if value:
                return str(value)
        return ""


class NoteImageUploadThread(QThread):
    """Upload a pasted image to Chaoxing's note cloud storage."""

    uploaded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, session, image_bytes, parent=None):
        super().__init__(parent)
        self.session = session
        self.image_bytes = image_bytes

    def run(self):
        try:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Referer": "https://noteyd.chaoxing.com/pc/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            }
            response = self.session.get(
                "https://noteyd.chaoxing.com/proxy/apis/common/getYunPanUploadUrl",
                params={"crossOrigin": "true", "from": "note"},
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            upload_payload = response.json()
            upload_url = upload_payload.get("data")
            if not upload_url:
                raise RuntimeError(upload_payload.get("msg") or "未获取到图片上传地址")

            upload_response = self.session.post(
                upload_url,
                files={"file": ("image.png", self.image_bytes, "image/png")},
                headers=headers,
                timeout=30,
            )
            upload_response.raise_for_status()
            payload = upload_response.json()
            image_data = payload.get("data") or {}
            if not isinstance(image_data, dict):
                raise RuntimeError("图片上传接口返回格式错误")
            preview_url = image_data.get("previewUrl") or image_data.get("preview")
            object_id = image_data.get("objectId") or image_data.get("objectid")
            if not preview_url or not object_id:
                raise RuntimeError(payload.get("msg") or "图片上传成功但缺少图片资源信息")
            preview_response = self.session.get(
                preview_url,
                headers=headers,
                timeout=30,
            )
            preview_response.raise_for_status()
            if not preview_response.content:
                raise RuntimeError("图片已上传，但远程预览资源为空")
            self.uploaded.emit({
                "object_id": str(object_id),
                "preview_url": str(preview_url),
                "resid": str(image_data.get("resid") or ""),
                "remote_image_bytes": preview_response.content,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class NoteImageLoadThread(QThread):
    """Download existing note images for the QTextDocument resource cache."""

    image_loaded = pyqtSignal(str, bytes)

    def __init__(self, session, image_urls, parent=None):
        super().__init__(parent)
        self.session = session
        self.image_urls = image_urls

    def run(self):
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://noteyd.chaoxing.com/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 "
                "Safari/537.36"
            ),
        }
        for image_url in self.image_urls:
            try:
                response = self.session.get(
                    image_url, headers=headers, timeout=20
                )
                response.raise_for_status()
                if response.content:
                    self.image_loaded.emit(image_url, response.content)
            except Exception:
                continue


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


class ImageResizeOverlay(QWidget):
    """Draw an image selection frame and provide a bottom-right resize handle."""

    resized = pyqtSignal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._dragging = False
        self._start_pos = None
        self._start_global_pos = None
        self._start_global_left = None
        self._start_width = 0
        self._start_height = 0
        self._handle_size = 16

    def set_image_size(self, width, height):
        self._start_width = max(1, int(width))
        self._start_height = max(1, int(height))
        self.update()

    def _handle_rect(self):
        size = self._handle_size
        return self.rect().adjusted(
            self.width() - size - 1,
            self.height() - size - 1,
            -1,
            -1,
        )

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#007acc"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#007acc"))
        painter.drawRect(self._handle_rect())

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._handle_rect().contains(event.position().toPoint()):
            self._dragging = True
            self._start_pos = event.position().toPoint()
            self._start_global_pos = event.globalPosition().toPoint()
            overlay_global = self.mapToGlobal(QPoint(0, 0))
            self._start_global_left = overlay_global.x()
            event.accept()
            return
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
                if self._handle_rect().contains(event.position().toPoint())
                else Qt.CursorShape.ArrowCursor
            )
            return
        if not self._dragging or self._start_global_pos is None:
            return
        point = event.globalPosition().toPoint()
        width = max(80, point.x() - (self._start_global_left or point.x()))
        height = max(40, round(width * self._start_height / self._start_width))
        self.resized.emit(width, height, point.x())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._start_pos = None
            self._start_global_pos = None
            self._start_global_left = None
            event.accept()

    def leaveEvent(self, event):
        self.unsetCursor()
        if self.parentWidget() is not None:
            self.parentWidget().setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class MarkdownTextEdit(QTextEdit):
    """提供 Markdown 标题的即时转换。"""

    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    HEADING_SIZES = {1: 22, 2: 18, 3: 16, 4: 15, 5: 14, 6: 14}
    COMPOSER_TITLE_SIZE = 18
    image_paste_requested = pyqtSignal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_image_cursor = None
        self._image_boundary_action = None
        self._boundary_image_cursor = None
        self._image_overlay = ImageResizeOverlay(self.viewport())
        self._image_overlay.hide()
        self._image_overlay.resized.connect(self._resize_selected_image)

    def _image_cursor_at(self, position):
        cursor = self.cursorForPosition(position)
        candidates = []
        if cursor.position() > 0:
            previous = QTextCursor(cursor)
            previous.setPosition(cursor.position() - 1)
            candidates.append(previous)
        if cursor.charFormat().isImageFormat():
            candidates.append(cursor)
        if cursor.position() < self.document().characterCount() - 1:
            following = QTextCursor(cursor)
            following.setPosition(cursor.position() + 1)
            candidates.append(following)
        for candidate in candidates:
            if (
                candidate.position() < self.document().characterCount() - 1
                and candidate.charFormat().isImageFormat()
            ):
                width, height = self._image_size(candidate)
                image_x, image_y, image_width, image_height = self._image_viewport_rect(
                    candidate, width, height
                )
                if (
                    image_x <= position.x() <= image_x + image_width
                    and image_y <= position.y() <= image_y + image_height
                ):
                    return candidate
        return None

    @staticmethod
    def _image_size(cursor):
        image_format = cursor.charFormat().toImageFormat()
        width = image_format.width()
        height = image_format.height()
        if width > 0 and height > 0:
            return width, height
        return 320, 180

    def _image_viewport_rect(self, cursor, width, height):
        block = cursor.block()
        layout = block.layout()
        block_rect = self.document().documentLayout().blockBoundingRect(block)
        position_in_block = cursor.position() - block.position()
        line = layout.lineForTextPosition(max(0, position_in_block))
        if not line.isValid():
            cursor_rect = self.cursorRect(cursor)
            return cursor_rect.x(), cursor_rect.y(), width, height

        cursor_x = line.cursorToX(max(0, position_in_block))
        if isinstance(cursor_x, tuple):
            cursor_x = cursor_x[0]
        image_x = block_rect.x() + line.x() + cursor_x
        image_y = block_rect.y() + line.y() + line.ascent() - height
        offset_x = self.horizontalScrollBar().value()
        offset_y = self.verticalScrollBar().value()
        return image_x - offset_x, image_y - offset_y, width, height

    def _show_image_editor(self, cursor):
        self._selected_image_cursor = QTextCursor(cursor)
        width, height = self._image_size(cursor)
        image_x, image_y, image_width, image_height = self._image_viewport_rect(
            cursor, width, height
        )
        self._image_overlay.set_image_size(width, height)
        self._image_overlay.setGeometry(
            round(image_x),
            round(image_y),
            round(image_width),
            round(image_height),
        )
        self._image_overlay.setCursor(Qt.CursorShape.ArrowCursor)
        self._image_overlay.show()
        self._image_overlay.raise_()

    def _hide_image_editor(self):
        self._selected_image_cursor = None
        self._image_overlay.hide()

    def _composer_separator_y(self):
        first_block = self.document().firstBlock()
        second_block = first_block.next()
        if second_block.isValid():
            second_rect = self.cursorRect(QTextCursor(second_block))
            return second_rect.top() - 4
        first_rect = self.cursorRect(QTextCursor(first_block))
        return first_rect.top() + QFontMetrics(self.font()).height() + 8

    def _resize_selected_image(self, width, height, _mouse_x=None):
        if self._selected_image_cursor is None:
            return
        cursor = QTextCursor(self._selected_image_cursor)
        image_format = cursor.charFormat().toImageFormat()
        image_format.setWidth(width)
        image_format.setHeight(height)
        image_position = cursor.position()
        last_position = self.document().characterCount() - 1
        if image_position >= last_position:
            return
        cursor.setPosition(
            min(image_position + 1, last_position),
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.setCharFormat(image_format)
        cursor.clearSelection()
        cursor.setPosition(image_position)
        self._selected_image_cursor = cursor
        self._show_image_editor(cursor)

    def _set_image_alignment(self, alignment):
        if self._selected_image_cursor is None:
            return
        cursor = self._isolate_image_block(self._selected_image_cursor)
        block_format = cursor.blockFormat()
        block_format.setAlignment(alignment)
        cursor.setBlockFormat(block_format)
        self._selected_image_cursor = cursor
        self._show_image_editor(cursor)

    def _isolate_image_block(self, image_cursor):
        cursor = QTextCursor(image_cursor)
        document = self.document()
        image_position = (
            cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        )
        cursor.setPosition(image_position)
        block = cursor.block()
        block_start = block.position()
        block_end = block_start + block.length() - 1

        if image_position + 1 < block_end:
            split_after = QTextCursor(document)
            split_after.setPosition(image_position + 1)
            split_after.insertBlock()
        if image_position > block_start:
            split_before = QTextCursor(document)
            split_before.setPosition(image_position)
            split_before.insertBlock()
            image_position += 1

        image_position = min(image_position, document.characterCount() - 2)
        image_block_cursor = QTextCursor(document)
        image_block_cursor.setPosition(max(0, image_position))
        image_block = image_block_cursor.block()
        image_block_format = image_block.blockFormat()
        image_block_format.setTopMargin(8)
        image_block_format.setBottomMargin(8)
        image_block_cursor.setBlockFormat(image_block_format)
        if not image_block.next().isValid():
            split_after = QTextCursor(document)
            split_after.setPosition(image_position + 1)
            split_after.insertBlock()

        for text_block in (image_block.previous(), image_block.next()):
            if text_block.isValid():
                text_cursor = QTextCursor(text_block)
                text_format = text_block.blockFormat()
                text_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
                text_cursor.setBlockFormat(text_format)

        isolated_cursor = QTextCursor(document)
        isolated_cursor.setPosition(max(0, image_position))
        return isolated_cursor

    @staticmethod
    def _block_contains_image(block):
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                return True
            iterator += 1
        return False

    def _image_row_at(self, y):
        return self._image_at_row(y) is not None

    def _image_at_row(self, y):
        scroll_offset = self.verticalScrollBar().value()
        block = self.document().firstBlock()
        layout = self.document().documentLayout()
        while block.isValid():
            if self._block_contains_image(block):
                block_rect = layout.blockBoundingRect(block)
                row_top = block_rect.top() - scroll_offset
                row_bottom = block_rect.bottom() - scroll_offset
                if row_top <= y <= row_bottom:
                    iterator = block.begin()
                    while not iterator.atEnd():
                        fragment = iterator.fragment()
                        if fragment.isValid() and fragment.charFormat().isImageFormat():
                            image_cursor = QTextCursor(self.document())
                            image_cursor.setPosition(fragment.position())
                            width, height = self._image_size(image_cursor)
                            image_rect = self._image_viewport_rect(
                                image_cursor, width, height
                            )
                            return image_cursor, image_rect
                        iterator += 1
            block = block.next()
        return None

    def _move_cursor_out_of_image_block(self):
        cursor = self.textCursor()
        if cursor.hasSelection() or not self._block_contains_image(cursor.block()):
            return False

        image_block = cursor.block()
        following_block = image_block.next()
        if not following_block.isValid():
            end_cursor = QTextCursor(image_block)
            end_cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            end_cursor.insertBlock()
            following_block = image_block.next()
        self.setTextCursor(QTextCursor(following_block))
        return True

    def _delete_selected_image(self):
        if self._selected_image_cursor is None:
            return
        cursor = QTextCursor(self._selected_image_cursor)
        cursor.deleteChar()
        self._hide_image_editor()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            image_row = self._image_at_row(round(event.position().y()))
            if image_row is not None:
                image_cursor, image_rect = image_row
                image_cursor = self._isolate_image_block(image_cursor)
                self._boundary_image_cursor = QTextCursor(image_cursor)
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                image_x, _image_y, image_width, _image_height = image_rect
                click_x = event.position().x()
                if click_x < image_x:
                    self._hide_image_editor()
                    cursor = QTextCursor(image_cursor.block())
                    self.setTextCursor(cursor)
                    self._image_boundary_action = "before"
                    event.accept()
                    return
                if click_x > image_x + image_width:
                    self._hide_image_editor()
                    cursor = QTextCursor(image_cursor)
                    cursor.setPosition(image_cursor.block().position() + 1)
                    self.setTextCursor(cursor)
                    self._image_boundary_action = "after"
                    event.accept()
                    return
                self._image_boundary_action = None
                self._boundary_image_cursor = None
                self._show_image_editor(image_cursor)
                self.clearFocus()
                event.accept()
                return

            self._image_boundary_action = None
            self._boundary_image_cursor = None
            if getattr(self, "_note_composer_mode", False):
                separator_y = self._composer_separator_y()
                if event.position().y() >= separator_y:
                    body_block = self.document().firstBlock().next()
                    if body_block.isValid():
                        cursor = self.cursorForPosition(event.position().toPoint())
                        if cursor.block() == self.document().firstBlock():
                            cursor.setPosition(body_block.position())
                            self.setTextCursor(cursor)
                            self._move_cursor_out_of_image_block()
                            event.accept()
                            return
            image_cursor = self._image_cursor_at(event.position().toPoint())
            if image_cursor is not None:
                self._show_image_editor(image_cursor)
            else:
                self._hide_image_editor()
        super().mousePressEvent(event)
        self._move_cursor_out_of_image_block()

    def mouseDoubleClickEvent(self, event):
        point = event.position().toPoint()
        cursor = self.cursorForPosition(point)
        previous_block = cursor.block().previous()
        if self._block_contains_image(previous_block):
            image_cursor = None
            iterator = previous_block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image_cursor = QTextCursor(self.document())
                    image_cursor.setPosition(fragment.position())
                    break
                iterator += 1
            if image_cursor is not None:
                width, height = self._image_size(image_cursor)
                _image_x, image_y, _image_width, _image_height = (
                    self._image_viewport_rect(image_cursor, width, height)
                )
                if point.y() >= image_y + height:
                    self._image_boundary_action = None
                    self._boundary_image_cursor = None
                    self._hide_image_editor()
                    cursor.clearSelection()
                    self.setTextCursor(cursor)
                    self.setFocus(Qt.FocusReason.MouseFocusReason)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        self.viewport().setCursor(
            Qt.CursorShape.ArrowCursor
            if self._image_row_at(round(event.position().y()))
            else Qt.CursorShape.IBeamCursor
        )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().leaveEvent(event)

    def focusOutEvent(self, event):
        self._image_boundary_action = None
        self._boundary_image_cursor = None
        super().focusOutEvent(event)

    def contextMenuEvent(self, event):
        image_cursor = self._image_cursor_at(event.pos())
        if image_cursor is None:
            super().contextMenuEvent(event)
            return

        self._show_image_editor(image_cursor)
        self.clearFocus()
        menu = QMenu(self)
        left_action = menu.addAction("左对齐")
        center_action = menu.addAction("居中")
        right_action = menu.addAction("右对齐")
        menu.addSeparator()
        delete_action = menu.addAction("删除图片")
        left_action.triggered.connect(
            lambda: self._set_image_alignment(Qt.AlignmentFlag.AlignLeft)
        )
        center_action.triggered.connect(
            lambda: self._set_image_alignment(Qt.AlignmentFlag.AlignCenter)
        )
        right_action.triggered.connect(
            lambda: self._set_image_alignment(Qt.AlignmentFlag.AlignRight)
        )
        delete_action.triggered.connect(self._delete_selected_image)
        menu.exec(self.viewport().mapToGlobal(event.pos()))

    def enable_note_composer_mode(self):
        self._note_composer_mode = True
        self.setPlaceholderText("")
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not getattr(self, "_note_composer_mode", False):
            return
        first_block = self.document().firstBlock()
        if not first_block.isValid() or not first_block.next().isValid():
            return
        cursor_rect = self.cursorRect(QTextCursor(first_block))
        title_font = self.font()
        title_font.setPointSize(self.COMPOSER_TITLE_SIZE)
        title_metrics = QFontMetrics(title_font)
        separator_y = self._composer_separator_y()
        painter = QPainter(self.viewport())
        painter.setPen(
            QPen(self.palette().color(QPalette.ColorRole.Highlight), 1)
        )
        painter.drawLine(10, separator_y, self.viewport().width() - 10, separator_y)

        raw_text = self.toPlainText()
        title = raw_text.split("\n", 1)[0]
        placeholder_color = self.palette().color(QPalette.ColorRole.PlaceholderText)
        if not title:
            painter.setPen(placeholder_color)
            title_font = self.font()
            title_font.setPointSize(self.COMPOSER_TITLE_SIZE)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.drawText(
                12,
                cursor_rect.top() + title_metrics.ascent() + 2,
                "请输入标题",
            )

    def insertFromMimeData(self, source):
        if self._image_boundary_action is not None:
            return
        self._move_cursor_out_of_image_block()
        if source.hasImage():
            image_data = source.imageData()
            image = image_data if isinstance(image_data, QImage) else image_data.toImage()
            if not image.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if image.save(buffer, "PNG"):
                    self.image_paste_requested.emit(bytes(buffer.data()))
                    return
        super().insertFromMimeData(source)

    def inputMethodEvent(self, event):
        if self._image_boundary_action is not None:
            event.accept()
            return
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if self._image_boundary_action is not None:
            if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                event.accept()
                return
            image_cursor = self._boundary_image_cursor
            if image_cursor is not None:
                if self._image_boundary_action == "before":
                    cursor = self.textCursor()
                    cursor.insertBlock()
                    previous_block = image_cursor.block().previous()
                    if previous_block.isValid():
                        block_format = previous_block.blockFormat()
                        block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
                        paragraph_cursor = QTextCursor(previous_block)
                        paragraph_cursor.setBlockFormat(block_format)
                        paragraph_cursor.movePosition(
                            QTextCursor.MoveOperation.StartOfBlock
                        )
                        self.setTextCursor(paragraph_cursor)
                else:
                    following_block = image_cursor.block().next()
                    if following_block.isValid():
                        self.setTextCursor(QTextCursor(following_block))
            self._image_boundary_action = None
            self._boundary_image_cursor = None
            event.accept()
            return

        self._move_cursor_out_of_image_block()
        cursor = self.textCursor()
        if (
            event.key() == Qt.Key.Key_Backspace
            and not cursor.hasSelection()
            and cursor.position() == cursor.block().position()
            and self._block_contains_image(cursor.block().previous())
        ):
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._convert_current_heading():
                super().keyPressEvent(event)
                self._clear_heading_level()
                self._move_cursor_out_of_image_block()
                return
        super().keyPressEvent(event)
        self._move_cursor_out_of_image_block()

    def convert_all_headings(self):
        cursor = QTextCursor(self.document())
        block = self.document().firstBlock()
        while block.isValid():
            match = self.HEADING_PATTERN.match(block.text())
            if match:
                block_cursor = QTextCursor(block)
                block_cursor.setPosition(block.position())
                block_cursor.setPosition(
                    block.position() + len(block.text()),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                block_cursor.insertText(match.group(2))
                self._apply_heading_format(block_cursor, block.position(), len(match.group(2)), len(match.group(1)))
            block = block.next()

    def _convert_current_heading(self):
        cursor = self.textCursor()
        text = cursor.block().text()
        if cursor.positionInBlock() != len(text):
            return False
        match = self.HEADING_PATTERN.match(text)
        if not match:
            return False

        block_cursor = QTextCursor(cursor.block())
        block_cursor.setPosition(cursor.block().position())
        block_cursor.setPosition(
            cursor.block().position() + len(text),
            QTextCursor.MoveMode.KeepAnchor,
        )
        block_cursor.insertText(match.group(2))
        self._apply_heading_format(
            block_cursor,
            cursor.block().position(),
            len(match.group(2)),
            len(match.group(1)),
        )
        block_cursor.setPosition(
            cursor.block().position() + len(match.group(2))
        )
        self.setTextCursor(block_cursor)
        return True

    def _clear_heading_level(self):
        cursor = self.textCursor()
        block_format = cursor.blockFormat()
        block_format.setHeadingLevel(0)
        cursor.setBlockFormat(block_format)
        char_format = QTextCharFormat()
        char_format.setFontPointSize(14)
        char_format.setFontWeight(400)
        cursor.setCharFormat(char_format)
        self.setTextCursor(cursor)

    def _apply_heading_format(self, cursor, block_position, text_length, level):
        cursor.setPosition(block_position)
        cursor.setPosition(
            block_position + text_length,
            QTextCursor.MoveMode.KeepAnchor,
        )
        char_format = QTextCharFormat()
        char_format.setFontPointSize(self.HEADING_SIZES.get(level, 14))
        char_format.setFontWeight(700)
        cursor.setCharFormat(char_format)
        cursor.clearSelection()
        block_format = cursor.blockFormat()
        block_format.setHeadingLevel(level)
        cursor.setBlockFormat(block_format)


class NotesView(QWidget):
    """直接请求超星笔记接口并在应用内展示列表。"""

    NOTE_HOME_URL = "https://noteyd.chaoxing.com/pc/note_notebook/myNotebooksLatest"
    NOTEBOOK_ID_FALLBACK = "bb551915d9e7d5a86071cdfeb91dc755"
    TAB_NAMES = ("公开笔记", "个人笔记", "推荐")
    TAB_LABELS = ("🌐 公开笔记", "👤 个人笔记", "⭐ 推荐")

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.user_id = ""
        self.notebook_id = ""
        self.parent_id = "root"
        self.load_thread = None
        self._resource_encoder = None
        self._note_preview_cache = {}
        self._active_folder_cids = {0: None, 1: None, 2: None}
        self._active_folder_paths = {0: None, 1: None, 2: None}
        self._folder_stacks = {0: [], 1: [], 2: []}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.category_buttons = QButtonGroup(self)
        self.category_buttons.setExclusive(True)
        for index, label in enumerate(self.TAB_LABELS):
            category_button = QPushButton(label)
            category_button.setCheckable(True)
            category_button.setCursor(Qt.CursorShape.PointingHandCursor)
            category_button.setMinimumHeight(28)
            apply_theme_stylesheet(category_button, """
                QPushButton {
                    background-color: #3e3e42;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 5px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #4e4e52;
                    border: 1px solid #007acc;
                }
                QPushButton:checked {
                    background-color: #007acc;
                    border: 1px solid #007acc;
                }
            """)
            self.category_buttons.addButton(category_button, index)
            header.addWidget(category_button)

        self.category_buttons.idClicked.connect(self._select_category)
        self.category_buttons.button(0).setChecked(True)
        header.addStretch()

        self.create_button = QPushButton("📝 写笔记")
        self.create_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_button.setMinimumHeight(28)
        apply_theme_stylesheet(self.create_button, """
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005c99;
            }
        """)
        self.create_button.clicked.connect(self._create_note)
        header.addWidget(self.create_button)

        self.refresh_button = QPushButton("🔄 刷新")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.setMinimumHeight(28)
        apply_theme_stylesheet(self.refresh_button, """
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                border: 1px solid #007acc;
            }
        """)
        self.refresh_button.clicked.connect(self.refresh_current)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        breadcrumb_bar = QWidget()
        breadcrumb_bar.setObjectName("breadcrumb_bar")
        self.breadcrumb_layout = QHBoxLayout(breadcrumb_bar)
        self.breadcrumb_layout.setContentsMargins(4, 0, 4, 0)
        self.breadcrumb_layout.setSpacing(2)
        apply_theme_stylesheet(breadcrumb_bar, lambda palette: f"""
            QWidget#breadcrumb_bar {{
                background-color: {palette.panel_alt_bg};
                border: 1px solid {palette.border};
                border-radius: 5px;
            }}
        """)
        layout.addWidget(breadcrumb_bar)
        self._render_breadcrumb(0)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)
        self.lists = []
        for name in self.TAB_NAMES:
            note_list = QListWidget()
            apply_theme_stylesheet(note_list, self._note_list_stylesheet)
            note_list.setWordWrap(True)
            note_list.setSpacing(0)
            note_list.setAlternatingRowColors(False)
            note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            note_list.customContextMenuRequested.connect(
                lambda position, current_list=note_list:
                self._show_note_context_menu(current_list, position)
            )
            note_list.itemDoubleClicked.connect(
                lambda item, current_list=note_list:
                self._open_folder(current_list, item)
            )
            note_list.currentItemChanged.connect(
                lambda current, _previous, current_list=note_list:
                self._sync_note_selection(current_list, current)
            )
            self.lists.append(note_list)
            self.tabs.addTab(note_list, self.TAB_LABELS[len(self.lists) - 1])
        self.tabs.setCurrentIndex(0)
        self.tabs.currentChanged.connect(self.load_current)
        layout.addWidget(self.tabs)
        self.summary_label = QLabel("请选择一个分类")
        self.summary_label.setObjectName("notes_summary")
        layout.addWidget(self.summary_label)
        self.status_label = QLabel()
        self.status_label.setObjectName("notes_status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
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
                border-bottom: 1px solid {palette.border};
                padding: 0;
                margin: 0;
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
    def _note_menu_stylesheet(palette):
        return f"""
            QMenu {{
                background-color: {palette.hover_bg};
                color: {palette.text_secondary};
                border: 1px solid {palette.border_strong};
                border-radius: 6px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 8px 25px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {palette.accent};
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {palette.border_strong};
                margin: 5px 10px;
            }}
        """

    @staticmethod
    def _note_card_stylesheet(palette):
        return f"""
            QWidget#note_card {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {palette.border};
                border-radius: 0;
            }}
            QWidget#note_card[selected="true"] {{
                background-color: {palette.hover_bg};
                border-bottom: 1px solid {palette.accent};
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

    def _create_note(self):
        try:
            self._prepare_context()
        except Exception as exc:
            QMessageBox.warning(self, "创建失败", f"无法获取笔记配置: {exc}")
            return

        self._show_note_composer()

    def _show_note_composer(self, note=None):
        is_new_note = note is None
        dialog = QDialog(self)
        dialog.setWindowTitle("创建笔记" if is_new_note else "编辑笔记")
        main_size = self.window().size()
        screen = dialog.screen()
        available_size = (
            screen.availableGeometry().size() if screen else main_size
        )
        dialog.resize(
            min(max(800, int(main_size.width() * 0.85)), int(available_size.width() * 0.9)),
            min(max(600, int(main_size.height() * 0.85)), int(available_size.height() * 0.9)),
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        composer_panel = QWidget()
        composer_panel.setObjectName("note_composer")
        composer_layout = QVBoxLayout(composer_panel)
        composer_layout.setContentsMargins(12, 8, 12, 10)
        composer_layout.setSpacing(0)

        title_edit = QLineEdit()
        title_edit.setObjectName("note_composer_title")
        title_edit.setPlaceholderText("请输入标题")
        title_edit.setMinimumHeight(42)
        if not is_new_note:
            title_edit.setText(str(note.get("title") or ""))
        composer_layout.addWidget(title_edit)

        separator = QFrame()
        separator.setObjectName("note_composer_separator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFixedHeight(1)
        composer_layout.addWidget(separator)

        content_edit = MarkdownTextEdit()
        content_edit.setObjectName("note_composer_body")
        content_edit.setMinimumHeight(420)
        if not is_new_note:
            content = str(
                note.get("rtf_content")
                or note.get("content")
                or note.get("contentTxt")
                or ""
            ).strip()
            if re.search(r"<[a-zA-Z][^>]*>", content):
                content_edit.setHtml(content)
                self._load_note_image_resources(content_edit)
            else:
                content_edit.setPlainText(content)
        content_edit.image_paste_requested.connect(
            lambda image_bytes: self._upload_pasted_image(content_edit, image_bytes)
        )
        composer_layout.addWidget(content_edit)
        title_edit.returnPressed.connect(
            lambda: self._focus_note_composer(content_edit)
        )

        apply_theme_stylesheet(composer_panel, lambda palette: f"""
            QWidget#note_composer {{
                background-color: {palette.card_bg};
                border: 1px solid {palette.border};
                border-radius: 6px;
            }}
            QLineEdit#note_composer_title {{
                background: transparent;
                color: {palette.text};
                border: none;
                padding: 2px 4px;
                font-size: 18px;
                font-weight: 600;
            }}
            QFrame#note_composer_separator {{
                background-color: {palette.border_strong};
                border: none;
            }}
            QTextEdit#note_composer_body {{
                background: transparent;
                color: {palette.text_secondary};
                border: none;
                padding: 10px 4px 4px 4px;
                font-size: 14px;
            }}
        """)
        layout.addWidget(composer_panel)
        QTimer.singleShot(0, lambda: self._focus_note_composer(content_edit))

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        save_button = QPushButton("创建" if is_new_note else "保存")
        save_button.setAutoDefault(False)
        save_button.setDefault(False)
        if is_new_note:
            save_button.clicked.connect(
                lambda: self._save_new_note(title_edit, content_edit, dialog)
            )
        else:
            save_button.clicked.connect(
                lambda: self._save_edited_note(
                    note, title_edit, content_edit, dialog
                )
            )
        action_layout.addWidget(save_button)
        layout.addLayout(action_layout)
        apply_theme_stylesheet(dialog, self._note_detail_stylesheet)
        dialog.exec()

    @staticmethod
    def _focus_note_composer(content_edit):
        content_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        content_edit.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _note_image_urls(document):
        image_urls = set()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image_url = fragment.charFormat().toImageFormat().name()
                    if image_url.startswith(("http://", "https://")):
                        image_urls.add(image_url)
                iterator += 1
            block = block.next()
        return sorted(image_urls)

    def _load_note_image_resources(self, content_edit):
        image_urls = self._note_image_urls(content_edit.document())
        if not image_urls:
            return

        thread = NoteImageLoadThread(
            self.crawler.session, image_urls, content_edit
        )
        if not hasattr(content_edit, "_image_load_threads"):
            content_edit._image_load_threads = []
        content_edit._image_load_threads.append(thread)
        thread.image_loaded.connect(
            lambda image_url, image_data, editor=content_edit:
            self._register_note_image_resource(editor, image_url, image_data)
        )
        thread.finished.connect(
            lambda editor=content_edit, current=thread:
            self._cleanup_note_image_thread(editor, current)
        )
        thread.start()

    @staticmethod
    def _register_note_image_resource(content_edit, image_url, image_data):
        image = QImage.fromData(image_data)
        if image.isNull():
            return
        document = content_edit.document()
        document.addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(image_url), image
        )
        document.markContentsDirty(0, document.characterCount())
        content_edit.viewport().update()

    @staticmethod
    def _cleanup_note_image_thread(content_edit, thread):
        threads = getattr(content_edit, "_image_load_threads", [])
        if thread in threads:
            threads.remove(thread)
        thread.deleteLater()

    def _upload_pasted_image(self, content_edit, image_bytes):
        marker = f"[图片上传中:{uuid.uuid4().hex}]"
        cursor = content_edit.textCursor()
        cursor.insertText(marker)
        content_edit.setTextCursor(cursor)

        thread = NoteImageUploadThread(self.crawler.session, image_bytes, content_edit)
        if not hasattr(content_edit, "_image_upload_threads"):
            content_edit._image_upload_threads = []
        content_edit._image_upload_threads.append(thread)
        thread.uploaded.connect(
            lambda image_data: self._insert_uploaded_image(
                content_edit, marker, image_data
            )
        )
        thread.failed.connect(
            lambda message: self._handle_image_upload_failure(
                content_edit, marker, message
            )
        )
        thread.finished.connect(
            lambda: self._cleanup_image_upload_thread(content_edit, thread)
        )
        thread.start()

    @staticmethod
    def _find_text_cursor(content_edit, text):
        cursor = content_edit.document().find(text)
        return None if cursor.isNull() else cursor

    def _insert_uploaded_image(self, content_edit, marker, image_data):
        cursor = self._find_text_cursor(content_edit, marker)
        if cursor is None:
            return
        marker_end = cursor.selectionEnd()
        editor_cursor = content_edit.textCursor()
        cursor_is_at_marker = editor_cursor.position() == marker_end
        cursor.removeSelectedText()
        image = QImage.fromData(image_data["remote_image_bytes"])
        if image.isNull():
            self._handle_image_upload_failure(
                content_edit, marker, "远程图片资源无法解码，未插入笔记"
            )
            return

        resource_url = QUrl(image_data["preview_url"])
        content_edit.document().addResource(
            QTextDocument.ResourceType.ImageResource, resource_url, image
        )
        image_format = QTextImageFormat()
        image_format.setName(resource_url.toString())
        display_width = min(800, image.width())
        display_height = image.height() * display_width / image.width()
        image_format.setWidth(display_width)
        image_format.setHeight(display_height)
        image_position = cursor.position()
        cursor.insertImage(image_format)
        image_cursor = QTextCursor(content_edit.document())
        image_cursor.setPosition(image_position)
        image_cursor = content_edit._isolate_image_block(image_cursor)
        if cursor_is_at_marker:
            following_block = image_cursor.block().next()
            if following_block.isValid():
                content_edit.setTextCursor(QTextCursor(following_block))

    def _handle_image_upload_failure(self, content_edit, marker, message):
        cursor = self._find_text_cursor(content_edit, marker)
        if cursor is not None:
            cursor.removeSelectedText()
        QMessageBox.warning(content_edit, "图片粘贴失败", message)

    @staticmethod
    def _cleanup_image_upload_thread(content_edit, thread):
        threads = getattr(content_edit, "_image_upload_threads", [])
        if thread in threads:
            threads.remove(thread)
        thread.deleteLater()

    def _select_category(self, index):
        self._active_folder_cids[index] = None
        self._active_folder_paths[index] = None
        self._folder_stacks[index] = []
        self._render_breadcrumb(index)
        if self.tabs.currentIndex() == index:
            self.load_current(index)
        else:
            self.tabs.setCurrentIndex(index)

    def _save_edited_note(self, note, title_edit, content_edit, dialog):
        title = title_edit.text().strip()
        if not title:
            QMessageBox.warning(dialog, "无法保存", "请输入笔记标题")
            title_edit.setFocus()
            return

        content_edit.convert_all_headings()
        note["title"] = title
        self._save_note_content(note, content_edit, dialog)

    def _save_new_note(self, title_edit, content_edit, dialog):
        title = title_edit.text().strip()
        content_edit.convert_all_headings()
        content = content_edit.toPlainText()
        if not title:
            QMessageBox.warning(dialog, "无法保存", "请输入笔记标题")
            title_edit.setFocus()
            return

        note = {
            "noteCid": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "contentTxt": content,
            "notebookCid": (
                f"gongkaibiji{self.user_id}"
                if self.tabs.currentIndex() == 0
                else f"gerenbiji{self.user_id}"
            ),
            "extension": json.dumps({"cooperateVersion": 1}, ensure_ascii=False),
            "isNewNote": 1,
        }
        rtf_content = content_edit.toHtml()
        resource_html = self._resource_editor_html(rtf_content)
        if self._resource_encoder is None:
            self._resource_encoder = CoopResourceEncoder(
                self.crawler.session, note["noteCid"], self
            )
        else:
            self._resource_encoder.set_note_cid(note["noteCid"])
        self._resource_encoder.encode(
            resource_html,
            title,
            on_encoded=lambda resource: self._finish_new_note(
                note, content, rtf_content, resource, dialog
            ),
            on_failed=lambda message: QMessageBox.warning(dialog, "创建失败", message),
        )

    def _finish_new_note(self, note, content, rtf_content, resource, dialog):
        note["coopResource"] = resource
        try:
            self._save_note_draft(note, content, rtf_content)
            self._create_note_remote(note, content, rtf_content)
        except Exception as exc:
            QMessageBox.warning(dialog, "创建失败", str(exc))
            return

        dialog.accept()
        preview = " ".join(content.split())
        self._note_preview_cache[self._note_id(note)] = preview
        self.refresh_current()

    def refresh_current(self):
        self.load_current(self.tabs.currentIndex())

    def load_current(self, index):
        if self.load_thread and self.load_thread.isRunning():
            return
        self.lists[index].clear()
        self._set_status(index, f"正在加载{self.TAB_NAMES[index]}...")
        self.summary_label.setText(f"{self.TAB_NAMES[index]} · 加载中")
        try:
            self._prepare_context()
        except Exception as exc:
            self._show_error(index, f"无法获取笔记配置: {exc}")
            return

        category_id = (
            f"gongkaibiji{self.user_id}"
            if index == 0 else f"gerenbiji{self.user_id}"
        )
        folder_cid = self._active_folder_cids.get(index) or category_id
        self.load_thread = NotesLoadThread(
            self.crawler, index, self.user_id, self.notebook_id,
            self.parent_id, folder_cid
        )
        self.load_thread.loaded.connect(self._on_notes_loaded)
        self.load_thread.failed.connect(self._on_notes_failed)
        self.load_thread.finished.connect(self._clear_load_thread)
        self.load_thread.finished.connect(self.load_thread.deleteLater)
        self.load_thread.start()

    def _clear_load_thread(self):
        self.load_thread = None

    def _on_notes_loaded(self, index, notes, folder_counts, folder_ids):
        note_list = self.lists[index]
        note_list.clear()
        if not notes:
            self._set_status(index, f"暂无{self.TAB_NAMES[index]}")
        self._set_status(index, "")
        self.summary_label.setText(f"{self.TAB_NAMES[index]} · {len(notes)} 条")
        grouped_notes = {}
        active_folder_path = self._active_folder_paths.get(index)
        active_folder_name = (
            active_folder_path.rsplit(" / ", 1)[-1]
            if active_folder_path else None
        )
        current_folder_name = active_folder_name or self.TAB_NAMES[index]
        for folder_path in folder_counts:
            if folder_path in (
                self.TAB_NAMES[index], active_folder_path, active_folder_name
            ):
                continue
            path_parts = str(folder_path).split(" / ")
            if len(path_parts) < 2 or path_parts[-2] != current_folder_name:
                continue
            grouped_notes.setdefault(folder_path, [])
        for note in notes:
            folder_name = str(note.get("folder_name") or "未分类")
            if folder_name in (
                self.TAB_NAMES[index], active_folder_path, active_folder_name
            ):
                folder_name = ""
            grouped_notes.setdefault(folder_name, []).append(note)

        for folder_name, folder_notes in grouped_notes.items():
            if folder_name:
                display_name = folder_name.rsplit(" / ", 1)[-1]
                folder_item = QListWidgetItem()
                folder_item.setData(33, True)
                folder_item.setData(34, folder_ids.get(folder_name))
                folder_item.setData(35, folder_name)
                folder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                note_list.addItem(folder_item)

                folder_widget = QWidget()
                folder_widget.setObjectName("folder_item")
                folder_widget.setFixedHeight(92)
                folder_layout = QHBoxLayout(folder_widget)
                folder_layout.setContentsMargins(14, 0, 14, 0)
                folder_layout.setSpacing(8)
                folder_label = QLabel(f"📁 {display_name}")
                folder_label.setObjectName("folder_name")
                folder_label.setFont(QFont("", 16, QFont.Weight.Bold))
                count_label = QLabel(
                    str(folder_counts.get(folder_name, len(folder_notes)))
                )
                count_label.setObjectName("folder_count")
                folder_layout.addWidget(
                    folder_label, alignment=Qt.AlignmentFlag.AlignVCenter
                )
                folder_layout.addStretch()
                folder_layout.addWidget(
                    count_label, alignment=Qt.AlignmentFlag.AlignVCenter
                )
                apply_theme_stylesheet(folder_widget, lambda palette: f"""
                    QLabel#folder_name {{
                        color: {palette.text};
                    }}
                    QWidget#folder_item {{
                        background-color: transparent;
                        border: none;
                        border-bottom: 1px solid {palette.border};
                        border-radius: 0;
                    }}
                    QLabel#folder_count {{
                        color: {palette.text_muted};
                        font-size: 14px;
                    }}
                """)
                folder_item.setSizeHint(QSize(0, 92))
                note_list.setItemWidget(folder_item, folder_widget)

            for note in folder_notes:
                cached_preview = self._note_preview_cache.get(self._note_id(note))
                if cached_preview and not self._note_preview_text(note):
                    note["content"] = cached_preview
                    note["contentTxt"] = cached_preview
                item = QListWidgetItem()
                item.setData(32, note)
                note_list.addItem(item)
                note_widget = self._create_note_widget(note)
                note_widget.clicked.connect(
                    lambda current_item=item: note_list.setCurrentItem(current_item)
                )
                note_widget.double_clicked.connect(
                    lambda current=note: self._show_note_detail(current)
                )
                item.setSizeHint(note_widget.sizeHint())
                note_list.setItemWidget(item, note_widget)

    def _render_breadcrumb(self, index):
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        labels = [self.TAB_NAMES[index]]
        labels.extend(folder[0] for folder in self._folder_stacks[index])
        for depth, label in enumerate(labels):
            button = QPushButton(label)
            button.setFlat(True)
            is_current = depth == len(labels) - 1
            button.setEnabled(not is_current)
            button.setCursor(
                Qt.CursorShape.ArrowCursor
                if is_current else Qt.CursorShape.PointingHandCursor
            )
            apply_theme_stylesheet(button, lambda palette, current=is_current: f"""
                QPushButton {{
                    color: {palette.text if current else palette.accent};
                    background: transparent;
                    border: none;
                    padding: 3px 6px;
                    font-size: 12px;
                    font-weight: {"600" if current else "normal"};
                }}
                QPushButton:hover {{
                    color: {palette.accent_hover};
                    background-color: {palette.hover_bg};
                    border-radius: 3px;
                }}
                QPushButton:disabled {{
                    color: {palette.text};
                }}
            """)
            button.clicked.connect(
                lambda _checked=False, target_depth=depth:
                self._navigate_breadcrumb(index, target_depth)
            )
            self.breadcrumb_layout.addWidget(button)
            if depth < len(labels) - 1:
                separator = QLabel("›")
                apply_theme_stylesheet(
                    separator,
                    lambda palette: f"color: {palette.text_muted}; font-size: 14px;"
                )
                self.breadcrumb_layout.addWidget(separator)
        self.breadcrumb_layout.addStretch()

    def _navigate_breadcrumb(self, index, target_depth):
        if target_depth == 0:
            self._folder_stacks[index] = []
            self._active_folder_cids[index] = None
            self._active_folder_paths[index] = None
        else:
            self._folder_stacks[index] = self._folder_stacks[index][:target_depth]
            _folder_name, folder_cid = self._folder_stacks[index][-1]
            self._active_folder_cids[index] = folder_cid
            self._active_folder_paths[index] = " / ".join(
                [self.TAB_NAMES[index]]
                + [folder[0] for folder in self._folder_stacks[index]]
            )
        self._render_breadcrumb(index)
        self.load_current(index)

    def _open_folder(self, note_list, item):
        if not item.data(33):
            return
        folder_cid = item.data(34)
        folder_path = item.data(35)
        if not folder_cid or not folder_path:
            return
        index = self.lists.index(note_list)
        folder_name = str(folder_path).rsplit(" / ", 1)[-1]
        self._folder_stacks[index].append((folder_name, str(folder_cid)))
        self._active_folder_cids[index] = str(folder_cid)
        self._active_folder_paths[index] = " / ".join(
            [self.TAB_NAMES[index]]
            + [folder[0] for folder in self._folder_stacks[index]]
        )
        self._render_breadcrumb(index)
        self.load_current(index)

    def _on_notes_failed(self, index, message):
        self._show_error(index, f"笔记加载失败: {message}")

    def _show_note_context_menu(self, note_list, position):
        item = note_list.itemAt(position)
        if item is None or item.data(33):
            return
        note_list.setCurrentItem(item)
        note = item.data(32) or {}
        menu = QMenu(self)
        apply_theme_stylesheet(menu, self._note_menu_stylesheet)
        delete_action = menu.addAction("🗑️ 删除")
        delete_action.triggered.connect(lambda: self._delete_note(note))
        menu.exec(note_list.viewport().mapToGlobal(position))

    def _delete_note(self, note):
        note_id = self._note_id(note)
        if not note_id:
            QMessageBox.warning(self, "删除失败", "笔记数据中缺少笔记 ID")
            return
        title = str(note.get("title") or "无标题").strip()
        answer = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除《{title}》吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            response = self.crawler.session.get(
                f"https://noteyd.chaoxing.com/pc/note_note/{note_id}/deleteNoteLatest",
                headers=self._note_request_headers(
                    f"https://noteyd.chaoxing.com/pc/{note_id}?from=fetchAdjacent"
                ),
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("result") not in (1, True, "1", "true", "True"):
                raise RuntimeError(payload.get("msg") or "服务器未确认删除成功")
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return

        self._note_preview_cache.pop(note_id, None)
        self.refresh_current()

    def _show_error(self, index, message):
        self.lists[index].clear()
        self._set_status(index, message)
        self.summary_label.setText(f"{self.TAB_NAMES[index]} · 加载失败")

    def _set_status(self, index, message):
        self.status_label.setText(message)
        self.status_label.setVisible(bool(message))

        if message:
            self.status_label.setStyleSheet("color: #888888; font-size: 14px; padding: 20px;")

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

        if self._uses_resource_note(note):
            self._prepare_resource_encoder(note)
        self._show_note_composer(note)

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

    def _create_note_remote(self, note, content, rtf_content):
        """先保存草稿后正式创建新笔记，不能使用已有笔记的编辑接口。"""
        note_id = self._note_id(note)
        if not note_id:
            raise RuntimeError("新笔记缺少笔记 ID，无法创建")

        notebook_id = str(note.get("notebookCid") or self.notebook_id)
        response = self.crawler.session.post(
            "https://noteyd.chaoxing.com/pc/note_note/createNote",
            params={"cid": note_id},
            data={
                "title": str(note.get("title") or "").strip(),
                "encode": 0,
                "content": content,
                "files_url": note.get("files_url") or note.get("filesUrl") or "",
                "attachment": note.get("attachment") or "",
                "rtf_content": rtf_content,
                "_t": int(datetime.now().timestamp() * 1000),
                "isRichText": 1,
                "isCooperate": 1 if self._uses_resource_note(note) else 0,
                "notebookCid": notebook_id,
                "extension": note.get("extension") or json.dumps({
                    "cooperateVersion": 1,
                    "storeType": "2",
                    "useMySQL": True,
                }, ensure_ascii=False),
                "isNewNote": 1,
                "coopResource": note.get("coopResource") or "",
                "sort": note.get("sort") or "",
                "cooperatorPuids": note.get("cooperatorPuids") or "",
                "openInviteSign": note.get("openInviteSign", 0),
            },
            headers=self._note_request_headers(
                "https://noteyd.chaoxing.com/pc/editor"
                f"?isEdit=1&type=1&cid={note_id}"
            ),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("result") not in (1, True, "1", "true", "True"):
            raise RuntimeError(payload.get("msg") or "服务器未确认创建成功")

        message = payload.get("msg")
        if isinstance(message, dict) and message.get("newCid"):
            note["noteCid"] = str(message["newCid"])

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
        content = self._note_preview_text(note, plain_content)
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
                item.setData(32, note)
                title_label = card.findChild(QLabel, "note_title")
                if title_label is not None:
                    title_label.setText(str(note.get("title") or "无标题"))
                content_label = card.findChild(QLabel, "note_content")
                if content_label is not None:
                    content_label.setText(content)
                return

    @staticmethod
    def _note_preview_text(note, plain_content=None):
        content = plain_content
        if content is None:
            content = note.get("content") or note.get("contentTxt") or ""
        content = str(content or "").strip()
        if not content:
            rich_content = str(note.get("rtf_content") or "").strip()
            rich_content = re.sub(
                r"<hidden\b[^>]*>.*?</hidden>", " ", rich_content,
                flags=re.IGNORECASE | re.DOTALL,
            )
            content = re.sub(r"<[^>]+>", " ", rich_content)
            content = unescape(content)
        return " ".join(content.split())

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
        content = NotesView._note_preview_text(note)
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
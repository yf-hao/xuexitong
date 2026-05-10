"""
聊天视图 - 左右布局，左侧消息/学生列表，右侧聊天区域
"""
from html import escape
from datetime import datetime
import json
import threading
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget,
    QTabWidget, QTextEdit, QLineEdit, QPushButton,
    QSplitter, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QUrl
from PyQt6.QtGui import QFont, QPixmap, QKeyEvent
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from core.config import DATA_DIR
from core.group_members_cache import build_group_members_cache_path, load_group_members_cache, sanitize_group_cache_filename
from ui.workers import ChatMessageListWorker, ChatHistoryWorker, ChatGroupMembersWorker
from core.logger import get_logger

logger = get_logger()


# ── 样式 ──────────────────────────────────────────────

CHAT_STYLE = """
    /* 左侧面板 */
    QFrame#left_panel {
        background-color: #1a1a1a;
        border-right: 1px solid #2d2d2d;
    }
    QTabWidget::pane {
        border: none;
        background-color: #1a1a1a;
    }
    QTabBar::tab {
        background-color: #1a1a1a;
        color: #aaaaaa;
        padding: 10px 20px;
        border: none;
        border-bottom: 2px solid transparent;
        font-size: 14px;
        font-weight: bold;
        min-width: 80px;
    }
    QTabBar::tab:selected {
        color: #007acc;
        border-bottom: 2px solid #007acc;
    }
    QTabBar::tab:hover:!selected {
        color: #ffffff;
        background-color: #252526;
    }
    /* 消息列表 / 学生列表 */
    QListWidget#chat_list, QListWidget#student_list {
        background-color: #1a1a1a;
        border: none;
        outline: none;
        font-size: 14px;
    }
    QListWidget#chat_list::item, QListWidget#student_list::item {
        padding: 0px;
        border-bottom: 1px solid #252526;
        color: #cccccc;
    }
    QListWidget#chat_list::item:hover, QListWidget#student_list::item:hover {
        background-color: #252526;
    }
    QListWidget#chat_list::item:selected, QListWidget#student_list::item:selected {
        background-color: #007acc;
        color: #ffffff;
    }

    /* 右侧聊天区域 */
    QFrame#right_panel {
        background-color: #1e1e1e;
    }
    QLabel#chat_title {
        color: #ffffff;
        font-size: 16px;
        font-weight: bold;
        padding: 12px 16px;
        background-color: #252526;
        border-bottom: 1px solid #2d2d2d;
    }
    /* 消息气泡区域 */
    QTextEdit#chat_messages {
        background-color: #1e1e1e;
        border: none;
        color: #cccccc;
        font-size: 14px;
        padding: 10px;
    }
    /* 输入区域 */
    QFrame#input_area {
        background-color: #252526;
        border-top: 1px solid #2d2d2d;
    }
    QLineEdit#student_search {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 13px;
        margin: 8px 8px 4px 8px;
    }
    QLineEdit#student_search:focus {
        border: 1px solid #007acc;
    }
    QPushButton#group_refresh_btn {
        background-color: #2d2d2d;
        color: #dcdcdc;
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: bold;
        margin: 8px 8px 4px 0;
    }
    QPushButton#group_refresh_btn:hover {
        background-color: #3a3a3a;
        border: 1px solid #4a4a4a;
    }
    QPushButton#group_refresh_btn:disabled {
        color: #777777;
        background-color: #252526;
        border: 1px solid #333333;
    }
    QLineEdit#msg_input {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #3d3d3d;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 14px;
    }
    QLineEdit#msg_input:focus {
        border: 1px solid #007acc;
    }
    QPushButton#send_btn {
        background-color: #007acc;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 10px 20px;
        font-size: 14px;
        font-weight: bold;
    }
    QPushButton#send_btn:hover {
        background-color: #1a8ad4;
    }
    QPushButton#send_btn:disabled {
        background-color: #2d2d2d;
        color: #666666;
    }

    /* 空状态占位 */
    QLabel#empty_hint {
        color: #555555;
        font-size: 16px;
    }

    /* 加载提示 */
    QLabel#loading_hint {
        color: #888888;
        font-size: 13px;
        padding: 10px;
    }
"""


class ChatSessionItem(QWidget):
    """自定义会话列表项：头像 + 名字/副标题 + 时间"""

    def __init__(self, name: str, time_str: str, avatar_url: str = None, session=None, subtitle: str = "", unread_count: int = 0, parent=None):
        super().__init__(parent)
        self._avatar_url = avatar_url
        self._session = session
        self._setup_ui(name, time_str, avatar_url, subtitle, unread_count)

    def _setup_ui(self, name: str, time_str: str, avatar_url: str, subtitle: str, unread_count: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 头像
        self.avatar_container = QWidget()
        self.avatar_container.setFixedSize(40, 40)
        self.avatar_label = QLabel()
        self.avatar_label.setParent(self.avatar_container)
        self.avatar_label.setGeometry(0, 0, 40, 40)
        self.avatar_label.setScaledContents(True)
        self._set_placeholder_avatar(name)
        self.unread_badge_label = QLabel(self.avatar_container)
        self.unread_badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unread_badge_label.hide()
        layout.addWidget(self.avatar_container)

        # 中间：名字 + 副标题
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #cccccc; font-size: 14px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(self.name_label)

        self.subtitle_label = QLabel(subtitle or "")
        self.subtitle_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if subtitle:
            text_layout.addWidget(self.subtitle_label)

        layout.addLayout(text_layout, stretch=1)

        # 右侧：时间
        self.time_label = QLabel(time_str or "")
        self.time_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if time_str:
            layout.addWidget(self.time_label)
        self.set_unread_count(unread_count)

    def _set_placeholder_avatar(self, name: str):
        """显示名字首字作为占位头像"""
        self.avatar_label.setText(name[:1] if name else "?")
        self.avatar_label.setStyleSheet(
            "background-color: #6b5ce7; color: white; font-size: 16px; font-weight: bold;"
        )
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_avatar_pixmap(self, pixmap: QPixmap):
        """异步加载完成后设置头像"""
        if pixmap and not pixmap.isNull():
            self.avatar_label.setPixmap(pixmap)
            self.avatar_label.setStyleSheet("")
            self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_unread_count(self, unread_count: int):
        try:
            unread_count = int(unread_count or 0)
        except Exception:
            unread_count = 0
        if unread_count <= 0:
            self.unread_badge_label.hide()
            return

        badge_text = "99+" if unread_count > 99 else str(unread_count)
        badge_width = 22 if len(badge_text) >= 2 else 18
        self.unread_badge_label.setText(badge_text)
        self.unread_badge_label.setGeometry(40 - badge_width, 0, badge_width, 18)
        self.unread_badge_label.setStyleSheet(
            "background-color: #ff4d4f; color: white; border-radius: 9px; "
            "font-size: 11px; font-weight: bold; padding: 0 4px;"
        )
        self.unread_badge_label.raise_()
        self.unread_badge_label.show()


class StudentSearchLineEdit(QLineEdit):
    """学生搜索框：Esc 清空搜索。"""

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatView(QWidget):
    """聊天视图：左侧消息/学生列表，右侧聊天区域"""

    send_message = pyqtSignal(str, str)  # (target_id, message_text)
    msync_message_received = pyqtSignal(dict)

    def __init__(self, crawler, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self._current_target_id = None
        self._current_history_id = None
        self._current_target_name = None
        self._message_worker = None
        self._history_worker = None
        self._history_workers = []
        self._group_members_worker = None
        self._last_send_error = ""
        self._raw_sessions = []  # 保存原始 API 返回数据
        self._message_cache = {}
        self._pending_read_acks = {}
        self._msync_connecting = False
        self._msync_connect_lock = threading.Lock()
        self._suppress_unread_summary_request = False
        self._all_students = []
        self._history_id_by_peer = {}
        self._session_meta_by_peer = {}
        self._unread_count_by_peer = {}
        self._locally_read_conversations = set()
        self._last_read_sync_by_conversation = {}
        self._group_members_cache = {}
        self._group_members_cache_dir = Path(DATA_DIR) / "data" / "group_members"
        self._current_group_room_id = ""
        self._current_group_room_name = ""
        self._current_group_cache_name = ""
        self._group_name_by_room_id = {}
        self._group_cache_name_by_room_id = {}
        self._pending_group_room_id = ""
        self._avatar_requests = {}  # QNetworkReply -> ChatSessionItem，用于异步回调
        self._net_mgr = QNetworkAccessManager(self)
        self.msync_message_received.connect(self._on_msync_message)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(CHAT_STYLE)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 左侧面板 ──
        left_frame = QFrame()
        left_frame.setObjectName("left_panel")
        left_frame.setFixedWidth(280)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Tab: 消息 / 学生列表
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        # Tab 1: 消息列表
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("chat_list")
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.chat_list.currentItemChanged.connect(self._on_chat_selected)
        self.tab_widget.addTab(self.chat_list, "消息")

        # Tab 2: 群组列表
        self.student_tab = QWidget()
        student_layout = QVBoxLayout(self.student_tab)
        student_layout.setContentsMargins(0, 0, 0, 0)
        student_layout.setSpacing(0)
        student_header_layout = QHBoxLayout()
        student_header_layout.setContentsMargins(0, 0, 0, 0)
        student_header_layout.setSpacing(6)
        self.student_search = StudentSearchLineEdit()
        self.student_search.setObjectName("student_search")
        self.student_search.setFixedHeight(50)
        self.student_search.setPlaceholderText("搜索学生...")
        self.student_search.textChanged.connect(self._on_student_search_changed)
        student_header_layout.addWidget(self.student_search, stretch=1)
        self.group_refresh_btn = QPushButton("刷新")
        self.group_refresh_btn.setObjectName("group_refresh_btn")
        self.group_refresh_btn.setFixedHeight(50)
        self.group_refresh_btn.setFixedWidth(64)
        self.group_refresh_btn.setEnabled(False)
        self.group_refresh_btn.clicked.connect(self._refresh_current_group_members)
        student_header_layout.addWidget(self.group_refresh_btn)
        student_layout.addLayout(student_header_layout)
        self.student_list = QListWidget()
        self.student_list.setObjectName("student_list")
        self.student_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.student_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.student_list.currentItemChanged.connect(self._on_student_selected)
        student_layout.addWidget(self.student_list)
        self.tab_widget.addTab(self.student_tab, "群组")

        # 加载状态提示
        self.loading_hint = QLabel("")
        self.loading_hint.setObjectName("loading_hint")
        self.loading_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_hint.hide()

        left_layout.addWidget(self.tab_widget)
        left_layout.addWidget(self.loading_hint)
        splitter.addWidget(left_frame)

        # ── 右侧面板 ──
        right_frame = QFrame()
        right_frame.setObjectName("right_panel")
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 聊天标题栏
        self.chat_title_label = QLabel("选择一个对话")
        self.chat_title_label.setObjectName("chat_title")
        self.chat_title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        right_layout.addWidget(self.chat_title_label)

        # 消息显示区域
        self.chat_messages = QTextEdit()
        self.chat_messages.setObjectName("chat_messages")
        self.chat_messages.setReadOnly(True)
        self.chat_messages.setPlaceholderText("")
        right_layout.addWidget(self.chat_messages, stretch=1)

        # 输入区域
        input_frame = QFrame()
        input_frame.setObjectName("input_area")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)

        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("msg_input")
        self.msg_input.setPlaceholderText("输入消息...")
        self.msg_input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.msg_input, stretch=1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setEnabled(False)
        input_layout.addWidget(self.send_btn)

        right_layout.addWidget(input_frame)
        splitter.addWidget(right_frame)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # 默认显示空状态
        self._show_empty_state()

    # ── 公共方法 ──

    def on_show(self):
        """视图被切换到时调用，异步加载会话列表。"""
        # 先同步获取凭证，确保 token 只请求一次
        try:
            self.crawler.get_im_credentials()
        except Exception:
            pass
        if not self._raw_sessions:
            self._load_message_list()
        self._ensure_msync_connected()
        if self._raw_sessions:
            self._request_unread_summary(self._raw_sessions)

    def _load_message_list(self):
        """异步加载会话列表"""
        if self._message_worker and self._message_worker.isRunning():
            return
        self.loading_hint.setText("正在加载会话列表...")
        self.loading_hint.show()
        self.chat_list.setEnabled(False)

        self._message_worker = ChatMessageListWorker(self.crawler)
        self._message_worker.messages_ready.connect(self._on_messages_loaded)
        self._message_worker.start()

    def _on_messages_loaded(self, sessions: list):
        """会话列表加载完成回调"""
        self.loading_hint.hide()
        self.chat_list.setEnabled(True)
        prepared_sessions = []
        for session in sessions or []:
            if isinstance(session, dict):
                item = dict(session)
                if not item.get("_historyKey"):
                    item["_historyKey"] = str(item.get("msgId", "") or item.get("chatId", "") or "")
                prepared_sessions.append(item)
            else:
                prepared_sessions.append(session)
        sessions = [self._merge_session_metadata(session) for session in prepared_sessions]
        self._raw_sessions = sessions
        if not self._suppress_unread_summary_request:
            self._request_unread_summary(sessions)
        selected_chat_id = self._current_history_id or self._current_target_id
        self.chat_list.clear()

        if not sessions:
            self.chat_list.addItem(QListWidgetItem("暂无会话"))
            return

        # 按更新时间降序排列
        sorted_sessions = sorted(
            sessions,
            key=lambda s: s.get("updateTime", 0),
            reverse=True
        )

        # 分离私聊和群聊
        private_chats = []
        group_chats = []
        for s in sorted_sessions:
            if s.get("isGroup") == 0 or s.get("isPrivate") is False:
                group_chats.append(s)
            else:
                private_chats.append(s)

        if private_chats:
            for s in private_chats:
                self._add_session_item(s)
        if group_chats:
            sep = QListWidgetItem("── 群聊 ──")
            sep.setFlags(sep.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            sep.setForeground(Qt.GlobalColor.gray)
            self.chat_list.addItem(sep)
            for s in group_chats:
                self._add_session_item(s)

        if selected_chat_id:
            self._restore_selected_chat(selected_chat_id)

    def _request_unread_summary(self, sessions: list):
        if not hasattr(self.crawler, "request_history_summary_msync"):
            return
        peer_ids = []
        for session in sessions or []:
            if not isinstance(session, dict):
                continue
            peer_id = self._resolve_session_peer_id(session)
            if peer_id and peer_id not in peer_ids:
                peer_ids.append(peer_id)
        if peer_ids:
            self.crawler.request_history_summary_msync(peer_ids)

    def _refresh_session_list(self, sessions: list = None):
        sessions = self._raw_sessions if sessions is None else sessions
        self._suppress_unread_summary_request = True
        try:
            self._on_messages_loaded(sessions)
        finally:
            self._suppress_unread_summary_request = False

    def _resolve_session_peer_id(self, session: dict) -> str:
        """为已有会话解析实时发送目标。"""
        chat_id = str(session.get("chatId", "") or "")
        if chat_id:
            mapped_peer_id = ChatView._resolve_peer_id_by_history_id(self, chat_id)
            if mapped_peer_id:
                return mapped_peer_id
        msg_id = str(session.get("msgId", "") or "")
        course_params = getattr(getattr(getattr(self, "crawler", None), "session_manager", None), "course_params", {}) or {}
        current_tuid = str(course_params.get("im_tuid", "") or "")
        if msg_id and "+" in msg_id:
            left, right = msg_id.split("+", 1)
            if current_tuid and left == current_tuid:
                return right
            if current_tuid and right == current_tuid:
                return left
        return str(chat_id or "")

    def _resolve_peer_id_by_history_id(self, history_id: str) -> str:
        history_id = str(history_id or "")
        if not history_id:
            return ""
        for peer_id, mapped_history_id in (getattr(self, "_history_id_by_peer", {}) or {}).items():
            if str(mapped_history_id or "") == history_id:
                return str(peer_id or "")
        return ""

    def _resolve_session_history_id(self, session: dict) -> str:
        if not isinstance(session, dict):
            return ""
        return str(session.get("_historyKey", "") or session.get("msgId", "") or session.get("chatId", "") or "")

    def _resolve_active_peer_id(self, peer_id: str = "", history_id: str = "") -> str:
        peer_id = str(peer_id or "")
        history_id = str(history_id or "")
        if history_id:
            mapped_peer_id = ChatView._resolve_peer_id_by_history_id(self, history_id)
            if mapped_peer_id:
                return mapped_peer_id
        return ChatView._normalize_unread_peer_id(self, peer_id)

    def _resolve_best_history_key(self, session: dict = None, peer_id: str = "", history_id: str = "") -> str:
        session = session if isinstance(session, dict) else {}
        peer_id = str(peer_id or "")
        history_id = str(history_id or "")
        active_peer_id = ChatView._resolve_active_peer_id(self, peer_id, history_id)

        meta = {}
        for key in (active_peer_id, peer_id, history_id):
            value = (getattr(self, "_session_meta_by_peer", {}) or {}).get(str(key or ""))
            if isinstance(value, dict) and value:
                meta = value
                break

        candidates = []
        for candidate in (
            session.get("_historyKey"),
            session.get("msgId"),
            meta.get("chatId"),
            (getattr(self, "_history_id_by_peer", {}) or {}).get(active_peer_id, ""),
            history_id,
            session.get("chatId"),
        ):
            candidate = str(candidate or "")
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            if candidate != active_peer_id:
                return candidate
        return candidates[0] if candidates else ""

    def _mark_conversation_locally_read(self, peer_id: str = "", history_id: str = ""):
        if not hasattr(self, "_locally_read_conversations"):
            self._locally_read_conversations = set()
        for key in (
            ChatView._normalize_unread_peer_id(self, peer_id),
            str(history_id or ""),
        ):
            if key:
                self._locally_read_conversations.add(key)

    def _clear_conversation_locally_read_marker(self, peer_id: str = "", history_id: str = ""):
        if not hasattr(self, "_locally_read_conversations"):
            self._locally_read_conversations = set()
        for key in (
            ChatView._normalize_unread_peer_id(self, peer_id),
            str(history_id or ""),
        ):
            if key:
                self._locally_read_conversations.discard(key)

    def _normalize_unread_peer_id(self, peer_id: str) -> str:
        peer_id = str(peer_id or "")
        if "/" in peer_id:
            return peer_id.split("/", 1)[0]
        return peer_id

    def _extract_session_unread_count(self, session: dict) -> int:
        if not isinstance(session, dict):
            return 0
        for key in ("unread_count", "unreadCount", "unread", "unRead", "msgUnRead", "notReadCount"):
            value = session.get(key)
            if value in (None, ""):
                continue
            try:
                return max(int(value), 0)
            except Exception:
                continue
        return 0

    def _get_unread_count(self, peer_id: str = "", history_id: str = "", session: dict = None) -> int:
        for key in (self._normalize_unread_peer_id(peer_id), str(history_id or "")):
            if key and key in self._unread_count_by_peer:
                try:
                    return max(int(self._unread_count_by_peer.get(key, 0) or 0), 0)
                except Exception:
                    return 0
        history_id = str(history_id or "")
        if history_id:
            for mapped_peer_id, mapped_history_id in (self._history_id_by_peer or {}).items():
                if str(mapped_history_id or "") != history_id:
                    continue
                mapped_peer_id = self._normalize_unread_peer_id(mapped_peer_id)
                if mapped_peer_id in self._unread_count_by_peer:
                    try:
                        return max(int(self._unread_count_by_peer.get(mapped_peer_id, 0) or 0), 0)
                    except Exception:
                        return 0
        return self._extract_session_unread_count(session or {})

    def _set_unread_count(self, peer_id: str, unread_count: int, history_id: str = ""):
        peer_id = self._normalize_unread_peer_id(peer_id)
        history_id = str(history_id or "")
        try:
            unread_count = max(int(unread_count or 0), 0)
        except Exception:
            unread_count = 0

        changed = False
        for key in (peer_id, history_id):
            if not key:
                continue
            if self._unread_count_by_peer.get(key) != unread_count:
                self._unread_count_by_peer[key] = unread_count
                changed = True
        return changed

    def _apply_history_summary_unread(self, subjects: list):
        changed = []
        current_history_id = str(getattr(self, "_current_history_id", "") or "")
        current_peer_id = ChatView._resolve_active_peer_id(self, getattr(self, "_current_target_id", ""), current_history_id)
        for item in subjects or []:
            if not isinstance(item, dict):
                continue
            subject = self._normalize_unread_peer_id(item.get("subject"))
            if not subject:
                continue
            try:
                count = max(int(item.get("count") or 0), 0)
            except Exception:
                continue
            mapped_history_id = str(self._history_id_by_peer.get(subject, "") or "")
            if (
                subject == current_peer_id
                or (current_history_id and mapped_history_id == current_history_id)
                or subject in getattr(self, "_locally_read_conversations", set())
                or (mapped_history_id and mapped_history_id in getattr(self, "_locally_read_conversations", set()))
            ):
                count = 0
            if self._set_unread_count(subject, count):
                changed.append({"peer_id": subject, "history_id": mapped_history_id, "unread_count": count})
        return changed

    def _clear_current_unread_count(self):
        changed = False
        history_id = self._current_history_id or self._history_id_by_peer.get(str(self._current_target_id or ""), "")
        active_peer_id = ChatView._resolve_active_peer_id(self, self._current_target_id, history_id)
        ChatView._mark_conversation_locally_read(self, active_peer_id, history_id)
        if active_peer_id or history_id:
            changed = self._set_unread_count(
                active_peer_id,
                0,
                history_id=history_id,
            )
        if changed:
            self._update_session_unread_row(active_peer_id, history_id, 0)
        return changed

    def _merge_session_metadata(self, session: dict) -> dict:
        if not isinstance(session, dict):
            return session
        merged = dict(session)
        peer_id = str(self._resolve_session_peer_id(merged) or "")
        chat_id = str(merged.get("chatId", "") or "")
        meta = None
        for key in (peer_id, chat_id):
            if key and key in self._session_meta_by_peer:
                meta = self._session_meta_by_peer[key]
                break
        if isinstance(meta, dict):
            if meta.get("subtitle"):
                merged["subtitle"] = meta["subtitle"]
            if meta.get("courseName"):
                merged["courseName"] = meta["courseName"]
            if meta.get("chatIco") and not merged.get("chatIco"):
                merged["chatIco"] = meta["chatIco"]
            if meta.get("chatId") and (
                not merged.get("chatId")
                or str(merged.get("chatId") or "") == peer_id
            ):
                merged["chatId"] = meta["chatId"]
            if meta.get("chatId") and (
                not merged.get("_historyKey")
                or str(merged.get("_historyKey") or "") == peer_id
            ):
                merged["_historyKey"] = meta["chatId"]
        unread_count = self._get_unread_count(peer_id, chat_id, merged)
        if unread_count:
            merged["unread_count"] = unread_count
        else:
            merged.pop("unread_count", None)
        return merged

    def _store_class_info_metadata(self, peer_id: str, class_info: dict):
        if not isinstance(class_info, dict):
            return False

        meta = {}
        if class_info.get("class_name"):
            meta["subtitle"] = str(class_info.get("class_name") or "")
        if class_info.get("course_name"):
            meta["courseName"] = str(class_info.get("course_name") or "")
        if class_info.get("image_url"):
            meta["chatIco"] = str(class_info.get("image_url") or "")
        if class_info.get("chat_id"):
            meta["chatId"] = str(class_info.get("chat_id") or "")
        if not meta:
            return False

        changed = False
        for key in (str(peer_id or ""), str(meta.get("chatId") or "")):
            if not key:
                continue
            current = dict(self._session_meta_by_peer.get(key) or {})
            merged = dict(current)
            merged.update({k: v for k, v in meta.items() if v})
            if merged != current:
                self._session_meta_by_peer[key] = merged
                changed = True

        if meta.get("chatId") and peer_id and not self._history_id_by_peer.get(str(peer_id)):
            self._history_id_by_peer[str(peer_id)] = str(meta["chatId"])
            changed = True
        if meta.get("chatId") and peer_id:
            existing_unread = self._get_unread_count(peer_id, "")
            if existing_unread and self._set_unread_count(peer_id, existing_unread, history_id=str(meta["chatId"])):
                changed = True

        if changed and self._raw_sessions:
            updated_sessions = [self._merge_session_metadata(session) for session in self._raw_sessions]
            if updated_sessions != self._raw_sessions:
                self._raw_sessions = updated_sessions
                target_history_id = str(meta.get("chatId") or self._history_id_by_peer.get(str(peer_id or ""), "") or "")
                for session in updated_sessions:
                    if not isinstance(session, dict):
                        continue
                    current_peer_id = self._resolve_session_peer_id(session)
                    current_history_id = str(session.get("msgId", "") or session.get("chatId", "") or "")
                    if str(peer_id or "") not in {current_peer_id, current_history_id} and target_history_id not in {current_peer_id, current_history_id}:
                        continue
                    self._update_session_row(current_peer_id, current_history_id, session=session)

        return changed

    def _upsert_session_from_message(self, peer_id: str, msg: dict, display_name: str = ""):
        peer_id = str(peer_id or "")
        if not peer_id:
            return False

        history_id = str(self._history_id_by_peer.get(peer_id, "") or peer_id)
        timestamp = int(msg.get("timestamp") or int(time.time() * 1000))
        is_group = bool(msg.get("class_info"))
        session_name = self._resolve_session_display_name(peer_id, msg, fallback_name=display_name)

        updated_sessions = []
        found = False
        for session in self._raw_sessions or []:
            if not isinstance(session, dict):
                updated_sessions.append(session)
                continue

            current = dict(session)
            current_peer_id = self._resolve_session_peer_id(current)
            current_history_id = ChatView._resolve_session_history_id(self, current)
            if peer_id not in {current_peer_id, current_history_id} and history_id not in {current_peer_id, current_history_id}:
                updated_sessions.append(current)
                continue

            found = True
            current["updateTime"] = timestamp
            current_name = str(current.get("chatName") or "")
            if not current_name or current_name in {current_peer_id, current_history_id, peer_id, history_id}:
                current["chatName"] = session_name
            if not current.get("chatId"):
                current["chatId"] = history_id
            if not current.get("_historyKey"):
                current["_historyKey"] = current_history_id or history_id
            if ChatView._is_group_session(self, current):
                is_group = True
            if is_group:
                current["isGroup"] = 0
                current["isPrivate"] = False
            updated_sessions.append(current)

        if not found:
            new_session = {
                "chatId": history_id,
                "_historyKey": history_id if history_id != peer_id else "",
                "chatName": session_name,
                "chatIco": "",
                "updateTime": timestamp,
                "isGroup": 0 if is_group else 1,
                "isPrivate": False if is_group else True,
            }
            updated_sessions.append(new_session)

        if updated_sessions == (self._raw_sessions or []):
            return False

        self._raw_sessions = updated_sessions
        self._refresh_session_list(updated_sessions)
        return True

    def _resolve_session_display_name(self, peer_id: str, msg: dict, fallback_name: str = "") -> str:
        peer_id = str(peer_id or "")
        msg = msg if isinstance(msg, dict) else {}
        class_info = msg.get("class_info")
        if not isinstance(class_info, dict):
            class_info = {}

        history_id = str(getattr(self, "_history_id_by_peer", {}).get(peer_id, "") or "")
        meta_by_peer = getattr(self, "_session_meta_by_peer", {}) or {}
        meta = {}
        for key in (peer_id, history_id):
            value = meta_by_peer.get(str(key or ""))
            if isinstance(value, dict) and value:
                meta = value
                break

        for candidate in (
            class_info.get("course_name"),
            msg.get("chatName"),
            msg.get("name"),
            meta.get("courseName"),
            class_info.get("class_name"),
            meta.get("subtitle"),
            fallback_name,
            peer_id,
        ):
            candidate = str(candidate or "").strip()
            if candidate:
                return candidate
        return peer_id

    def _add_session_item(self, session: dict):
        """向消息列表添加一个自定义会话项（头像+名字+时间）"""
        session, item_widget, peer_id, item_name, item_history_id, unread_count, avatar_url = self._build_session_item_components(session)
        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, peer_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, item_name)
        item.setData(Qt.ItemDataRole.UserRole + 2, session)
        item.setData(Qt.ItemDataRole.UserRole + 3, item_history_id)
        item.setData(Qt.ItemDataRole.UserRole + 4, unread_count)

        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, item_widget)

        # 异步加载头像
        if avatar_url:
            self._request_avatar(self.chat_list, item, avatar_url)

    def _build_session_item_components(self, session: dict):
        session = self._merge_session_metadata(session)
        chat_id = str(session.get("chatId", "") or "")
        history_key = str(session.get("msgId", "") or "")
        history_id = history_key or chat_id
        name = session.get("chatName", "未知")
        peer_id = self._resolve_session_peer_id(session)
        update_time = session.get("updateTime", 0)
        avatar_url = str(session.get("chatIco", "") or "")
        if history_id:
            self._history_id_by_peer[peer_id] = history_id

        if avatar_url.startswith("<"):
            import re
            m = re.search(r'src=["\']([^"\']+)["\']', avatar_url)
            if m:
                avatar_url = m.group(1)

        time_str = ""
        if update_time:
            try:
                dt = datetime.fromtimestamp(update_time / 1000)
                now = datetime.now()
                if dt.date() == now.date():
                    time_str = dt.strftime("%H:%M")
                elif (now.date() - dt.date()).days == 1:
                    time_str = "昨天"
                elif (now.date() - dt.date()).days < 7:
                    time_str = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
                else:
                    time_str = dt.strftime("%m-%d")
            except Exception:
                pass

        subtitle = str(session.get("subtitle", "") or "")
        unread_count = self._get_unread_count(peer_id, history_id, session)
        item_widget = ChatSessionItem(name, time_str, avatar_url, session, subtitle=subtitle, unread_count=unread_count)
        return session, item_widget, peer_id, name, history_id, unread_count, avatar_url

    def _update_session_row(self, peer_id: str = "", history_id: str = "", session: dict = None):
        list_widget = getattr(self, "chat_list", None)
        if list_widget is None:
            return False

        peer_id = self._normalize_unread_peer_id(peer_id)
        history_id = str(history_id or "")
        updated = False
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item is None:
                continue
            item_peer_id = self._normalize_unread_peer_id(item.data(Qt.ItemDataRole.UserRole) or "")
            item_history_id = str(item.data(Qt.ItemDataRole.UserRole + 3) or "")
            if peer_id not in {item_peer_id, item_history_id} and history_id not in {item_peer_id, item_history_id}:
                continue
            source_session = session or item.data(Qt.ItemDataRole.UserRole + 2) or {}
            built_session, item_widget, built_peer_id, item_name, built_history_id, unread_count, avatar_url = self._build_session_item_components(source_session)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, built_peer_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, item_name)
            item.setData(Qt.ItemDataRole.UserRole + 2, built_session)
            item.setData(Qt.ItemDataRole.UserRole + 3, built_history_id)
            item.setData(Qt.ItemDataRole.UserRole + 4, unread_count)
            list_widget.setItemWidget(item, item_widget)
            if avatar_url:
                self._request_avatar(list_widget, item, avatar_url)
            updated = True
        return updated

    def _update_session_unread_row(self, peer_id: str = "", history_id: str = "", unread_count: int = 0):
        peer_id = self._normalize_unread_peer_id(peer_id)
        history_id = str(history_id or "")
        try:
            unread_count = max(int(unread_count or 0), 0)
        except Exception:
            unread_count = 0

        updated = False
        for session in self._raw_sessions or []:
            if not isinstance(session, dict):
                continue
            current_peer_id = self._resolve_session_peer_id(session)
            current_history_id = str(session.get("msgId", "") or session.get("chatId", "") or "")
            if peer_id not in {current_peer_id, current_history_id} and history_id not in {current_peer_id, current_history_id}:
                continue
            if unread_count > 0:
                session["unread_count"] = unread_count
            else:
                session.pop("unread_count", None)
            updated = True

        list_widget = getattr(self, "chat_list", None)
        if list_widget is None:
            return updated

        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item is None:
                continue
            item_peer_id = self._normalize_unread_peer_id(item.data(Qt.ItemDataRole.UserRole) or "")
            item_history_id = str(item.data(Qt.ItemDataRole.UserRole + 3) or "")
            if peer_id not in {item_peer_id, item_history_id} and history_id not in {item_peer_id, item_history_id}:
                continue
            item.setData(Qt.ItemDataRole.UserRole + 4, unread_count)
            session = item.data(Qt.ItemDataRole.UserRole + 2) or {}
            if isinstance(session, dict):
                session = dict(session)
                if unread_count > 0:
                    session["unread_count"] = unread_count
                else:
                    session.pop("unread_count", None)
                item.setData(Qt.ItemDataRole.UserRole + 2, session)
            widget = list_widget.itemWidget(item)
            if widget and hasattr(widget, "set_unread_count"):
                widget.set_unread_count(unread_count)
            updated = True
        return updated

    def set_messages(self, messages: list[dict]):
        """设置消息列表（兼容旧接口，新数据通过 _on_messages_loaded 处理）
        messages: [{"id": ..., "name": ..., "last_msg": ..., "time": ..., "unread": ...}, ...]
        """
        self.chat_list.clear()
        for msg in messages:
            name = msg.get("name", "未知")
            last_msg = msg.get("last_msg", "")
            time_str = msg.get("time", "")
            unread = msg.get("unread", 0)

            display = f"{name}"
            if last_msg:
                display += f"\n{last_msg[:30]}"
            if time_str:
                display += f"  {time_str}"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, msg.get("id", ""))
            if unread:
                item.setData(Qt.ItemDataRole.UserRole + 1, unread)
            self.chat_list.addItem(item)

    def set_students(self, students: list[dict]):
        """设置学生列表
        students: [{"person_id": ..., "name": ..., "student_id": ...}, ...]
        """
        self._all_students = list(students or [])
        self._render_students(self._filtered_students())

    def _update_group_tab_title(self, count: int = 0):
        if not hasattr(self, "tab_widget") or not hasattr(self, "student_tab"):
            return
        index = self.tab_widget.indexOf(self.student_tab)
        if index >= 0:
            normalized_count = max(0, int(count or 0))
            title = f"群组({normalized_count})" if normalized_count > 0 else "群组"
            self.tab_widget.setTabText(index, title)

    def _filtered_students(self):
        keyword = self.student_search.text().strip().lower() if hasattr(self, "student_search") else ""
        if not keyword:
            return list(self._all_students)
        return [
            stu for stu in self._all_students
            if keyword in str(stu.get("name", "") or "").lower()
        ]

    def _render_students(self, students: list[dict]):
        self.student_list.clear()
        ChatView._update_group_tab_title(self, len(students or []))
        if not students:
            self.student_list.addItem(QListWidgetItem("未找到匹配群组"))
            return
        for stu in students:
            name = stu.get("name", "未知")
            person_id = stu.get("person_id", "")
            avatar_url = stu.get("avatar_url", "") or ""

            item_widget = ChatSessionItem(name, "", avatar_url, stu)
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            item.setData(Qt.ItemDataRole.UserRole + 2, stu)
            self.student_list.addItem(item)
            self.student_list.setItemWidget(item, item_widget)

            if avatar_url:
                self._request_avatar(self.student_list, item, avatar_url)

    def _on_student_search_changed(self, text: str):
        self._render_students(self._filtered_students())

    def _is_group_session(self, session: dict) -> bool:
        if not isinstance(session, dict):
            return False
        return session.get("isGroup") == 0 or session.get("isPrivate") is False

    def _resolve_group_room_id(self, session: dict) -> str:
        if not isinstance(session, dict):
            return ""
        for key in ("roomId", "chatId", "groupId", "id"):
            value = session.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _show_group_members_loading(self):
        self._all_students = []
        self.student_list.clear()
        ChatView._update_group_tab_title(self, 0)
        self.student_list.addItem(QListWidgetItem("正在加载群成员..."))

    def _show_group_members_empty(self):
        self._all_students = []
        self.student_list.clear()
        ChatView._update_group_tab_title(self, 0)
        self.student_list.addItem(QListWidgetItem("暂无群成员"))

    def _update_group_refresh_button_state(self):
        if hasattr(self, "group_refresh_btn"):
            self.group_refresh_btn.setEnabled(bool(self._current_group_room_id))

    def _resolve_group_room_name(self, session: dict) -> str:
        if not isinstance(session, dict):
            session = {}
        for key in ("chatName", "name", "title", "courseName"):
            value = session.get(key)
            if value not in (None, ""):
                return str(value).strip()
        room_id = ChatView._resolve_group_room_id(self, session)
        if room_id:
            return str(getattr(self, "_group_name_by_room_id", {}).get(room_id, "") or "").strip()
        return ""

    def _resolve_group_cache_name(self, session: dict) -> str:
        room_name = ChatView._resolve_group_room_name(self, session)
        class_name = ""
        if isinstance(session, dict):
            for key in ("subtitle", "className", "classname", "class_name"):
                value = session.get(key)
                if value not in (None, ""):
                    class_name = str(value).strip()
                    break
        if not class_name:
            room_id = ChatView._resolve_group_room_id(self, session)
            if room_id:
                return str(getattr(self, "_group_cache_name_by_room_id", {}).get(room_id, "") or room_name).strip()
        if room_name and class_name and class_name != room_name:
            return f"{room_name}-{class_name}"
        return room_name or class_name

    def _sanitize_group_cache_filename(self, room_name: str, room_id: str = "") -> str:
        return sanitize_group_cache_filename(room_name, fallback=room_id)

    def _legacy_group_members_cache_file(self, room_id: str) -> Path:
        cache_dir = Path(getattr(self, "_group_members_cache_dir", Path(DATA_DIR) / "data" / "group_members"))
        return cache_dir / f"{str(room_id or '').strip()}.json"

    def _group_members_cache_file(self, room_id: str, cache_name: str = "") -> Path:
        cache_dir = Path(getattr(self, "_group_members_cache_dir", Path(DATA_DIR) / "data" / "group_members"))
        return build_group_members_cache_path(
            cache_name or getattr(self, "_current_group_cache_name", ""),
            "",
            fallback=room_id,
            cache_dir=cache_dir,
        )

    def _load_persisted_group_members(self, room_id: str, cache_name: str = "", room_name: str = ""):
        room_id = str(room_id or "").strip()
        if not room_id:
            return None

        members, target_file = load_group_members_cache(
            cache_name,
            "",
            fallback=room_id,
            cache_dir=Path(getattr(self, "_group_members_cache_dir", Path(DATA_DIR) / "data" / "group_members")),
        )
        if target_file is None and room_name:
            members, target_file = load_group_members_cache(
                room_name,
                "",
                fallback=room_id,
                cache_dir=Path(getattr(self, "_group_members_cache_dir", Path(DATA_DIR) / "data" / "group_members")),
            )
        if target_file is None:
            return None

        logger.info(f"ChatView: 已加载群成员缓存 room_id={room_id}, file={target_file.name}, count={len(members)}")
        return members

    def _persist_group_members(self, room_id: str, members: list, cache_name: str = ""):
        room_id = str(room_id or "").strip()
        if not room_id or not isinstance(members, list):
            return

        payload = []
        for item in members:
            if not isinstance(item, dict):
                continue
            member = dict(item)
            if "person_id" in member:
                member["person_id"] = str(member.get("person_id") or "")
            if "name" in member:
                member["name"] = str(member.get("name") or "")
            if "student_id" in member:
                member["student_id"] = str(member.get("student_id") or "")
            if "avatar_url" in member:
                member["avatar_url"] = str(member.get("avatar_url") or "")
            if "tuid" in member:
                member["tuid"] = str(member.get("tuid") or "")
            if "puid" in member:
                member["puid"] = str(member.get("puid") or "")
            payload.append(member)

        if not payload:
            return

        cache_file = ChatView._group_members_cache_file(self, room_id, cache_name)
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"ChatView: 已保存群成员缓存 room_id={room_id}, file={cache_file.name}, count={len(payload)}")
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"ChatView: 保存群成员缓存失败 room_id={room_id}, error={e}")

    def _delete_persisted_group_members(self, room_id: str, cache_name: str = "", room_name: str = ""):
        room_id = str(room_id or "").strip()
        if not room_id:
            return False

        removed = False
        candidate_files = {
            ChatView._legacy_group_members_cache_file(self, room_id),
        }
        if cache_name:
            candidate_files.add(ChatView._group_members_cache_file(self, room_id, cache_name))
        if room_name:
            candidate_files.add(ChatView._group_members_cache_file(self, room_id, room_name))
        for cache_file in candidate_files:
            try:
                cache_file.unlink()
                logger.info(f"ChatView: 已删除群成员缓存 room_id={room_id}, file={cache_file.name}")
                removed = True
            except FileNotFoundError:
                continue
            except OSError as e:
                logger.warning(f"ChatView: 删除群成员缓存失败 room_id={room_id}, error={e}")
        return removed

    def _start_group_members_reload(self, room_id: str):
        room_id = str(room_id or "").strip()
        if not room_id:
            return False

        if self._group_members_worker and self._group_members_worker.isRunning():
            self._pending_group_room_id = room_id
            return False

        self._pending_group_room_id = ""
        self._show_group_members_loading()
        self._group_members_worker = ChatGroupMembersWorker(self.crawler, room_id)
        self._group_members_worker.members_ready.connect(self._on_group_members_loaded)
        self._group_members_worker.start()
        return True

    def _refresh_current_group_members(self):
        room_id = str(self._current_group_room_id or "").strip()
        room_name = str(self._current_group_room_name or self._group_name_by_room_id.get(room_id, "") or "").strip()
        cache_name = str(self._current_group_cache_name or self._group_cache_name_by_room_id.get(room_id, "") or "").strip()
        if not room_id:
            return

        self._group_members_cache.pop(room_id, None)
        ChatView._delete_persisted_group_members(self, room_id, cache_name, room_name)
        if hasattr(self, "tab_widget") and hasattr(self, "student_tab"):
            self.tab_widget.setCurrentWidget(self.student_tab)
        ChatView._start_group_members_reload(self, room_id)

    def _load_group_members(self, session: dict):
        room_id = self._resolve_group_room_id(session)
        room_name = ChatView._resolve_group_room_name(self, session)
        cache_name = ChatView._resolve_group_cache_name(self, session)
        self._current_group_room_id = room_id
        self._current_group_room_name = room_name
        self._current_group_cache_name = cache_name
        if room_id and room_name:
            self._group_name_by_room_id[room_id] = room_name
        if room_id and cache_name:
            self._group_cache_name_by_room_id[room_id] = cache_name
        ChatView._update_group_refresh_button_state(self)
        if not room_id:
            self.student_list.clear()
            self.student_list.addItem(QListWidgetItem("无法获取群成员"))
            return

        cached = self._group_members_cache.get(room_id)
        if cached is not None:
            if cached:
                self.set_students(cached)
            else:
                self._show_group_members_empty()
            self.tab_widget.setCurrentWidget(self.student_tab)
            return

        persisted = ChatView._load_persisted_group_members(self, room_id, cache_name, room_name)
        if persisted is not None:
            self._group_members_cache[room_id] = persisted
            if persisted:
                self.set_students(persisted)
            else:
                self._show_group_members_empty()
            self.tab_widget.setCurrentWidget(self.student_tab)
            return

        ChatView._start_group_members_reload(self, room_id)

    def _on_group_members_loaded(self, room_id: str, members: list):
        room_id = str(room_id or "")
        cache_name = str(self._group_cache_name_by_room_id.get(room_id, "") or self._current_group_cache_name or "").strip()
        self._group_members_cache[room_id] = members or []
        if members:
            ChatView._persist_group_members(self, room_id, members, cache_name)
        if room_id != self._current_group_room_id:
            pending_room_id = self._pending_group_room_id
            if pending_room_id and pending_room_id != room_id:
                self._pending_group_room_id = ""
                self._load_group_members({"roomId": pending_room_id})
            return
        if members:
            self.set_students(members)
            self.tab_widget.setCurrentWidget(self.student_tab)
        else:
            self._show_group_members_empty()

    def append_message(self, sender: str, text: str, is_self: bool = False, status_text: str = ""):
        """向聊天区域追加一条消息"""
        sender_html = escape(sender or "")
        text_html = escape(text or "").replace("\n", "<br/>")
        status_html = escape(status_text or "")
        if is_self:
            footer = f'<br/><span style="color:#7f7f7f; font-size:12px;">{status_html}</span>' if status_html else ""
            html = f'<div style="text-align:right; margin:6px 0;"><span style="color:#007acc; font-weight:bold;">我</span><br/><span style="color:#cccccc;">{text_html}</span>{footer}</div>'
        else:
            html = f'<div style="text-align:left; margin:6px 0;"><span style="color:#4ec9b0; font-weight:bold;">{sender_html}</span><br/><span style="color:#cccccc;">{text_html}</span></div>'
        self.chat_messages.append(html)

    def clear_chat(self):
        """清空聊天区域"""
        self.chat_messages.clear()

    def _conversation_key(self, peer_id: str = None, history_id: str = None) -> str:
        history_id = history_id if history_id is not None else self._current_history_id
        peer_id = peer_id if peer_id is not None else self._current_target_id
        return str(history_id or peer_id or "")

    def _message_sort_key(self, msg: dict):
        timestamp = msg.get("timestamp") or 0
        try:
            timestamp = int(timestamp)
        except Exception:
            timestamp = 0

        message_id = str(msg.get("message_id") or "")
        try:
            message_id_sort = int(message_id)
        except Exception:
            message_id_sort = 0

        return (
            0 if timestamp > 0 else 1,
            timestamp,
            message_id_sort,
        )

    def _message_identity(self, msg: dict):
        message_id = str(msg.get("message_id") or "")
        if message_id:
            return ("message_id", message_id)
        return (
            "content",
            str(msg.get("sender_id") or ""),
            str(msg.get("content") or ""),
            int(msg.get("timestamp") or 0),
            bool(msg.get("is_self")),
        )

    def _merge_read_state(self, old_state: str, new_state: str):
        priority = {
            "": 0,
            "unknown": 1,
            "unread": 2,
            "read": 3,
        }
        old_state = str(old_state or "")
        new_state = str(new_state or "")
        return new_state if priority.get(new_state, 0) > priority.get(old_state, 0) else old_state

    def _apply_pending_read_ack(self, message: dict):
        message_id = str(message.get("message_id") or "")
        if not message_id:
            return
        read_at = int(self._pending_read_acks.get(message_id, 0) or 0)
        if read_at:
            message["read_state"] = "read"
            message["read_at"] = max(int(message.get("read_at") or 0), read_at)

    def _find_cached_message(self, cache: list, message: dict):
        message_id = str(message.get("message_id") or "")
        if message_id:
            for item in cache:
                if str(item.get("message_id") or "") == message_id:
                    return item

            if message.get("is_self"):
                message_ts = int(message.get("timestamp") or 0)
                for item in cache:
                    item_ts = int(item.get("timestamp") or 0)
                    if item.get("is_self") != message.get("is_self"):
                        continue
                    if str(item.get("sender_id") or "") != str(message.get("sender_id") or ""):
                        continue
                    if str(item.get("content") or "") != str(message.get("content") or ""):
                        continue
                    if item.get("message_id"):
                        continue
                    if not item_ts or not message_ts or abs(item_ts - message_ts) <= 120000:
                        return item

        identity = self._message_identity(message)
        for item in cache:
            if self._message_identity(item) == identity:
                return item
        return None

    def _merge_cached_entry(self, current: dict, incoming: dict):
        for key in ("sender_id", "sender_name", "content", "message_id"):
            value = incoming.get(key)
            if value and (not current.get(key) or key == "message_id"):
                current[key] = value

        if incoming.get("timestamp"):
            incoming_ts = int(incoming.get("timestamp") or 0)
            current_ts = int(current.get("timestamp") or 0)
            if not current_ts or (incoming.get("message_id") and not current.get("message_id")):
                current["timestamp"] = incoming_ts
            elif incoming_ts and abs(incoming_ts - current_ts) <= 120000:
                current["timestamp"] = min(current_ts, incoming_ts) if current_ts else incoming_ts

        if incoming.get("is_self"):
            current["is_self"] = True

        current["read_state"] = self._merge_read_state(current.get("read_state", ""), incoming.get("read_state", ""))
        current["read_at"] = max(int(current.get("read_at") or 0), int(incoming.get("read_at") or 0))
        self._apply_pending_read_ack(current)

    def _merge_cached_messages(self, conversation_key: str, messages: list[dict]):
        cache = self._message_cache.setdefault(conversation_key, [])
        for message in messages:
            self._apply_pending_read_ack(message)
            existing = self._find_cached_message(cache, message)
            if existing:
                self._merge_cached_entry(existing, message)
                continue
            cache.append(message)
        cache.sort(key=self._message_sort_key)
        return cache

    def _message_status_text(self, msg: dict):
        if not msg.get("is_self"):
            return ""
        state = str(msg.get("read_state") or "")
        if state == "read":
            return "已读"
        if state == "unread":
            return "未读"
        return ""

    def _is_ai_assistant_conversation(self, peer_id: str, msg: dict = None):
        peer_id = str(peer_id or "")
        msg = msg or {}
        ai_ids = {"340857874", "admin"}
        if peer_id in ai_ids:
            return True

        from_user = str(msg.get("from", "") or "")
        to_user = str(msg.get("to", "") or "")
        if from_user in ai_ids or to_user in ai_ids:
            return True

        current_name = str(self._current_target_name or "")
        return "AI助教" in current_name or "AI 助教" in current_name

    def _mark_previous_self_messages_read(self, conversation_key: str, read_at: int = 0):
        cache = self._message_cache.get(conversation_key, [])
        updated = False
        read_at = int(read_at or 0)
        for item in cache:
            if not item.get("is_self"):
                continue
            if str(item.get("read_state") or "") == "read":
                continue
            item["read_state"] = "read"
            item["read_at"] = max(int(item.get("read_at") or 0), read_at)
            updated = True
        return updated

    def _render_cached_messages(self, conversation_key: str = None):
        """渲染本地缓存的消息。"""
        conversation_key = conversation_key or self._conversation_key()
        self.chat_messages.clear()
        self.chat_messages.setPlaceholderText(f"与 {self._current_target_name or '该会话'} 的对话")

        messages = sorted(self._message_cache.get(conversation_key, []), key=self._message_sort_key)
        self._message_cache[conversation_key] = messages
        for msg in messages:
            sender = "我" if msg.get("is_self") else msg.get("sender_name", self._current_target_name or "对方")
            self.append_message(
                sender,
                msg.get("content", ""),
                is_self=msg.get("is_self", False),
                status_text=self._message_status_text(msg),
            )

        if self._last_send_error:
            self.append_message("系统", self._last_send_error, is_self=False)

    def _latest_message_id_for_conversation(self, conversation_key: str = None) -> str:
        conversation_key = conversation_key or self._conversation_key()
        messages = self._message_cache.get(conversation_key, []) or []
        for item in reversed(sorted(messages, key=self._message_sort_key)):
            message_id = str(item.get("message_id") or "")
            if message_id:
                return message_id
        return ""

    def _sync_conversation_read_state(self, peer_id: str = None, history_id: str = None, message_id: str = ""):
        if not hasattr(self.crawler, "request_conversation_read_msync"):
            return False
        peer_id = str(peer_id if peer_id is not None else self._current_target_id or "")
        history_id = str(history_id if history_id is not None else self._current_history_id or "")
        peer_id = ChatView._resolve_active_peer_id(self, peer_id, history_id)
        if not peer_id:
            return False

        conversation_key = self._conversation_key(peer_id=peer_id, history_id=history_id)
        message_id = str(message_id or self._latest_message_id_for_conversation(conversation_key))
        if not message_id:
            return False

        if self._last_read_sync_by_conversation.get(conversation_key) == message_id:
            return False

        if self.crawler.request_conversation_read_msync(peer_id, message_id):
            self._last_read_sync_by_conversation[conversation_key] = message_id
            return True
        return False

    def _append_cached_message(self, sender_id: str, sender_name: str, content: str, is_self: bool, timestamp: int = 0, conversation_key: str = None, message_id: str = "", read_state: str = "", read_at: int = 0):
        """向本地缓存追加一条消息。"""
        conversation_key = conversation_key or self._conversation_key()
        if not conversation_key or not content:
            return

        entry = {
            "sender_id": str(sender_id or ""),
            "sender_name": sender_name or (self._current_target_name or "对方"),
            "content": str(content),
            "is_self": bool(is_self),
            "timestamp": int(timestamp or int(time.time() * 1000)),
            "message_id": str(message_id or ""),
            "read_state": str(read_state or ""),
            "read_at": int(read_at or 0),
        }
        self._apply_pending_read_ack(entry)
        cache = self._message_cache.setdefault(conversation_key, [])
        existing = self._find_cached_message(cache, entry)
        if existing:
            self._merge_cached_entry(existing, entry)
        else:
            cache.append(entry)
        cache.sort(key=self._message_sort_key)

    def _normalize_history_messages(self, messages: list):
        """标准化历史消息结构，供本地缓存与渲染复用。"""
        current_tuid = str(self.crawler.session_manager.course_params.get("im_tuid", "") or "")
        normalized = []
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            timestamp = raw.get("timestamp") or raw.get("updateTime") or raw.get("createTime") or 0
            try:
                timestamp = int(timestamp)
            except Exception:
                timestamp = 0

            sender_id = str(raw.get("from", "") or raw.get("fromUserId", "") or raw.get("tuid", "") or "")
            sender_name = raw.get("fromName") or raw.get("name") or self._current_target_name or "对方"
            content = raw.get("content") or raw.get("msg") or raw.get("message") or ""
            if not content:
                continue

            normalized.append({
                "sender_id": sender_id,
                "sender_name": sender_name,
                "content": str(content),
                "is_self": sender_id == current_tuid,
                "timestamp": timestamp,
                "message_id": str(raw.get("msgId", "") or raw.get("messageId", "") or raw.get("id", "") or ""),
                "read_state": "unread" if sender_id == current_tuid else "",
                "read_at": 0,
            })

        normalized.sort(key=self._message_sort_key)
        return normalized

    # ── 内部方法 ──

    def _show_empty_state(self):
        """显示空状态占位"""
        self.chat_messages.clear()
        self.chat_messages.setPlaceholderText("选择左侧的对话或群组开始聊天")
        self.chat_title_label.setText("选择一个对话")
        self.send_btn.setEnabled(False)

    def _on_chat_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """消息列表选中事件"""
        if not current:
            return
        session = current.data(Qt.ItemDataRole.UserRole + 2) or {}
        target_id = self._resolve_session_peer_id(session) or current.data(Qt.ItemDataRole.UserRole)
        name = current.data(Qt.ItemDataRole.UserRole + 1) or "未知"
        history_id = ChatView._resolve_best_history_key(
            self,
            session,
            peer_id=str(target_id or ""),
            history_id=str(current.data(Qt.ItemDataRole.UserRole + 3) or ""),
        )
        if self._is_group_session(session):
            self._load_group_members(session)
        else:
            self._current_group_room_id = ""
            ChatView._update_group_refresh_button_state(self)
        self._open_chat(target_id, name, history_id=history_id)

    def _on_student_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """学生列表选中事件"""
        if not current:
            return
        target_id = current.data(Qt.ItemDataRole.UserRole)
        name = current.data(Qt.ItemDataRole.UserRole + 1) or "未知"
        history_id = ChatView._resolve_best_history_key(self, peer_id=str(target_id or ""), history_id=self._history_id_by_peer.get(str(target_id), ""))
        self._open_chat(target_id, name, history_id=history_id)

    def _open_chat(self, target_id: str, target_name: str, history_id: str = ""):
        """打开与目标的聊天"""
        self._current_target_id = str(target_id or "")
        self._current_history_id = ChatView._resolve_best_history_key(self, peer_id=self._current_target_id, history_id=history_id) or None
        self._current_target_name = target_name
        self._last_send_error = ""
        self._clear_current_unread_count()
        self.chat_title_label.setText(target_name)
        self.send_btn.setEnabled(bool(target_id))
        conversation_key = self._conversation_key()
        if conversation_key in self._message_cache:
            self._render_cached_messages(conversation_key)
        else:
            self.chat_messages.clear()
            self.chat_messages.setPlaceholderText("正在加载聊天记录...")

        self._ensure_msync_connected()
        self._sync_conversation_read_state()
        if hasattr(self.crawler, "request_history_msync"):
            self.crawler.request_history_msync(ChatView._resolve_active_peer_id(self, self._current_target_id, self._current_history_id) or self._current_target_id)
        if self._current_history_id:
            self._load_current_chat_history()

    def _request_avatar(self, list_widget: QListWidget, item: QListWidgetItem, avatar_url: str):
        if not avatar_url:
            return
        req = QNetworkRequest(QUrl(avatar_url))
        req.setRawHeader(b"Referer", b"https://im.chaoxing.com/")
        req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
        reply = self._net_mgr.get(req)
        self._avatar_requests[reply] = (list_widget, item)
        reply.finished.connect(lambda r=reply: self._on_avatar_reply_finished(r))

    def _on_avatar_reply_finished(self, reply):
        """头像异步加载完成回调"""
        target = self._avatar_requests.pop(reply, None)
        widget = None
        if target:
            list_widget, item = target
            try:
                widget = list_widget.itemWidget(item) if list_widget and item else None
            except RuntimeError:
                widget = None

        if widget and reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                try:
                    widget.set_avatar_pixmap(pixmap)
                except RuntimeError:
                    pass
        reply.deleteLater()

    def _ensure_msync_connected(self):
        """确保 MSync 实时连接已建立"""
        if not hasattr(self.crawler, "is_msync_connected"):
            return
        if self.crawler.is_msync_connected():
            return

        with self._msync_connect_lock:
            if self._msync_connecting:
                return
            self._msync_connecting = True

        def connect_in_background():
            try:
                self.crawler.connect_msync(
                    on_message=lambda msg: self.msync_message_received.emit(msg),
                    on_error=lambda e: logger.error(f"MSync error: {e}"),
                    on_close=lambda c, m: logger.info(f"MSync closed: {c} {m}"),
                    listener_key=self,
                )
                if self._raw_sessions:
                    self._request_unread_summary(self._raw_sessions)
                if self._current_target_id and hasattr(self.crawler, "request_history_msync"):
                    self.crawler.request_history_msync(ChatView._resolve_active_peer_id(self, self._current_target_id, self._current_history_id) or self._current_target_id)
                    self._sync_conversation_read_state()
            except Exception as e:
                logger.error(f"MSync connect failed: {e}")
            finally:
                with self._msync_connect_lock:
                    self._msync_connecting = False

        threading.Thread(target=connect_in_background, name="chat-msync-connect", daemon=True).start()

    def _load_current_chat_history(self, limit: int = 200):
        """异步加载当前会话历史消息。"""
        if not self._current_history_id:
            return
        if self._history_worker and self._history_worker.isRunning() and str(getattr(self._history_worker, "chat_id", "") or "") == str(self._current_history_id):
            return

        worker = ChatHistoryWorker(self.crawler, self._current_history_id, limit=limit)
        worker.history_ready.connect(self._on_history_loaded)
        worker.finished.connect(lambda w=worker: self._history_workers.remove(w) if w in self._history_workers else None)
        self._history_workers.append(worker)
        self._history_worker = worker
        worker.start()

    def _on_history_loaded(self, chat_id: str, messages: list):
        """历史消息加载完成回调。"""
        if str(chat_id) != str(self._current_history_id):
            return
        conversation_key = self._conversation_key(history_id=str(chat_id), peer_id=self._current_target_id)
        normalized = self._normalize_history_messages(messages)
        if normalized:
            self._merge_cached_messages(conversation_key, normalized)
            if self._current_target_id and self._current_history_id and self._current_target_id != self._current_history_id:
                self._history_id_by_peer[self._current_target_id] = self._current_history_id
            self._render_cached_messages(conversation_key)
            self._sync_conversation_read_state(peer_id=self._current_target_id, history_id=str(chat_id))
        elif conversation_key in self._message_cache:
            self._render_cached_messages(conversation_key)
            self._sync_conversation_read_state(peer_id=self._current_target_id, history_id=str(chat_id))
        else:
            self.chat_messages.clear()
            self.chat_messages.setPlaceholderText(f"与 {self._current_target_name or '该会话'} 的对话")
            if self._last_send_error:
                self.append_message("系统", self._last_send_error, is_self=False)

    def _restore_selected_chat(self, chat_id: str):
        """刷新列表后恢复当前选中的会话。"""
        for index in range(self.chat_list.count()):
            item = self.chat_list.item(index)
            item_history_id = item.data(Qt.ItemDataRole.UserRole + 3) or item.data(Qt.ItemDataRole.UserRole)
            if item and item_history_id == chat_id:
                self.chat_list.blockSignals(True)
                self.chat_list.setCurrentItem(item)
                self.chat_list.blockSignals(False)
                return

    def _resolve_message_peer_id(self, msg: dict) -> str:
        """根据 from/to 推断当前消息对应的会话对端。"""
        current_tuid = str(self.crawler.session_manager.course_params.get("im_tuid", "") or "")
        from_user = str(msg.get("from", "") or "")
        to_user = str(msg.get("to", "") or "")

        candidates = [user for user in (from_user, to_user) if user and user != current_tuid]
        if self._current_target_id and self._current_target_id in candidates:
            return self._current_target_id
        if candidates:
            return candidates[0]
        return from_user or to_user

    def _is_current_conversation_message(self, peer_id: str, msg: dict) -> bool:
        if not peer_id:
            return False
        if peer_id == self._current_target_id:
            return True

        history_id = self._history_id_by_peer.get(peer_id, "")
        if history_id and history_id == self._current_history_id:
            return True

        from_user = str(msg.get("from", "") or "")
        to_user = str(msg.get("to", "") or "")
        return self._current_target_id in {from_user, to_user}

    def _is_remote_self_device_message(self, msg: dict, current_tuid: str) -> bool:
        from_user = str(msg.get("from", "") or "")
        to_user = str(msg.get("to", "") or "")
        if from_user != current_tuid or to_user != current_tuid:
            return False

        current_resource = ""
        if hasattr(self.crawler, "get_msync_resource"):
            current_resource = str(self.crawler.get_msync_resource() or "")
        if not current_resource:
            return False

        from_resource = str(msg.get("from_resource", "") or "")
        to_resource = str(msg.get("to_resource", "") or "")
        return bool(
            to_resource == current_resource
            and from_resource
            and from_resource != current_resource
        )

    def _on_msync_message(self, msg: dict):
        """MSync 收到实时消息回调"""
        if msg.get("event") == "read_ack":
            self._on_read_ack(msg)
            return
        if msg.get("event") == "history_summary":
            changed_rows = self._apply_history_summary_unread(msg.get("subjects") or [])
            if changed_rows:
                for row in changed_rows:
                    self._update_session_unread_row(
                        row.get("peer_id", ""),
                        row.get("history_id", ""),
                        row.get("unread_count", 0),
                    )
            return

        peer_id = str(msg.get("peer_id") or self._resolve_message_peer_id(msg) or "")
        self._store_class_info_metadata(peer_id, msg.get("class_info"))
        from_user = str(msg.get("from", "") or "")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", 0)
        current_tuid = str(self.crawler.session_manager.course_params.get("im_tuid", "") or "")
        is_self = from_user == current_tuid and not ChatView._is_remote_self_device_message(self, msg, current_tuid)
        sender_name = "我" if is_self else (
            self._current_target_name if self._is_current_conversation_message(peer_id, msg) else (peer_id or from_user)
        )
        conversation_key = self._conversation_key(
            peer_id=peer_id,
            history_id=self._history_id_by_peer.get(peer_id, ""),
        )
        self._append_cached_message(
            sender_id=peer_id or from_user,
            sender_name=sender_name,
            content=content,
            is_self=is_self,
            timestamp=timestamp,
            conversation_key=conversation_key,
            message_id=str(msg.get("message_id", "") or ""),
            read_state="unread" if is_self else "",
        )

        if not is_self and self._is_ai_assistant_conversation(peer_id, msg):
            self._mark_previous_self_messages_read(conversation_key, read_at=timestamp)

        # 如果当前正在和该用户聊天，直接显示
        if self._is_current_conversation_message(peer_id, msg):
            if not is_self:
                self._set_unread_count(peer_id, 0, history_id=self._history_id_by_peer.get(peer_id, ""))
            self._render_cached_messages(conversation_key)
            if not is_self:
                self._sync_conversation_read_state(
                    peer_id=peer_id,
                    history_id=self._history_id_by_peer.get(peer_id, ""),
                    message_id=str(msg.get("message_id", "") or ""),
                )
        else:
            # 否则刷新会话列表（显示未读）
            if not is_self:
                ChatView._clear_conversation_locally_read_marker(self, peer_id, self._history_id_by_peer.get(peer_id, ""))
                current_unread = self._get_unread_count(peer_id, self._history_id_by_peer.get(peer_id, ""))
                self._set_unread_count(peer_id, current_unread + 1, history_id=self._history_id_by_peer.get(peer_id, ""))
            if self._raw_sessions:
                self._upsert_session_from_message(peer_id, msg, display_name=sender_name if not is_self else "")
            elif msg.get("history_sync"):
                self._refresh_session_list()
            else:
                self._load_message_list()

    def _on_read_ack(self, msg: dict):
        message_id = str(msg.get("message_id") or "")
        if not message_id:
            return

        read_at = int(msg.get("timestamp") or 0)
        self._pending_read_acks[message_id] = max(int(self._pending_read_acks.get(message_id, 0) or 0), read_at)
        unread_count = msg.get("unread_count")
        if unread_count is not None:
            self._set_unread_count(
                str(msg.get("peer_id") or ""),
                unread_count,
                history_id=self._history_id_by_peer.get(self._normalize_unread_peer_id(str(msg.get("peer_id") or "")), ""),
            )

        current_key = self._conversation_key()
        updated_current = False
        for conversation_key, cache in self._message_cache.items():
            for item in cache:
                if str(item.get("message_id") or "") != message_id:
                    continue
                item["read_state"] = "read"
                item["read_at"] = max(int(item.get("read_at") or 0), read_at)
                if conversation_key == current_key:
                    updated_current = True

        if updated_current:
            self._render_cached_messages(current_key)
        if unread_count is not None:
            self._update_session_unread_row(
                str(msg.get("peer_id") or ""),
                self._history_id_by_peer.get(self._normalize_unread_peer_id(str(msg.get("peer_id") or "")), ""),
                unread_count,
            )

    def _on_send(self):
        """发送消息"""
        text = self.msg_input.text().strip()
        if not text or not self._current_target_id:
            return

        # 调用 API 发送
        try:
            self._ensure_msync_connected()
            result = self.crawler.send_message(
                self._current_target_id,
                text,
                target_name=self._current_target_name or "",
                history_chat_id=self._current_history_id or self._current_target_id,
            )
            if result.get("status") == "success":
                self._last_send_error = ""
                self.msg_input.clear()
                current_tuid = str(self.crawler.session_manager.course_params.get("im_tuid", "") or "")
                self._append_cached_message(
                    sender_id=current_tuid,
                    sender_name="我",
                    content=text,
                    is_self=True,
                    timestamp=int(time.time() * 1000),
                    read_state="unread",
                )
                self._render_cached_messages()
                if hasattr(self.crawler, "request_history_msync"):
                    self.crawler.request_history_msync(ChatView._resolve_active_peer_id(self, self._current_target_id, self._current_history_id) or self._current_target_id)
            else:
                self._last_send_error = f"发送失败: {result.get('msg', '未知错误')}"
                self.append_message("系统", self._last_send_error, is_self=False)
        except Exception as e:
            self._last_send_error = f"发送异常: {e}"
            self.append_message("系统", self._last_send_error, is_self=False)

"""
聊天视图 - 左右布局，左侧消息/学生列表，右侧聊天区域
"""
from html import escape
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget,
    QTabWidget, QTextEdit, QLineEdit, QPushButton,
    QSplitter, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QUrl
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from ui.workers import ChatMessageListWorker, ChatHistoryWorker
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
    """自定义会话列表项：头像 + 名字 + 时间"""

    def __init__(self, name: str, time_str: str, avatar_url: str = None, session=None, parent=None):
        super().__init__(parent)
        self._avatar_url = avatar_url
        self._session = session
        self._setup_ui(name, time_str, avatar_url)

    def _setup_ui(self, name: str, time_str: str, avatar_url: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 头像
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(40, 40)
        self.avatar_label.setScaledContents(True)
        self._set_placeholder_avatar(name)
        layout.addWidget(self.avatar_label)

        # 中间：名字
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #cccccc; font-size: 14px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.name_label, stretch=1)

        # 右侧：时间
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.time_label)

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
        self._last_send_error = ""
        self._raw_sessions = []  # 保存原始 API 返回数据
        self._message_cache = {}
        self._history_id_by_peer = {}
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

        # Tab 2: 学生列表
        self.student_list = QListWidget()
        self.student_list.setObjectName("student_list")
        self.student_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.student_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.student_list.currentItemChanged.connect(self._on_student_selected)
        self.tab_widget.addTab(self.student_list, "学生")

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
        self._raw_sessions = sessions
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

    def _resolve_session_peer_id(self, session: dict) -> str:
        """为已有会话解析实时发送目标。"""
        chat_id = session.get("chatId", "")
        if chat_id not in (None, ""):
            return str(chat_id)
        msg_id = str(session.get("msgId", "") or "")
        current_tuid = str(self.crawler.session_manager.course_params.get("im_tuid", "") or "")
        if msg_id and "+" in msg_id:
            left, right = msg_id.split("+", 1)
            if current_tuid and left == current_tuid:
                return right
            if current_tuid and right == current_tuid:
                return left
        return str(chat_id or "")

    def _add_session_item(self, session: dict):
        """向消息列表添加一个自定义会话项（头像+名字+时间）"""
        chat_id = str(session.get("chatId", "") or "")
        name = session.get("chatName", "未知")
        peer_id = self._resolve_session_peer_id(session)
        update_time = session.get("updateTime", 0)
        avatar_url = session.get("chatIco", "")
        if chat_id:
            self._history_id_by_peer[peer_id] = chat_id

        # 清理 avatar_url：如果是 HTML 则提取 src
        if avatar_url and avatar_url.startswith("<"):
            import re
            m = re.search(r'src=["\']([^"\']+)["\']', avatar_url)
            if m:
                avatar_url = m.group(1)

        # 格式化时间
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

        # 创建自定义 widget 项
        item_widget = ChatSessionItem(name, time_str, avatar_url, session)
        item = QListWidgetItem()
        item.setSizeHint(item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, peer_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, name)
        item.setData(Qt.ItemDataRole.UserRole + 2, session)
        item.setData(Qt.ItemDataRole.UserRole + 3, chat_id)

        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, item_widget)

        # 异步加载头像
        if avatar_url:
            req = QNetworkRequest(QUrl(avatar_url))
            req.setRawHeader(b"Referer", b"https://im.chaoxing.com/")
            req.setRawHeader(b"User-Agent", b"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
            reply = self._net_mgr.get(req)
            reply.finished.connect(lambda r=reply, w=item_widget: self._on_avatar_reply_finished(r, w))

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
        self.student_list.clear()
        for stu in students:
            name = stu.get("name", "未知")
            sid = stu.get("student_id", "")
            person_id = stu.get("person_id", "")
            display = f"{name}"
            if sid:
                display += f"  ({sid})"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self.student_list.addItem(item)

    def append_message(self, sender: str, text: str, is_self: bool = False):
        """向聊天区域追加一条消息"""
        sender_html = escape(sender or "")
        text_html = escape(text or "").replace("\n", "<br/>")
        if is_self:
            html = f'<div style="text-align:right; margin:6px 0;"><span style="color:#007acc; font-weight:bold;">我</span><br/><span style="color:#cccccc;">{text_html}</span></div>'
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

    def _render_cached_messages(self, conversation_key: str = None):
        """渲染本地缓存的消息。"""
        conversation_key = conversation_key or self._conversation_key()
        self.chat_messages.clear()
        self.chat_messages.setPlaceholderText(f"与 {self._current_target_name or '该会话'} 的对话")

        for msg in self._message_cache.get(conversation_key, []):
            sender = "我" if msg.get("is_self") else msg.get("sender_name", self._current_target_name or "对方")
            self.append_message(sender, msg.get("content", ""), is_self=msg.get("is_self", False))

        if self._last_send_error:
            self.append_message("系统", self._last_send_error, is_self=False)

    def _append_cached_message(self, sender_id: str, sender_name: str, content: str, is_self: bool, timestamp: int = 0, conversation_key: str = None):
        """向本地缓存追加一条消息。"""
        conversation_key = conversation_key or self._conversation_key()
        if not conversation_key or not content:
            return

        self._message_cache.setdefault(conversation_key, []).append({
            "sender_id": str(sender_id or ""),
            "sender_name": sender_name or (self._current_target_name or "对方"),
            "content": str(content),
            "is_self": bool(is_self),
            "timestamp": int(timestamp or 0),
        })

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
            })

        normalized.sort(key=lambda item: item["timestamp"])
        return normalized

    # ── 内部方法 ──

    def _show_empty_state(self):
        """显示空状态占位"""
        self.chat_messages.clear()
        self.chat_messages.setPlaceholderText("选择左侧的对话或学生开始聊天")
        self.chat_title_label.setText("选择一个对话")
        self.send_btn.setEnabled(False)

    def _on_chat_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """消息列表选中事件"""
        if not current:
            return
        target_id = current.data(Qt.ItemDataRole.UserRole)
        name = current.data(Qt.ItemDataRole.UserRole + 1) or "未知"
        history_id = current.data(Qt.ItemDataRole.UserRole + 3) or ""
        self._open_chat(target_id, name, history_id=history_id)

    def _on_student_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """学生列表选中事件"""
        if not current:
            return
        target_id = current.data(Qt.ItemDataRole.UserRole)
        name = current.data(Qt.ItemDataRole.UserRole + 1) or "未知"
        history_id = self._history_id_by_peer.get(str(target_id), "")
        self._open_chat(target_id, name, history_id=history_id)

    def _open_chat(self, target_id: str, target_name: str, history_id: str = ""):
        """打开与目标的聊天"""
        self._current_target_id = str(target_id or "")
        self._current_history_id = str(history_id or "") or None
        self._current_target_name = target_name
        self._last_send_error = ""
        self.chat_title_label.setText(target_name)
        self.send_btn.setEnabled(bool(target_id))
        conversation_key = self._conversation_key()
        if conversation_key in self._message_cache:
            self._render_cached_messages(conversation_key)
        else:
            self.chat_messages.clear()
            self.chat_messages.setPlaceholderText("正在加载聊天记录...")

        if self._current_history_id:
            self._load_current_chat_history()

    def _on_avatar_reply_finished(self, reply, widget):
        """头像异步加载完成回调"""
        if widget and reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                widget.set_avatar_pixmap(pixmap)
        reply.deleteLater()

    def _ensure_msync_connected(self):
        """确保 MSync 实时连接已建立"""
        if hasattr(self.crawler, "is_msync_connected") and not self.crawler.is_msync_connected():
            try:
                self.crawler.connect_msync(
                    on_message=lambda msg: self.msync_message_received.emit(msg),
                    on_error=lambda e: logger.error(f"MSync error: {e}"),
                    on_close=lambda c, m: logger.info(f"MSync closed: {c} {m}"),
                )
            except Exception as e:
                logger.error(f"MSync connect failed: {e}")

    def _load_current_chat_history(self, limit: int = 50):
        """异步加载当前会话历史消息。"""
        if not self._current_history_id:
            return
        if self._history_worker and self._history_worker.isRunning():
            return

        self._history_worker = ChatHistoryWorker(self.crawler, self._current_history_id, limit=limit)
        self._history_worker.history_ready.connect(self._on_history_loaded)
        self._history_worker.start()

    def _on_history_loaded(self, chat_id: str, messages: list):
        """历史消息加载完成回调。"""
        if str(chat_id) != str(self._current_history_id):
            return
        conversation_key = self._conversation_key(history_id=str(chat_id), peer_id=self._current_target_id)
        normalized = self._normalize_history_messages(messages)
        if normalized:
            self._message_cache[conversation_key] = normalized
            if self._current_target_id and self._current_history_id and self._current_target_id != self._current_history_id:
                self._history_id_by_peer[self._current_target_id] = self._current_history_id
            self._render_cached_messages(conversation_key)
        elif conversation_key in self._message_cache:
            self._render_cached_messages(conversation_key)
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

    def _on_msync_message(self, msg: dict):
        """MSync 收到实时消息回调"""
        from_user = str(msg.get("from", "") or "")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", 0)
        conversation_key = self._conversation_key(
            peer_id=from_user,
            history_id=self._history_id_by_peer.get(from_user, ""),
        )
        self._append_cached_message(
            sender_id=from_user,
            sender_name=self._current_target_name if self._current_target_id == from_user else from_user,
            content=content,
            is_self=False,
            timestamp=timestamp,
            conversation_key=conversation_key,
        )

        # 如果当前正在和该用户聊天，直接显示
        if self._current_target_id == from_user:
            self.append_message(self._current_target_name or from_user, content, is_self=False)
        else:
            # 否则刷新会话列表（显示未读）
            self._load_message_list()

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
                )
                self.append_message("我", text, is_self=True)
            else:
                self._last_send_error = f"发送失败: {result.get('msg', '未知错误')}"
                self.append_message("系统", self._last_send_error, is_self=False)
        except Exception as e:
            self._last_send_error = f"发送异常: {e}"
            self.append_message("系统", self._last_send_error, is_self=False)

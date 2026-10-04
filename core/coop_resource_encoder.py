from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class CoopResourceEncoder(QObject):
    """Use Chaoxing's own web editor to encode cooperative rich text."""

    encoded = pyqtSignal(str)
    failed = pyqtSignal(str)

    EDITOR_URL = "https://noteyd.chaoxing.com/pc/"

    def __init__(self, session, note_cid, parent=None, editor_type=1):
        super().__init__(parent)
        self._session = session
        self._note_cid = str(note_cid)
        self._editor_type = int(editor_type)
        self._loaded_resource = None
        self._requested_resource = None
        self._profile = QWebEngineProfile(self)
        self._page = QWebEnginePage(self._profile, self)
        self._html = ""
        self._title = ""
        self._ready = False
        self._loading = False
        self._pending = None
        self._on_encoded_callback = None
        self._on_failed_callback = None
        self._on_editor_html_callback = None
        self._on_editor_html_failed_callback = None
        self._editor_html_attempts = 0
        self._ready_timer = QTimer(self)
        self._ready_timer.setInterval(250)
        self._ready_timer.timeout.connect(self._check_ready)
        self._page.loadFinished.connect(self._on_loaded)

    def set_note_cid(self, note_cid):
        note_cid = str(note_cid)
        if note_cid != self._note_cid:
            self._note_cid = note_cid
            self._ready = False
            self._loaded_resource = None
            self._requested_resource = None

    def set_editor_type(self, editor_type):
        editor_type = int(editor_type)
        if editor_type != self._editor_type:
            self._editor_type = editor_type
            self._ready = False
            self._loaded_resource = None
            self._requested_resource = None

    @staticmethod
    def _build_editor_url(note_cid, editor_type):
        return QUrl(
            f"{CoopResourceEncoder.EDITOR_URL}{note_cid}"
            f"?isEdit=1&type={int(editor_type)}"
        )

    def prepare(self):
        """Start loading the editor without waiting for content to be saved."""
        if self._ready or self._loading:
            return
        self._loading = True
        self._set_cookies()
        self._page.load(self._build_editor_url(self._note_cid, self._editor_type))

    def encode(self, html, title="", on_encoded=None, on_failed=None):
        self._html = str(html or "")
        self._title = str(title or "")
        self._on_encoded_callback = on_encoded
        self._on_failed_callback = on_failed
        if self._ready:
            self._run_encoder()
            return
        self._pending = True
        self.prepare()

    def load_editor_html(self, on_loaded, on_failed=None, resource=None):
        self._on_editor_html_callback = on_loaded
        self._on_editor_html_failed_callback = on_failed
        self._editor_html_attempts = 0
        self._requested_resource = resource
        if self._ready:
            if (
                self._loaded_resource is not None
                and resource is not None
                and resource != self._loaded_resource
            ):
                self._ready = False
                self._loading = False
            else:
                if self._loaded_resource is None:
                    self._loaded_resource = resource
                self._read_editor_html()
                return
        self.prepare()

    def _set_cookies(self):
        store = self._profile.cookieStore()
        for name, value in self._session.cookies.get_dict().items():
            cookie = QNetworkCookie(name.encode(), value.encode())
            cookie.setDomain(".chaoxing.com")
            cookie.setPath("/")
            store.setCookie(cookie, QUrl("https://noteyd.chaoxing.com"))

    def _on_loaded(self, success):
        self._loading = False
        if not success:
            if self._on_editor_html_failed_callback:
                callback = self._on_editor_html_failed_callback
                self._on_editor_html_callback = None
                self._on_editor_html_failed_callback = None
                callback("无法加载学习通笔记编辑器，未打开编辑界面")
            self._fail("无法加载学习通网页编辑器")
            return
        self._ready_timer.start()

    def _check_ready(self):
        self._page.runJavaScript(
            "typeof window.cxeditor !== 'undefined' && "
            "typeof window.cxeditor.htmlToCoopResource === 'function'",
            self._on_ready,
        )

    def _on_ready(self, ready):
        if not ready:
            return
        self._ready_timer.stop()
        self._ready = True
        if self._on_editor_html_callback:
            self._read_editor_html()
        elif self._pending:
            self._run_encoder()

    def _read_editor_html(self):
        script = (
            "(() => { const id = "
            f"{self._js_string(self._note_cid)}; "
            "const editor = window.cxeditor.allInstance && "
            "window.cxeditor.allInstance.find(item => item.id === id); "
            "return editor ? window.cxeditor.getHTML(id) : null; })()"
        )
        self._page.runJavaScript(script, self._on_editor_html_loaded)

    def _on_editor_html_loaded(self, html):
        if isinstance(html, str):
            self._loaded_resource = self._requested_resource
            callback = self._on_editor_html_callback
            self._on_editor_html_callback = None
            self._on_editor_html_failed_callback = None
            if callback:
                callback(html)
            return

        self._editor_html_attempts += 1
        if self._editor_html_attempts >= 40:
            callback = self._on_editor_html_failed_callback
            self._on_editor_html_callback = None
            self._on_editor_html_failed_callback = None
            if callback:
                callback("学习通尚未加载笔记正文，未打开编辑界面")
            return
        QTimer.singleShot(250, self._read_editor_html)

    def _run_encoder(self):
        self._pending = None
        script = (
            "window.cxeditor.htmlToCoopResource(" 
            f"{self._js_string(self._html)}, {self._js_string(self._title)})"
        )
        self._page.runJavaScript(script, self._on_encoded)

    def _on_encoded(self, resource):
        if isinstance(resource, str) and resource:
            callback = self._on_encoded_callback
            self._on_encoded_callback = None
            if callback:
                QTimer.singleShot(
                    0, lambda result=resource: callback(result)
                )
            self.encoded.emit(resource)
        else:
            self._fail("学习通编辑器未生成 coopResource")

    def _fail(self, message):
        callback = self._on_failed_callback
        self._on_failed_callback = None
        if callback:
            QTimer.singleShot(0, lambda error=message: callback(error))
        self.failed.emit(message)

    @staticmethod
    def _js_string(value):
        escaped = (
            str(value).replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("</", "<\\/")
        )
        return "'" + escaped + "'"
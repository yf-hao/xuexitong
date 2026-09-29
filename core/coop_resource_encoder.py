from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class CoopResourceEncoder(QObject):
    """Use Chaoxing's own web editor to encode cooperative rich text."""

    encoded = pyqtSignal(str)
    failed = pyqtSignal(str)

    EDITOR_URL = "https://noteyd.chaoxing.com/pc/"

    def __init__(self, session, note_cid, parent=None):
        super().__init__(parent)
        self._session = session
        self._note_cid = str(note_cid)
        self._profile = QWebEngineProfile(self)
        self._page = QWebEnginePage(self._profile, self)
        self._html = ""
        self._title = ""
        self._ready = False
        self._loading = False
        self._pending = None
        self._on_encoded_callback = None
        self._on_failed_callback = None
        self._ready_timer = QTimer(self)
        self._ready_timer.setInterval(250)
        self._ready_timer.timeout.connect(self._check_ready)
        self._page.loadFinished.connect(self._on_loaded)

    def set_note_cid(self, note_cid):
        note_cid = str(note_cid)
        if note_cid != self._note_cid:
            self._note_cid = note_cid
            self._ready = False

    def prepare(self):
        """Start loading the editor without waiting for content to be saved."""
        if self._ready or self._loading:
            return
        self._loading = True
        self._set_cookies()
        self._page.load(QUrl(f"{self.EDITOR_URL}{self._note_cid}?isEdit=1&type=1"))

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
        self._run_encoder()

    def _run_encoder(self):
        self._pending = None
        script = (
            "window.cxeditor.htmlToCoopResource(" 
            f"{self._js_string(self._html)}, {self._js_string(self._title)})"
        )
        self._page.runJavaScript(script, self._on_encoded)

    def _on_encoded(self, resource):
        if isinstance(resource, str) and resource:
            if self._on_encoded_callback:
                self._on_encoded_callback(resource)
            self.encoded.emit(resource)
        else:
            self._fail("学习通编辑器未生成 coopResource")

    def _fail(self, message):
        if self._on_failed_callback:
            self._on_failed_callback(message)
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
from __future__ import annotations

import json
import os
import sys
import threading
from functools import lru_cache

from core.config import BASE_DIR


class _KaTeXRenderBridge:
    def __init__(self, app):
        from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

        class _BridgeObject(QObject):
            render_requested = pyqtSignal(object)

            def __init__(self, owner):
                super().__init__()
                self._owner = owner
                self.render_requested.connect(self._handle_request)

            @pyqtSlot(object)
            def _handle_request(self, payload):
                try:
                    payload["result"] = KaTeXSnapshotRenderer._render_to_png_in_gui_thread(
                        payload["expr"],
                        payload["display_mode"],
                    )
                except Exception as exc:
                    payload["error"] = exc
                finally:
                    payload["event"].set()

        self.object = _BridgeObject(self)
        self.object.moveToThread(app.thread())

    def request(self, expr: str, display_mode: bool):
        payload = {
            "expr": expr,
            "display_mode": display_mode,
            "event": threading.Event(),
            "result": None,
            "error": None,
        }
        self.object.render_requested.emit(payload)
        payload["event"].wait(20)
        if payload.get("error"):
            return None
        return payload.get("result")


class KaTeXSnapshotRenderer:
    """Render a single LaTeX expression to PNG bytes via local KaTeX + Qt WebEngine."""

    _KATEX_DIR = os.path.join(BASE_DIR, "assets", "katex")
    _CAPTURE_SCALE = 2

    @classmethod
    def _looks_blank(cls, image) -> bool:
        width = image.width()
        height = image.height()
        if width <= 0 or height <= 0:
            return True

        step_x = max(width // 120, 1)
        step_y = max(height // 120, 1)
        non_white_samples = 0
        total_samples = 0

        for y in range(0, height, step_y):
            for x in range(0, width, step_x):
                color = image.pixelColor(x, y)
                total_samples += 1
                if color.alpha() < 245 or color.red() < 245 or color.green() < 245 or color.blue() < 245:
                    non_white_samples += 1
                    if non_white_samples >= 8:
                        return False

        return non_white_samples == 0 or (total_samples > 0 and non_white_samples / total_samples < 0.003)

    @classmethod
    @lru_cache(maxsize=1)
    def _load_assets(cls) -> tuple[str, str, str]:
        def read_asset(name: str) -> str:
            path = os.path.join(cls._KATEX_DIR, name)
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        return (
            read_asset("katex.min.css"),
            read_asset("katex.min.js"),
            read_asset("auto-render.min.js"),
        )

    @classmethod
    def _build_html(cls, expr: str, display_mode: bool) -> str:
        """Build a minimal HTML that references KaTeX files via file:// links.

        IMPORTANT: We must NOT inline katex.min.css (1.4 MB) or katex.min.js
        (271 KB) into the HTML string.  Qt's setHtml() truncates content larger
        than ~2 MB, which silently breaks KaTeX rendering.  Instead we write a
        thin HTML that uses <link> / <script src> tags pointing to the actual
        files on disk so the browser can stream them without size limits.
        """
        expr_json = json.dumps(expr)
        display_json = "true" if display_mode else "false"
        # Use POSIX-style path so QUrl.fromLocalFile can parse it correctly on
        # all platforms (Windows included via Qt's own normalisation).
        katex_dir_url = cls._KATEX_DIR.replace("\\", "/")
        if not katex_dir_url.startswith("/"):
            # Windows absolute path like C:/... → needs a leading slash for file URL
            katex_dir_url = "/" + katex_dir_url
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            background: transparent;
            overflow: visible;
        }}
        body {{
            display: inline-block;
            color: #000000;
        }}
        #formula {{
            display: inline-block;
            padding: 1px 4px 3px 4px;
            background: transparent;
        }}
    </style>
    <link rel="stylesheet" href="file://{katex_dir_url}/katex.min.css">
</head>
<body>
    <div id="formula"></div>
    <script src="file://{katex_dir_url}/katex.min.js"></script>
    <script>
        (() => {{
            const root = document.getElementById("formula");
            window.__renderError = "";
            try {{
                katex.render({expr_json}, root, {{
                    displayMode: {display_json},
                    throwOnError: true,
                    strict: "ignore",
                    trust: false
                }});
            }} catch (error) {{
                window.__renderError = error && error.message ? error.message : String(error);
                root.textContent = "";
            }}
        }})();
    </script>
</body>
</html>"""

    @classmethod
    @lru_cache(maxsize=1)
    def _get_render_bridge(cls):
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return None

        app = QApplication.instance()
        if app is None:
            return None
        return _KaTeXRenderBridge(app)

    @classmethod
    def render_to_png(cls, expr: str, display_mode: bool = False) -> tuple[bytes, int, int] | None:
        try:
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return None

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            bridge = cls._get_render_bridge()
            if bridge is None:
                return None
            return bridge.request(expr, display_mode)

        return cls._render_to_png_in_gui_thread(expr, display_mode)

    @classmethod
    def _render_to_png_in_gui_thread(cls, expr: str, display_mode: bool = False) -> tuple[bytes, int, int] | None:
        try:
            from PyQt6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QTimer, Qt, QUrl
            from PyQt6.QtGui import QColor
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return None

        app = QApplication.instance()
        created_app = False
        if app is None:
            # QWebEngine (Chromium) requires argv[0] to be the program name;
            # passing an empty list causes "Argument list is empty" crash.
            argv = sys.argv if sys.argv else ["katex_snapshot"]
            app = QApplication(argv)
            created_app = True
            app.setQuitOnLastWindowClosed(False)

        html = cls._build_html(expr, display_mode)
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view.resize(32, 32)
        view.setZoomFactor(cls._CAPTURE_SCALE)
        view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        view.show()

        load_loop = QEventLoop()
        load_state = {"ok": False}

        def on_load_finished(ok: bool):
            load_state["ok"] = ok
            load_loop.quit()

        view.loadFinished.connect(on_load_finished)
        # Write HTML to a temp file and load via file:// URL.
        # We MUST NOT use setHtml() with embedded CSS/JS because Qt truncates
        # HTML content larger than ~2 MB, silently breaking KaTeX rendering.
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        )
        try:
            tmp.write(html)
            tmp_path = tmp.name
        finally:
            tmp.close()
        view.load(QUrl.fromLocalFile(tmp_path))
        QTimer.singleShot(5000, load_loop.quit)
        load_loop.exec()
        try:
            view.loadFinished.disconnect(on_load_finished)
        except Exception:
            pass
        if not load_state["ok"]:
            view.close()
            if created_app:
                app.processEvents()
            return None

        def run_js(script: str, timeout_ms: int = 5000):
            loop = QEventLoop()
            result_holder: dict[str, object] = {}

            def on_result(result):
                result_holder["value"] = result
                loop.quit()

            view.page().runJavaScript(script, on_result)
            QTimer.singleShot(timeout_ms, loop.quit)
            loop.exec()
            return result_holder.get("value")

        js_probe = f"""
            (() => {{
                const scale = {cls._CAPTURE_SCALE};
                const root = document.getElementById('formula');
                if (!root) {{
                    return {{ width: 0, height: 0, ready: false, error: 'missing formula root' }};
                }}

                const katexNode = root.querySelector('.katex');
                const fontsReady = !document.fonts || document.fonts.status === 'loaded';
                const rect = root.getBoundingClientRect();
                const rawWidth = Math.max(
                    rect.width,
                    root.scrollWidth * scale,
                    root.offsetWidth * scale
                );
                const rawHeight = Math.max(
                    rect.height,
                    root.scrollHeight * scale,
                    root.offsetHeight * scale
                );
                const extraWidthPadding = 4 * scale;
                const extraHeightPadding = 4 * scale;
                return {{
                    width: Math.ceil(rawWidth + extraWidthPadding),
                    height: Math.ceil(rawHeight + extraHeightPadding),
                    logicalWidth: Math.ceil((rawWidth + extraWidthPadding) / scale),
                    logicalHeight: Math.ceil((rawHeight + extraHeightPadding) / scale),
                    ready: !!katexNode && fontsReady,
                    hasKatex: !!katexNode,
                    fontsStatus: document.fonts ? document.fonts.status : 'unsupported',
                    error: window.__renderError || ''
                }};
            }})();
        """

        result = None
        for _ in range(84):
            app.processEvents()
            result = run_js(js_probe)
            if isinstance(result, dict):
                if result.get("error"):
                    break
                if result.get("ready"):
                    break

            wait_loop = QEventLoop()
            QTimer.singleShot(120, wait_loop.quit)
            wait_loop.exec()

        if (
            not isinstance(result, dict)
            or result.get("error")
            or not result.get("hasKatex")
            or int(result.get("width") or 0) <= 1
            or int(result.get("height") or 0) <= 1
        ):
            view.close()
            if created_app:
                app.processEvents()
            return None

        capture_width = max(int(result.get("width") or 0), 1)
        capture_height = max(int(result.get("height") or 0), 1)
        logical_width = max(int(result.get("logicalWidth") or 0), 1)
        logical_height = max(int(result.get("logicalHeight") or 0), 1)
        view.resize(capture_width, capture_height)
        app.processEvents()

        grab_loop = QEventLoop()
        pixmap_holder = {}

        def grab_view():
            pixmap_holder["pixmap"] = view.grab()
            grab_loop.quit()

        QTimer.singleShot(250, grab_view)
        QTimer.singleShot(5000, grab_loop.quit)
        grab_loop.exec()

        pixmap = pixmap_holder.get("pixmap")
        if pixmap is None or pixmap.isNull():
            view.close()
            if created_app:
                app.processEvents()
            return None

        image = pixmap.toImage()
        if cls._looks_blank(image):
            view.close()
            if created_app:
                app.processEvents()
            return None
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        view.close()
        if created_app:
            app.processEvents()
        return bytes(byte_array), logical_width, logical_height

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
    _shared_view = None
    _is_initializing = False

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
    def _build_base_html(cls) -> str:
        """Build the skeleton HTML that loads KaTeX once."""
        katex_dir_url = cls._KATEX_DIR.replace("\\", "/")
        if not katex_dir_url.startswith("/"):
            katex_dir_url = "/" + katex_dir_url
        
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        html, body {{
            margin: 0;
            padding: 0;
            background: #ffffff;
            overflow: visible;
        }}
        body {{
            display: inline-block;
            color: #000000;
        }}
        #formula {{
            display: inline-block;
            padding: 1px 4px 3px 4px;
            background: #ffffff;
            min-width: 1px;
            min-height: 1px;
        }}
    </style>
    <link rel="stylesheet" href="file://{katex_dir_url}/katex.min.css">
</head>
<body>
    <div id="formula"></div>
    <script src="file://{katex_dir_url}/katex.min.js"></script>
    <script>
        window.checkReady = () => {{
            return typeof katex !== "undefined";
        }};
        window.renderFormula = (expr, displayMode) => {{
            const root = document.getElementById("formula");
            root.innerHTML = "";
            window.__renderError = "";
            try {{
                if (typeof katex === "undefined") {{
                    throw new Error("KaTeX not loaded");
                }}
                katex.render(expr, root, {{
                    displayMode: displayMode,
                    throwOnError: true,
                    strict: "ignore",
                    trust: false
                }});
                
                const rect = root.getBoundingClientRect();
                return {{
                    width: rect.width,
                    height: rect.height,
                    scrollWidth: root.scrollWidth,
                    scrollHeight: root.scrollHeight,
                    ok: true,
                    fontsReady: !document.fonts || document.fonts.status === 'loaded'
                }};
            }} catch (error) {{
                window.__renderError = error.message || String(error);
                return {{ ok: false, error: window.__renderError }};
            }}
        }};
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
        if app is None:
            argv = sys.argv if sys.argv else ["katex_snapshot"]
            app = QApplication(argv)
            app.setQuitOnLastWindowClosed(False)

        # 1. Try Shared View (Singleton)
        try:
            if cls._shared_view is None:
                cls._shared_view = QWebEngineView()
                cls._shared_view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                cls._shared_view.setZoomFactor(cls._CAPTURE_SCALE)
                cls._shared_view.page().setBackgroundColor(QColor(255, 255, 255, 255))
                cls._shared_view.show()
                cls._is_initializing = True

                # Load base environment
                base_html = cls._build_base_html()
                
                loop = QEventLoop()
                cls._shared_view.loadFinished.connect(lambda: loop.quit())
                # Use setHtml with baseUrl
                cls._shared_view.setHtml(base_html, QUrl.fromLocalFile(cls._KATEX_DIR + os.sep))
                QTimer.singleShot(10000, loop.quit)
                loop.exec()
                
                # Additional check for JS readiness
                for _ in range(50):
                    if cls._perform_js_check(cls._shared_view, "window.checkReady && window.checkReady()"):
                        break
                    loop = QEventLoop()
                    QTimer.singleShot(200, loop.quit)
                    loop.exec()
                
                cls._is_initializing = False

            # Try rendering with shared view
            result = cls._perform_render(cls._shared_view, expr, display_mode)
            if result:
                return result
        except Exception as e:
            print(f"Shared renderer failed: {e}")

        # 2. Fallback to One-off View (More robust for CI)
        try:
            temp_view = QWebEngineView()
            temp_view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            temp_view.setZoomFactor(cls._CAPTURE_SCALE)
            temp_view.page().setBackgroundColor(QColor(255, 255, 255, 255))
            temp_view.show()
            
            base_html = cls._build_base_html()
            loop = QEventLoop()
            temp_view.loadFinished.connect(lambda: loop.quit())
            temp_view.setHtml(base_html, QUrl.fromLocalFile(cls._KATEX_DIR + os.sep))
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            
            result = cls._perform_render(temp_view, expr, display_mode)
            temp_view.deleteLater()
            return result
        except Exception as e:
            print(f"Fallback renderer failed: {e}")
            return None

    @classmethod
    def _perform_js_check(cls, view, script):
        loop = QEventLoop()
        res = {"v": None}
        def on_res(v):
            res["v"] = v
            loop.quit()
        view.page().runJavaScript(script, on_res)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        return res.get("v")

    @classmethod
    def _perform_render(cls, view, expr: str, display_mode: bool = False) -> tuple[bytes, int, int] | None:
        try:
            from PyQt6.QtCore import QBuffer, QByteArray, QEventLoop, QTimer, Qt
            from PyQt6.QtWidgets import QApplication
        except Exception:
            return None

        app = QApplication.instance()
        expr_json = json.dumps(expr)
        display_json = "true" if display_mode else "false"
        render_script = f"window.renderFormula({expr_json}, {display_json})"
        
        def run_js_sync(script: str, timeout_ms: int = 5000):
            loop = QEventLoop()
            res = {}
            def on_res(v):
                res["v"] = v
                loop.quit()
            view.page().runJavaScript(script, on_res)
            QTimer.singleShot(timeout_ms, loop.quit)
            loop.exec()
            return res.get("v")

        # Execute render and get dimensions with polling for fonts
        info = None
        for _ in range(50):
            info = run_js_sync(render_script)
            if isinstance(info, dict) and info.get("ok") and info.get("fontsReady"):
                break
            # Wait a bit for fonts
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            app.processEvents()

        if not isinstance(info, dict) or not info.get("ok"):
            if isinstance(info, dict) and "error" in info:
                print(f"KaTeX Render Error: {info['error']}")
            return None

        # 3. Snapshot and Capture
        scale = cls._CAPTURE_SCALE
        raw_w = info.get("width") or info.get("scrollWidth") or 1
        raw_h = info.get("height") or info.get("scrollHeight") or 1
        padding = 4
        
        # Use simple Math helper since we don't have math import here easily
        def ceil(x): return int(x) + (1 if x > int(x) else 0)
        
        capture_w = ceil((raw_w + padding) * scale)
        capture_h = ceil((raw_h + padding) * scale)
        logical_w = ceil(raw_w + padding)
        logical_h = ceil(raw_h + padding)

        view.resize(capture_w, capture_h)
        app.processEvents()

        # Brief wait for resize and paint stability
        grab_loop = QEventLoop()
        pix_holder = {}
        def do_grab():
            pix_holder["pix"] = view.grab()
            grab_loop.quit()
        
        QTimer.singleShot(50, do_grab)
        QTimer.singleShot(1500, grab_loop.quit)
        grab_loop.exec()

        pix = pix_holder.get("pix")
        if pix is None or pix.isNull():
            return None

        image = pix.toImage()
        if cls._looks_blank(image):
            return None

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        buf.close()
        
        return bytes(ba), logical_w, logical_h

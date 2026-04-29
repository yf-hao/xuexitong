from __future__ import annotations

import json
import os
from functools import lru_cache

from core.config import BASE_DIR


class KaTeXSnapshotRenderer:
    """Render a single LaTeX expression to PNG bytes via local KaTeX + Qt WebEngine."""

    _KATEX_DIR = os.path.join(BASE_DIR, "assets", "katex")
    _CAPTURE_SCALE = 2

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
        katex_css, katex_js, _auto_render_js = cls._load_assets()
        expr_json = json.dumps(expr)
        display_json = "true" if display_mode else "false"
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
        }}
    </style>
    <style>{katex_css}</style>
</head>
<body>
    <div id="formula"></div>
    <script>{katex_js}</script>
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
    def render_to_png(cls, expr: str, display_mode: bool = False) -> tuple[bytes, int, int] | None:
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
            app = QApplication([])
            created_app = True
            app.setQuitOnLastWindowClosed(False)

        html = cls._build_html(expr, display_mode)
        view = QWebEngineView()
        view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        view.resize(32, 32)
        view.setZoomFactor(cls._CAPTURE_SCALE)
        view.page().setBackgroundColor(QColor(255, 255, 255, 255))
        view.show()

        load_loop = QEventLoop()
        load_state = {"ok": False}

        def on_load_finished(ok: bool):
            load_state["ok"] = ok
            load_loop.quit()

        view.loadFinished.connect(on_load_finished)
        view.setHtml(html, QUrl.fromLocalFile(cls._KATEX_DIR + os.sep))
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

        size_loop = QEventLoop()
        size_result: dict[str, object] = {}

        def on_size_ready(result):
            size_result["value"] = result
            size_loop.quit()

        QTimer.singleShot(
            120,
            lambda: view.page().runJavaScript(
                f"""
                (() => {{
                    const scale = {cls._CAPTURE_SCALE};
                    const root = document.getElementById('formula');
                    if (!root) {{
                        return {{ width: 0, height: 0, error: 'missing formula root' }};
                    }}
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
                        error: window.__renderError || ''
                    }};
                }})();
                """,
                on_size_ready,
            ),
        )
        QTimer.singleShot(5000, size_loop.quit)
        size_loop.exec()
        result = size_result.get("value")
        if not isinstance(result, dict) or result.get("error"):
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

        QTimer.singleShot(120, grab_view)
        QTimer.singleShot(5000, grab_loop.quit)
        grab_loop.exec()

        pixmap = pixmap_holder.get("pixmap")
        if pixmap is None or pixmap.isNull():
            view.close()
            if created_app:
                app.processEvents()
            return None

        image = pixmap.toImage()
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        view.close()
        if created_app:
            app.processEvents()
        return bytes(byte_array), logical_width, logical_height

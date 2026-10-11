from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.utils.attachment_preview import AttachmentPreviewDocument
from core.logger import get_logger
from core.ui_diagnostics import log_dialog_state
from ui.theme import (
    apply_theme_stylesheet, get_theme_palette, theme_manager,
)

logger = get_logger()


class _AttachmentPreviewPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if (
            navigation_type
            == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        ):
            return False
        return super().acceptNavigationRequest(
            url, navigation_type, is_main_frame
        )


class AttachmentPreviewDialog(QDialog):
    def __init__(self, document: AttachmentPreviewDocument, parent=None):
        super().__init__(parent)
        self._document = document
        self.setWindowTitle(f"附件预览 - {document.title}")
        self.resize(1000, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        if document.warnings:
            warning = QLabel("；".join(document.warnings))
            warning.setWordWrap(True)
            warning.setObjectName("attachment_preview_warning")
            layout.addWidget(warning)

        self.web_view = QWebEngineView(self)
        self.page = _AttachmentPreviewPage(self.web_view)
        self.web_view.setPage(self.page)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.page.renderProcessTerminated.connect(
            self._on_render_process_terminated
        )
        settings = self.page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, False
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PluginsEnabled, False
        )
        layout.addWidget(self.web_view, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        apply_theme_stylesheet(self, lambda palette: f"""
            QDialog {{
                background-color: {palette.panel_bg};
                color: {palette.text};
            }}
            QLabel#attachment_preview_warning {{
                color: {palette.warning};
                padding: 4px;
            }}
            QPushButton {{
                background-color: {palette.panel_alt_bg};
                color: {palette.text};
                border: 1px solid {palette.border};
                border-radius: 4px;
                padding: 5px 14px;
            }}
        """)
        self._apply_document_theme(theme_manager().mode)
        theme_manager().theme_changed.connect(self._apply_document_theme)
        self.finished.connect(
            lambda result: self._log_finished(result)
        )
        self.destroyed.connect(
            lambda *_: logger.info("UI_DIAG preview_dialog_destroyed")
        )

    def _on_load_finished(self, succeeded):
        logger.info("UI_DIAG preview_webengine_load_finished ok=%s", succeeded)

    def _on_render_process_terminated(self, status, exit_code):
        logger.error(
            "UI_DIAG preview_webengine_renderer_terminated status=%s exit_code=%s",
            getattr(status, "name", str(status)),
            exit_code,
        )

    def _log_finished(self, result):
        logger.info("UI_DIAG preview_dialog_finished result=%s", result)
        log_dialog_state("preview_dialog_finished", self)

    def _apply_document_theme(self, mode=None):
        palette = get_theme_palette(mode)
        html = self._document.html.replace(
            "<body>", f'<body data-theme="{palette.mode}">', 1
        )
        theme_variables = f"""<style>
            :root {{
                --preview-bg: {palette.panel_bg};
                --preview-text: {palette.text};
                --preview-code-bg: {palette.panel_alt_bg};
                --preview-border: {palette.border};
                --preview-muted: {palette.text_muted};
                --preview-link: {palette.accent};
            }}
        </style>"""
        html = html.replace("</head>", f"{theme_variables}</head>", 1)
        self.page.setBackgroundColor(QColor(palette.panel_bg))
        logger.info(
            "UI_DIAG preview_webengine_set_html theme=%s chars=%s",
            palette.mode,
            len(html),
        )
        self.web_view.setHtml(html, QUrl("about:blank"))
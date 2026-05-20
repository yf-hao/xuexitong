from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from PyQt6.QtCore import QObject, QEvent, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget


THEME_SETTING_KEY = "ui/theme_mode"
THEME_MODES = ("dark", "light")


@dataclass(frozen=True)
class ThemePalette:
    mode: str
    window_bg: str
    panel_bg: str
    panel_alt_bg: str
    card_bg: str
    hover_bg: str
    input_bg: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_focus: str
    accent_soft: str
    success: str
    success_hover: str
    danger: str
    danger_soft: str
    warning: str
    disabled_bg: str
    disabled_text: str


DARK_THEME = ThemePalette(
    mode="dark",
    window_bg="#121212",
    panel_bg="#1e1e1e",
    panel_alt_bg="#252526",
    card_bg="#1a1a1a",
    hover_bg="#2a2d2e",
    input_bg="#252526",
    border="#333333",
    border_strong="#444444",
    text="#ffffff",
    text_secondary="#e6e6e6",
    text_muted="#aaaaaa",
    accent="#007acc",
    accent_hover="#1a8ad4",
    accent_focus="#0098ff",
    accent_soft="#00bfff",
    success="#28a745",
    success_hover="#218838",
    danger="#ff4d4d",
    danger_soft="#442222",
    warning="#ff5252",
    disabled_bg="#2d2d2d",
    disabled_text="#888888",
)

LIGHT_THEME = ThemePalette(
    mode="light",
    window_bg="#f6f8fa",
    panel_bg="#ffffff",
    panel_alt_bg="#f3f4f6",
    card_bg="#ffffff",
    hover_bg="#edf3ff",
    input_bg="#ffffff",
    border="#d0d7de",
    border_strong="#c2cad3",
    text="#1f2328",
    text_secondary="#24292f",
    text_muted="#57606a",
    accent="#0969da",
    accent_hover="#0550ae",
    accent_focus="#218bff",
    accent_soft="#54aeff",
    success="#1a7f37",
    success_hover="#116329",
    danger="#cf222e",
    danger_soft="#fff1f0",
    warning="#cf222e",
    disabled_bg="#eaeef2",
    disabled_text="#8c959f",
)


def get_theme_settings() -> QSettings:
    return QSettings("HaoSoft", "XuexitongManager")


def get_theme_mode() -> str:
    mode = str(get_theme_settings().value(THEME_SETTING_KEY, "dark") or "dark").strip().lower()
    return mode if mode in THEME_MODES else "dark"


def get_theme_palette(mode: str | None = None) -> ThemePalette:
    return LIGHT_THEME if (mode or get_theme_mode()) == "light" else DARK_THEME


def theme_label(mode: str) -> str:
    return "亮色" if mode == "light" else "暗色"


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._mode = get_theme_mode()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        mode = str(mode or "").strip().lower()
        if mode not in THEME_MODES or mode == self._mode:
            return
        self._mode = mode
        get_theme_settings().setValue(THEME_SETTING_KEY, mode)
        app = QApplication.instance()
        if app is not None:
            apply_application_theme(app, mode)
        self.theme_changed.emit(mode)


_theme_manager: ThemeManager | None = None


def theme_manager() -> ThemeManager:
    global _theme_manager
    if _theme_manager is not None:
        try:
            _theme_manager.mode
        except RuntimeError:
            _theme_manager = None
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def apply_application_theme(app: QApplication, mode: str | None = None):
    palette = get_theme_palette(mode)
    qt_palette = QPalette()
    qt_palette.setColor(QPalette.ColorRole.Window, QColor(palette.window_bg))
    qt_palette.setColor(QPalette.ColorRole.WindowText, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Base, QColor(palette.panel_bg))
    qt_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(palette.panel_alt_bg))
    qt_palette.setColor(QPalette.ColorRole.Text, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Button, QColor(palette.panel_alt_bg))
    qt_palette.setColor(QPalette.ColorRole.ButtonText, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(palette.panel_bg))
    qt_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(palette.text))
    qt_palette.setColor(QPalette.ColorRole.Highlight, QColor(palette.accent))
    qt_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    qt_palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette.text_muted))
    app.setPalette(qt_palette)


_DECLARATION_REPLACEMENTS = [
    ("background-color: #121212;", "background-color: {window_bg};"),
    ("background-color: #161616;", "background-color: {panel_alt_bg};"),
    ("background-color: #1a1a1a;", "background-color: {card_bg};"),
    ("background-color: #1e1e1e;", "background-color: {panel_bg};"),
    ("background-color: #1e1f22;", "background-color: {panel_bg};"),
    ("background-color: #202531;", "background-color: {panel_bg};"),
    ("background-color: #252526;", "background-color: {panel_alt_bg};"),
    ("background-color: #2a2d2e;", "background-color: {hover_bg};"),
    ("background-color: #2a2d31;", "background-color: {hover_bg};"),
    ("background-color: #2d2d2d;", "background-color: {disabled_bg};"),
    ("background-color: #2d2d30;", "background-color: {panel_alt_bg};"),
    ("background-color: #2d2f33;", "background-color: {panel_alt_bg};"),
    ("background-color: #343842;", "background-color: {panel_alt_bg};"),
    ("background-color: #3d434a;", "background-color: {border_strong};"),
    ("background-color: #4a4f55;", "background-color: {border_strong};"),
    ("background-color: #444;", "background-color: {border_strong};"),
    ("background-color: #555;", "background-color: {border_strong};"),
    ("background-color: #333333;", "background-color: {border};"),
    ("background-color: #3d3d3d;", "background-color: {border_strong};"),
    ("background-color: #3c3c3c;", "background-color: {panel_alt_bg};"),
    ("background-color: #3e3e42;", "background-color: {disabled_bg};"),
    ("background-color: #404040;", "background-color: {border_strong};"),
    ("background-color: #444444;", "background-color: {border_strong};"),
    ("background-color: #4e4e52;", "background-color: {border_strong};"),
    ("background-color: #555555;", "background-color: {text_muted};"),
    ("background-color: #094771;", "background-color: {accent};"),
    ("background-color: #007acc;", "background-color: {accent};"),
    ("background-color: #0078d4;", "background-color: {accent};"),
    ("background-color: #0066b8;", "background-color: {accent_hover};"),
    ("background-color: #1177bb;", "background-color: {accent_hover};"),
    ("background-color: #0e639c;", "background-color: {accent_hover};"),
    ("background-color: #0f5d8c;", "background-color: {accent_hover};"),
    ("background-color: #1a8ad4;", "background-color: {accent_hover};"),
    ("background-color: #005a9e;", "background-color: {accent_hover};"),
    ("background-color: #005c99;", "background-color: {accent_hover};"),
    ("background-color: #0098ff;", "background-color: {accent_focus};"),
    ("background-color: #28a745;", "background-color: {success};"),
    ("background-color: #218838;", "background-color: {success_hover};"),
    ("background-color: #4caf50;", "background-color: {success};"),
    ("background-color: #4a6fa5;", "background-color: {accent};"),
    ("background-color: #3d5f90;", "background-color: {accent_hover};"),
    ("background-color: #d9534f;", "background-color: {danger};"),
    ("background-color: #c9302c;", "background-color: {danger};"),
    ("background-color: #ff4d4d;", "background-color: {danger};"),
    ("background-color: #442222;", "background-color: {danger_soft};"),
    ("background-color: #3e2626;", "background-color: {danger_soft};"),
    ("alternate-background-color: #1a1a1a;", "alternate-background-color: {card_bg};"),
    ("alternate-background-color: #252526;", "alternate-background-color: {panel_alt_bg};"),
    ("alternate-background-color: #2d2d2d;", "alternate-background-color: {disabled_bg};"),
    ("background: #2d2d2d;", "background: {panel_alt_bg};"),
    ("background: #252526;", "background: {panel_alt_bg};"),
    ("background: #1e1e1e;", "background: {panel_bg};"),
    ("background: #18191c;", "background: {panel_bg};"),
    ("background: #1a1a1a;", "background: {card_bg};"),
    ("color: white;", "color: {text};"),
    ("color: #ffffff;", "color: {text};"),
    ("color: #fff;", "color: {text};"),
    ("color: #e6e6e6;", "color: {text_secondary};"),
    ("color: #e1e1e1;", "color: {text_secondary};"),
    ("color: #e0e0e0;", "color: {text_secondary};"),
    ("color: #d0d0d0;", "color: {text_secondary};"),
    ("color: #cfd8dc;", "color: {text_muted};"),
    ("color: #dcdcdc;", "color: {text_secondary};"),
    ("color: #cccccc;", "color: {text_secondary};"),
    ("color: #bbbbbb;", "color: {text_muted};"),
    ("color: #aaaaaa;", "color: {text_muted};"),
    ("color: #a0a7b5;", "color: {text_muted};"),
    ("color: #7f8695;", "color: {disabled_text};"),
    ("color: #9cdcfe;", "color: {accent};"),
    ("color: #9a9a9a;", "color: {disabled_text};"),
    ("color: #b8b8b8;", "color: {text_muted};"),
    ("color: #bfc7d5;", "color: {text_muted};"),
    ("color: #888;", "color: {text_muted};"),
    ("color: #888888;", "color: {text_muted};"),
    ("color: #a0a0a0;", "color: {text_muted};"),
    ("color: #666;", "color: {disabled_text};"),
    ("color: #555;", "color: {disabled_text};"),
    ("color: #666666;", "color: {disabled_text};"),
    ("color: #333;", "color: {text};"),
    ("color: #555555;", "color: {text_muted};"),
    ("color: #00bfff;", "color: {accent_soft};"),
    ("color: #007acc;", "color: {accent};"),
    ("color: #569cd6;", "color: {accent};"),
    ("color: #4ec9b0;", "color: {success};"),
    ("color: #d4a72c;", "color: {warning};"),
    ("color: #dcdcaa;", "color: {warning};"),
    ("color: #ff4d4d;", "color: {danger};"),
    ("color: #ff6b6b;", "color: {danger};"),
    ("color: #ff8888;", "color: {danger};"),
    ("color: #ff9f43;", "color: {warning};"),
    ("color: #ff5252;", "color: {warning};"),
    ("border: 1px solid #333333;", "border: 1px solid {border};"),
    ("border: 1px solid #333;", "border: 1px solid {border};"),
    ("border: 1px solid #3d3d3d;", "border: 1px solid {border};"),
    ("border: 1px solid #3e3e42;", "border: 1px solid {border};"),
    ("border: 1px solid #444;", "border: 1px solid {border_strong};"),
    ("border: 1px solid #404040;", "border: 1px solid {border_strong};"),
    ("border: 1px solid #444444;", "border: 1px solid {border_strong};"),
    ("border: 1px solid #4a4a4a;", "border: 1px solid {border_strong};"),
    ("border: 1px solid #555555;", "border: 1px solid {border_strong};"),
    ("border: 1px solid #007acc;", "border: 1px solid {accent};"),
    ("border: 1px solid #ff4d4d;", "border: 1px solid {danger};"),
    ("border: 1px solid #3a3f44;", "border: 1px solid {border_strong};"),
    ("border: 1px dashed #3a3f44;", "border: 1px dashed {border_strong};"),
    ("border-top: 1px solid #252526;", "border-top: 1px solid {border};"),
    ("border-bottom: 1px solid #252526;", "border-bottom: 1px solid {border};"),
    ("border-bottom: 1px solid #2d2d2d;", "border-bottom: 1px solid {border};"),
    ("border-left: 4px solid #00bfff;", "border-left: 4px solid {accent_soft};"),
    ("selection-background-color: #007acc;", "selection-background-color: {accent};"),
]


_FAST_TRANSLATION_HINTS = (
    "#",
    "white",
    "background-color",
    "alternate-background-color",
    "selection-background-color",
    "border:",
    "color:",
)


@lru_cache(maxsize=len(THEME_MODES))
def _formatted_replacements(mode: str) -> tuple[tuple[str, str], ...]:
    palette = get_theme_palette(mode)
    return tuple((source, target.format(**palette.__dict__)) for source, target in _DECLARATION_REPLACEMENTS)


@lru_cache(maxsize=1)
def _compiled_replacement_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (source, re.compile(rf"(?<![-\\w]){re.escape(source)}"))
        for source, _ in _DECLARATION_REPLACEMENTS
    )


@lru_cache(maxsize=512)
def _cached_themed_stylesheet(mode: str, css: str) -> str:
    if mode != "light" or not css:
        return css

    if not any(hint in css for hint in _FAST_TRANSLATION_HINTS):
        return css

    themed = css
    pattern_map = dict(_compiled_replacement_patterns())
    for source, target in _formatted_replacements(mode):
        if source in themed:
            themed = pattern_map[source].sub(target, themed)
    return themed


def themed_stylesheet(css: str, mode: str | None = None) -> str:
    css = str(css or "")
    mode = mode or theme_manager().mode
    return _cached_themed_stylesheet(mode, css)


def _resolve_theme_stylesheet(widget: QWidget, mode: str | None = None) -> str:
    factory = getattr(widget, "_theme_palette_stylesheet_factory", None)
    if callable(factory):
        return str(factory(get_theme_palette(mode or theme_manager().mode)) or "")

    base_css = getattr(widget, "_theme_base_stylesheet", "")
    return themed_stylesheet(str(base_css or ""), mode)


def apply_theme_stylesheet(widget: QWidget, css: str | Callable[[ThemePalette], str], mode: str | None = None):
    if widget is None:
        return
    setattr(widget, "_theme_managed_widget", True)
    binder = getattr(widget, "_theme_binder_ref", None)
    if binder is not None:
        binder.register_widget(widget)
    if callable(css):
        setattr(widget, "_theme_palette_stylesheet_factory", css)
        setattr(widget, "_theme_base_stylesheet", "")
    else:
        setattr(widget, "_theme_palette_stylesheet_factory", None)
        setattr(widget, "_theme_base_stylesheet", str(css or ""))
    _set_widget_stylesheet(widget, _resolve_theme_stylesheet(widget, mode))


def refresh_theme_styles(widget: QWidget, mode: str | None = None):
    if widget is None:
        return

    binder = getattr(widget, "_theme_tree_binder", None)
    targets = binder.iter_widgets() if binder is not None else [widget, *widget.findChildren(QWidget)]
    for target in targets:
        if target is None:
            continue
        has_factory = callable(getattr(target, "_theme_palette_stylesheet_factory", None))
        base_css = getattr(target, "_theme_base_stylesheet", None)
        if has_factory or isinstance(base_css, str):
            _set_widget_stylesheet(target, _resolve_theme_stylesheet(target, mode))


def _flush_scheduled_theme_refresh(widget: QWidget):
    if widget is None:
        return

    mode = getattr(widget, "_theme_pending_refresh_mode", None) or theme_manager().mode
    setattr(widget, "_theme_pending_refresh_mode", None)
    refresh_theme_styles(widget, mode)


def schedule_theme_refresh(widget: QWidget, mode: str | None = None):
    if widget is None:
        return

    setattr(widget, "_theme_pending_refresh_mode", mode or theme_manager().mode)
    timer = getattr(widget, "_theme_refresh_timer", None)
    if timer is None:
        timer = QTimer(widget)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda current_widget=widget: _flush_scheduled_theme_refresh(current_widget))
        setattr(widget, "_theme_refresh_timer", timer)

    if not timer.isActive():
        timer.start(0)


def _set_widget_stylesheet(widget: QWidget, css: str):
    css = str(css or "")
    if getattr(widget, "_theme_applied_stylesheet", None) == css and widget.styleSheet() == css:
        return
    setattr(widget, "_theme_style_syncing", True)
    try:
        widget.setStyleSheet(css)
        setattr(widget, "_theme_applied_stylesheet", css)
    finally:
        setattr(widget, "_theme_style_syncing", False)


def _sync_runtime_stylesheet(widget: QWidget):
    if widget is None or getattr(widget, "_theme_style_syncing", False):
        return

    current_css = widget.styleSheet()
    if not isinstance(current_css, str) or not current_css:
        return

    if current_css == getattr(widget, "_theme_applied_stylesheet", None):
        return

    mode = theme_manager().mode
    factory = getattr(widget, "_theme_palette_stylesheet_factory", None)
    if callable(factory):
        if current_css == _resolve_theme_stylesheet(widget, mode):
            return
        setattr(widget, "_theme_palette_stylesheet_factory", None)

    base_css = getattr(widget, "_theme_base_stylesheet", None)
    expected_css = themed_stylesheet(base_css, mode) if isinstance(base_css, str) else ""
    if isinstance(base_css, str) and current_css == expected_css:
        setattr(widget, "_theme_applied_stylesheet", current_css)
        return

    binder = getattr(widget, "_theme_binder_ref", None)
    if binder is not None:
        binder.register_widget(widget)
    setattr(widget, "_theme_base_stylesheet", current_css)
    themed_css = themed_stylesheet(current_css, mode)
    if themed_css == current_css:
        setattr(widget, "_theme_applied_stylesheet", current_css)
        return
    _set_widget_stylesheet(widget, themed_css)


class _ThemeChildBinder(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets: list[QWidget] = []

    def register_widget(self, widget: QWidget):
        if widget is None or widget in self._widgets:
            return
        self._widgets.append(widget)

    def iter_widgets(self) -> list[QWidget]:
        alive = []
        for widget in self._widgets:
            try:
                widget.objectName()
            except RuntimeError:
                continue
            alive.append(widget)
        self._widgets = alive
        return list(alive)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ChildAdded:
            child = event.child()
            if isinstance(child, QWidget):
                _bind_theme_widget(child, self)
                for descendant in child.findChildren(QWidget):
                    _bind_theme_widget(descendant, self)
        elif event.type() == QEvent.Type.StyleChange and isinstance(watched, QWidget):
            _sync_runtime_stylesheet(watched)
        return False


def _bind_theme_widget(widget: QWidget, binder: _ThemeChildBinder | None = None):
    if widget is None or getattr(widget, "_theme_styles_bound", False):
        return
    current_css = widget.styleSheet()
    setattr(widget, "_theme_styles_bound", True)

    if binder is not None:
        widget.installEventFilter(binder)
        setattr(widget, "_theme_binder_ref", binder)

    if isinstance(current_css, str) and current_css:
        if binder is not None:
            binder.register_widget(widget)
    elif getattr(widget, "_theme_managed_widget", False) and binder is not None:
        binder.register_widget(widget)

    if isinstance(current_css, str) and current_css and not hasattr(widget, "_theme_base_stylesheet"):
        setattr(widget, "_theme_base_stylesheet", current_css)
        _set_widget_stylesheet(widget, _resolve_theme_stylesheet(widget, theme_manager().mode))


def bind_theme_tree(root: QWidget):
    if root is None:
        return

    binder = getattr(root, "_theme_tree_binder", None)
    if binder is None:
        binder = _ThemeChildBinder(root)
        setattr(root, "_theme_tree_binder", binder)

    _bind_theme_widget(root, binder)
    for child in root.findChildren(QWidget):
        _bind_theme_widget(child, binder)

    if not getattr(root, "_theme_tree_connected", False):
        def _refresh(mode: str, widget=root):
            schedule_theme_refresh(widget, mode)

        manager = theme_manager()
        try:
            manager.theme_changed.connect(_refresh)
        except RuntimeError:
            global _theme_manager
            _theme_manager = None
            theme_manager().theme_changed.connect(_refresh)
        setattr(root, "_theme_tree_refresh", _refresh)
        setattr(root, "_theme_tree_connected", True)

    schedule_theme_refresh(root, theme_manager().mode)

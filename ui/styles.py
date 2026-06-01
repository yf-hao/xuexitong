# Stylesheets for the main window and shared statistics cards.


def MAIN_STYLE(palette):
    return f"""
    QMainWindow {{
        background-color: {palette.window_bg};
    }}
    QWidget#central_widget {{
        background-color: {palette.window_bg};
    }}
    QComboBox {{
        border: 1px solid {palette.border};
        background-color: {palette.panel_bg};
        color: {palette.text};
        border-radius: 6px;
        padding: 10px;
        font-size: 14px;
        min-width: 250px;
    }}
    QComboBox::drop-down {{ border: none; width: 30px; }}
    QComboBox::down-arrow {{
        image: none; border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {palette.accent}; margin-top: 2px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {palette.panel_bg}; color: {palette.text};
        border: 1px solid {palette.border_strong}; selection-background-color: {palette.accent};
        selection-color: #ffffff; outline: none;
    }}
    QListView::item {{
        min-height: 45px; padding-left: 10px;
        color: {palette.text}; background-color: transparent;
    }}
    QListView::item:hover {{ background-color: {palette.accent}; color: #ffffff; }}
    QListView::item:selected {{ background-color: {palette.accent_hover}; color: #ffffff; }}

    QListWidget#nav_list {{
        border: 1px solid {palette.border};
        background-color: {palette.panel_alt_bg};
        border-radius: 8px;
        outline: none;
        min-width: 160px;
        font-size: 15px;
    }}
    QListWidget#nav_list::item {{
        padding: 8px 12px;
        color: {palette.text_muted};
        border-bottom: 1px solid {palette.disabled_bg};
        border-left: 4px solid transparent;
    }}
    QListWidget#nav_list::item:hover {{
        background-color: {palette.hover_bg};
        color: {palette.text};
    }}
    QListWidget#nav_list::item:selected {{
        background-color: {palette.accent};
        color: #ffffff;
        border-left: 4px solid {palette.accent_soft};
        border-bottom: 1px solid {palette.disabled_bg};
    }}

    QTreeWidget {{
        border: 1px solid {palette.border};
        background-color: {palette.panel_bg};
        color: {palette.text_secondary};
        border-radius: 10px;
        padding: 5px;
        outline: none;
    }}
    QTreeWidget::item {{ height: 40px; border-bottom: 1px solid {palette.border}; padding-left: 10px; }}
    QTreeWidget::item:hover {{ background-color: {palette.border_strong}; }}
    QTreeWidget::item:selected {{ background-color: {palette.accent}; color: #ffffff; border-left: 4px solid {palette.accent_soft}; }}
    
    QHeaderView::section {{
        background-color: {palette.panel_alt_bg}; color: {palette.text_muted}; padding: 8px;
        border: 1px solid {palette.border}; font-weight: bold;
    }}
    QPushButton {{
        background-color: {palette.accent}; color: #ffffff; border: none;
        padding: 12px 20px; border-radius: 6px; font-size: 16px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {palette.accent_hover}; color: #ffffff; }}
    QPushButton:focus {{
        background-color: {palette.accent_focus};
        border: 2px solid #ffffff;
        outline: none;
        color: #ffffff;
    }}
    QPushButton:disabled {{ background-color: {palette.disabled_bg}; color: {palette.disabled_text}; }}
    
    QMessageBox QPushButton {{
        min-width: 100px;
        font-size: 14px;
        padding: 8px 15px;
    }}
    QMessageBox QLabel {{ color: {palette.text}; font-size: 14px; font-weight: normal; }}
    QLabel {{ color: {palette.text}; font-size: 16px; font-weight: bold; background: transparent; }}
"""


def stat_button_style(palette, highlighted: bool = False):
    border_width = 2 if highlighted else 1
    border_color = palette.accent if highlighted else palette.border
    return f"""
    QPushButton {{
        background-color: {palette.panel_bg};
        color: {palette.text};
        border: {border_width}px solid {border_color};
        padding: 25px;
        border-radius: 12px;
        font-size: 18px;
        font-weight: bold;
        min-width: 180px;
    }}
    QPushButton:hover {{
        background-color: {palette.hover_bg};
        border: 1px solid {palette.accent};
        color: {palette.accent};
    }}
    QPushButton:disabled {{
        color: {palette.disabled_text};
    }}
"""


def STAT_BUTTON_STYLE(palette):
    return stat_button_style(palette, highlighted=False)


def STAT_BUTTON_HIGHLIGHT_STYLE(palette):
    return stat_button_style(palette, highlighted=True)


def STAT_CARD_CONTAINER_STYLE(palette):
    return f"""
    QFrame {{
        background-color: {palette.card_bg};
        border: 1px solid {palette.border};
        border-radius: 12px;
    }}
"""


def STAT_CARD_STYLE(palette):
    return f"""
    QFrame#stats_card {{
        background-color: {palette.panel_alt_bg};
        border: 1px solid {palette.border};
        border-radius: 10px;
        padding: 10px;
    }}
    QFrame#stats_card:hover {{
        border: 1px solid {palette.accent};
        background-color: {palette.hover_bg};
    }}
"""


def STAT_CARD_HIGHLIGHT_STYLE(palette):
    return f"""
    QFrame#stats_card {{
        background-color: {palette.danger_soft};
        border: 2px solid {palette.danger};
        border-radius: 10px;
        padding: 10px;
    }}
"""

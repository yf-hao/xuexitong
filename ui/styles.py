# Stylesheets for the main window

MAIN_STYLE = """
    QMainWindow {
        background-color: #121212;
    }
    QWidget#central_widget {
        background-color: #121212;
    }
    QComboBox {
        border: 1px solid #333333;
        background-color: #1e1e1e;
        color: #ffffff;
        border-radius: 6px;
        padding: 10px;
        font-size: 14px;
        min-width: 250px;
    }
    QComboBox::drop-down { border: none; width: 30px; }
    QComboBox::down-arrow {
        image: none; border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid #007acc; margin-top: 2px;
    }
    QComboBox QAbstractItemView {
        background-color: #1e1e1e; color: #ffffff;
        border: 1px solid #444444; selection-background-color: #007acc;
        selection-color: #ffffff; outline: none;
    }
    QListView::item {
        min-height: 45px; padding-left: 10px;
        color: #ffffff; background-color: transparent;
    }
    QListView::item:hover { background-color: #007acc; color: #ffffff; }
    QListView::item:selected { background-color: #005a9e; color: #ffffff; }

    QListWidget#nav_list {
        border: 1px solid #333333;
        background-color: #161616;
        border-radius: 8px;
        outline: none;
        min-width: 160px;
        font-size: 15px;
    }
    QListWidget#nav_list::item {
        padding: 8px 12px;
        color: #aaaaaa;
        border-bottom: 1px solid #2d2d2d;
        border-left: 4px solid transparent; /* Placeholder to prevent jumping */
    }
    QListWidget#nav_list::item:hover {
        background-color: #2a2d2e;
        color: #ffffff;
    }
    QListWidget#nav_list::item:selected {
        background-color: #007acc;
        color: #ffffff;
        border-left: 4px solid #00bfff;
        border-bottom: 1px solid #2d2d2d; /* Keep border to maintain height */
    }

    QTreeWidget {
        border: 1px solid #333333;
        background-color: #1e1e1e;
        color: #e1e1e1;
        border-radius: 10px;
        padding: 5px;
        outline: none;
    }
    QTreeWidget::item { height: 40px; border-bottom: 1px solid #252526; padding-left: 10px; }
    QTreeWidget::item:hover { background-color: #3d3d3d; }
    QTreeWidget::item:selected { background-color: #007acc; color: #ffffff; border-left: 4px solid #00bfff; }
    
    QHeaderView::section {
        background-color: #252526; color: #bbbbbb; padding: 8px;
        border: 1px solid #333333; font-weight: bold;
    }
    QPushButton {
        background-color: #007acc; color: white; border: none;
        padding: 12px 20px; border-radius: 6px; font-size: 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #1a8ad4; }
    QPushButton:focus {
        background-color: #0098ff;
        border: 2px solid #ffffff;
        outline: none;
    }
    QPushButton:disabled { background-color: #2d2d2d; color: #888888; }
    
    QMessageBox QPushButton {
        min-width: 100px;
        font-size: 14px;
        padding: 8px 15px;
    }
    QMessageBox QLabel { color: #ffffff; font-size: 14px; font-weight: normal; }
    QLabel { color: #ffffff; font-size: 16px; font-weight: bold; background: transparent; }
"""

STAT_BUTTON_STYLE = """
    QPushButton {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 1px solid #333333;
        padding: 25px;
        border-radius: 12px;
        font-size: 18px;
        font-weight: bold;
        min-width: 180px;
    }
    QPushButton:hover {
        background-color: #2a2d2e;
        border: 1px solid #007acc;
        color: #007acc;
    }
"""

STAT_CARD_CONTAINER_STYLE = """
    QFrame {
        background-color: #1a1a1a;
        border: 1px solid #333333;
        border-radius: 12px;
    }
"""

STAT_CARD_STYLE = """
    QFrame#stats_card {
        background-color: #252526;
        border: 1px solid #333333;
        border-radius: 10px;
        padding: 10px;
    }
    QFrame#stats_card:hover {
        border: 1px solid #007acc;
        background-color: #2a2d2e;
    }
"""

STAT_CARD_HIGHLIGHT_STYLE = """
    QFrame#stats_card {
        background-color: #3e2626;
        border: 2px solid #ff4d4d;
        border-radius: 10px;
        padding: 10px;
    }
"""

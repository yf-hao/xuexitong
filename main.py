import sys
import os

# 1. 立即确定数据目录并启动日志，以捕捉导入阶段的崩溃
def _setup_early_logging():
    if sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/XuexitongManager")
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XuexitongManager")
    else:
        path = os.path.expanduser("~/.xuexitongmanager")
    
    os.makedirs(path, exist_ok=True)
    log_path = os.path.join(path, "app.log")
    try:
        f = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
        print("=== APP EARLY LOG START ===")
        print(f"Executable: {sys.executable}")
        print(f"Version: 0.5.2")
    except:
        pass

_setup_early_logging()

from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
# QtWebEngineWidgets 必须在 QApplication 创建之前导入
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401

from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from core.crawler import XuexitongCrawler

class AppController:
    def __init__(self):
        self.crawler = XuexitongCrawler()
        self.main_win = None

    def start(self):
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # 防止登录窗口关闭时程序意外退出
        app.setStyle("Fusion")
        
        # Pass crawler to login window for validation
        login_win = LoginWindow(self.crawler)
        if login_win.exec():
            # Login successful,
            try:
                self.main_win = MainWindow(self.crawler)
                self.main_win.show()
                app.setQuitOnLastWindowClosed(True) # 恢复正常退出逻辑
                sys.exit(app.exec())
            except Exception as e:
                import traceback
                from PyQt6.QtWidgets import QMessageBox
                error_trace = traceback.format_exc()
                print(f"FATAL ERROR:\n{error_trace}")
                QMessageBox.critical(None, "程序启动失败", f"发生了未预期的错误:\n{str(e)}\n\n详情请查看日志文件或查看以下堆栈:\n{error_trace}")
                sys.exit(1)
        else:
            sys.exit()

    def handle_login_success(self, phone, password):
        # In a real app, this would be handled asynchronously
        self.crawler.login_by_password(phone, password)

def main():
    controller = AppController()
    controller.start()

if __name__ == "__main__":
    main()

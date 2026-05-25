import sys
import threading
from core.logger import redirect_standard_streams, get_logger

# 1. 立即确定数据目录并启动日志，以捕捉导入阶段的崩溃
def _setup_early_logging():
    logger = get_logger()
    try:
        redirect_standard_streams()
        logger.info("=== APP EARLY LOG START ===")
        logger.info("Executable: %s", sys.executable)
        from core.config import APP_TITLE
        import re
        version_match = re.search(r"V([0-9]+(?:\.[0-9]+)*)", APP_TITLE)
        version_str = version_match.group(1) if version_match else "Unknown"
        logger.info("Version: %s", version_str)
    except:
        pass

_setup_early_logging()

from PyQt6.QtWidgets import QApplication
from ui.theme import apply_application_theme, theme_manager

# 后台预加载线程：在用户登录期间并行加载重依赖模块
_preload_result = {}
_preload_lock = threading.Lock()

def _preload_modules():
    """后台线程预加载 crawler 等重依赖模块，减少登录后等待时间。"""
    try:
        from core.crawler import XuexitongCrawler
        with _preload_lock:
            _preload_result["crawler_cls"] = XuexitongCrawler
    except Exception as e:
        with _preload_lock:
            _preload_result["error"] = e


class AppController:
    def __init__(self):
        self.crawler = None
        self.main_win = None

    def start(self):
        # QtWebEngineWidgets 必须在 QApplication 创建之前导入
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # 防止登录窗口关闭时程序意外退出
        app.setStyle("Fusion")
        apply_application_theme(app, theme_manager().mode)
        
        # 启动后台预加载
        preload_thread = threading.Thread(target=_preload_modules, daemon=True)
        preload_thread.start()
        
        # 获取 crawler（等待预加载完成或直接导入）
        with _preload_lock:
            if "crawler_cls" in _preload_result:
                XuexitongCrawler = _preload_result["crawler_cls"]
            elif "error" in _preload_result:
                raise _preload_result["error"]
            else:
                # 预加载尚未完成，直接导入
                from core.crawler import XuexitongCrawler
        
        preload_thread.join()  # 确保预加载完成
        with _preload_lock:
            if "crawler_cls" in _preload_result:
                XuexitongCrawler = _preload_result["crawler_cls"]
        
        self.crawler = XuexitongCrawler()
        
        # Pass crawler to login window for validation
        from ui.login_window import LoginWindow
        login_win = LoginWindow(self.crawler)
        if login_win.exec():
            # Login successful
            try:
                from ui.main_window import MainWindow
                self.main_win = MainWindow(self.crawler)
                self.main_win.show()
                app.setQuitOnLastWindowClosed(True) # 恢复正常退出逻辑
                sys.exit(app.exec())
            except Exception as e:
                import traceback
                from PyQt6.QtWidgets import QMessageBox
                error_trace = traceback.format_exc()
                get_logger().error("FATAL ERROR:\n%s", error_trace)
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

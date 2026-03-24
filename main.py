import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from ui.login_window import LoginWindow
from ui.main_window import MainWindow
from core.crawler import XuexitongCrawler

class AppController:
    def __init__(self):
        self.crawler = XuexitongCrawler()
        self.main_win = None

    def start(self):
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        
        # Pass crawler to login window for validation
        login_win = LoginWindow(self.crawler)
        if login_win.exec():
            # Login successful, open main window
            self.main_win = MainWindow(self.crawler)
            self.main_win.show()
            sys.exit(app.exec())
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

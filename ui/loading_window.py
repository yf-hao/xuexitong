"""登录成功后、主窗口构建期间显示的加载窗口，避免出现没有任何可见窗口的空档。"""

import time

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from core.config import APP_TITLE
from ui.theme import get_theme_palette, theme_manager


class LoadingWindow(QWidget):
    """无边框圆角卡片：中间旋转圆弧，下方一行提示文字。"""

    CARD_SIZE = (260, 190)
    SPINNER_DIAMETER = 56
    SPINNER_PEN_WIDTH = 5
    FRAME_INTERVAL_MS = 16
    DEGREES_PER_SECOND = 360

    def __init__(self, message="正在进入系统..."):
        super().__init__()
        self._message = message
        self._started_at = time.monotonic()
        self._palette = get_theme_palette(theme_manager().mode)

        # 标题仅用于任务栏显示，窗口本身不绘制标题
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*self.CARD_SIZE)

        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    def set_message(self, text):
        self._message = text
        self.update()

    def show(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        super().show()
        self._started_at = time.monotonic()
        self._timer.start()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)

    def _advance(self):
        self.update()

    def pump(self):
        """在耗时的同步任务之间调用，刷新旋转动画。"""
        self.repaint()
        QApplication.processEvents()

    def _current_angle(self):
        # 按时间计算角度，界面线程短暂阻塞后动画也不会变慢
        elapsed = time.monotonic() - self._started_at
        return -(elapsed * self.DEGREES_PER_SECOND) % 360

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(self._palette.panel_bg))
        painter.setPen(QPen(QColor(self._palette.border), 1))
        painter.drawRoundedRect(card, 16, 16)

        accent = QColor(self._palette.accent)
        d = self.SPINNER_DIAMETER
        spinner = QRectF((self.width() - d) / 2, 44, d, d)

        track = QColor(accent)
        track.setAlpha(45)
        pen = QPen(track, self.SPINNER_PEN_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(spinner)

        pen.setColor(accent)
        painter.setPen(pen)
        # Qt 的角度单位是 1/16 度；旋转弧长固定为 100 度
        painter.drawArc(spinner, int(self._current_angle() * 16), 100 * 16)

        font = QFont(self.font())
        font.setPointSize(11)
        painter.setFont(font)
        painter.setPen(QColor(self._palette.text_muted))
        text_rect = QRectF(0, spinner.bottom() + 22, self.width(), 24)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._message)

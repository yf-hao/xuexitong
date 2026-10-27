"""登录成功后、主窗口构建期间显示的加载窗口，避免出现没有任何可见窗口的空档。"""

import os
import tempfile
import time

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from core.config import APP_TITLE
from ui.theme import get_theme_palette, theme_manager


class WidgetLoadingWindow(QWidget):
    """无边框圆角卡片：中间旋转圆弧，下方一行提示文字。"""

    CARD_SIZE = (300, 260)
    SPINNER_DIAMETER = 100
    SPINNER_PEN_WIDTH = 6
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
        spinner = QRectF((self.width() - d) / 2, 46, d, d)

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
        font.setPointSize(14)
        painter.setFont(font)
        painter.setPen(QColor(self._palette.text_muted))
        text_rect = QRectF(0, spinner.bottom() + 26, self.width(), 32)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._message)


_QML = """
import QtQuick
import QtQuick.Shapes

Rectangle {
    id: card
    property color panelColor: "#ffffff"
    property color borderColor: "#dddddd"
    property color accentColor: "#3b82f6"
    property color textColor: "#666666"
    property string message: ""
    color: panelColor
    radius: 16
    border.color: borderColor
    border.width: 1

    Item {
        id: spinner
        width: 100; height: 100
        x: (card.width - width) / 2
        y: 46

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.GeometryRenderer
            layer.enabled: true
            layer.samples: 4
            ShapePath {
                fillColor: "transparent"
                strokeColor: Qt.rgba(card.accentColor.r, card.accentColor.g, card.accentColor.b, 0.18)
                strokeWidth: 6
                PathAngleArc { centerX: 50; centerY: 50; radiusX: 46.5; radiusY: 46.5; startAngle: 0; sweepAngle: 360 }
            }
        }
        Shape {
            anchors.fill: parent
            layer.enabled: true
            layer.samples: 4
            ShapePath {
                fillColor: "transparent"
                strokeColor: card.accentColor
                strokeWidth: 6
                capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: 50; centerY: 50; radiusX: 46.5; radiusY: 46.5; startAngle: -90; sweepAngle: 100 }
            }
            // RotationAnimator 在渲染线程执行，界面线程被占用时也会继续转动
            RotationAnimator on rotation {
                from: 0; to: 360; duration: 1000
                loops: Animation.Infinite
                running: true
            }
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 46 + 100 + 26
        text: card.message
        color: card.textColor
        font.pointSize: 14
    }
}
"""


class QuickLoadingWindow:
    """基于 Qt Quick 的加载窗口：旋转动画由渲染线程驱动，不受界面线程阻塞影响。"""

    def __init__(self, message="正在进入系统..."):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtQuick import QQuickView

        pal = get_theme_palette(theme_manager().mode)
        view = QQuickView()
        view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        view.setTitle(APP_TITLE)
        view.setFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        view.setColor(QColor(0, 0, 0, 0))
        view.setInitialProperties({
            "panelColor": QColor(pal.panel_bg),
            "borderColor": QColor(pal.border),
            "accentColor": QColor(pal.accent),
            "textColor": QColor(pal.text_muted),
            "message": message,
        })
        self._qml_file = tempfile.NamedTemporaryFile(
            "w", suffix=".qml", delete=False, encoding="utf-8")
        self._qml_file.write(_QML)
        self._qml_file.close()
        view.setSource(QUrl.fromLocalFile(self._qml_file.name))
        if view.status() != QQuickView.Status.Ready or view.rootObject() is None:
            raise RuntimeError("QML 加载失败: %s" % [e.toString() for e in view.errors()])
        view.setWidth(WidgetLoadingWindow.CARD_SIZE[0])
        view.setHeight(WidgetLoadingWindow.CARD_SIZE[1])
        self._view = view

    def set_message(self, text):
        self._view.rootObject().setProperty("message", text)

    def show(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            c = screen.availableGeometry().center()
            self._view.setPosition(c.x() - self._view.width() // 2, c.y() - self._view.height() // 2)
        self._view.show()

    def pump(self):
        QApplication.processEvents()

    def close(self):
        self._view.close()
        self._view.deleteLater()
        try:
            os.remove(self._qml_file.name)
        except OSError:
            pass


def LoadingWindow(message="正在进入系统..."):
    try:
        return QuickLoadingWindow(message)
    except Exception as e:
        print(f"Qt Quick 加载窗口不可用，回退到 Widget 版本: {e}")
        return WidgetLoadingWindow(message)

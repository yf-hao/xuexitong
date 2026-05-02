"""签到二维码弹窗，1秒轮询刷新。"""

import io
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage


class QRCodeDialog(QDialog):
    """显示签到二维码的弹窗，每秒轮询 enc 变化自动刷新。"""

    def __init__(self, crawler, active_id: str, title: str = "", end_time_ms: int = 0, parent=None):
        super().__init__(parent)
        self.crawler = crawler
        self.active_id = active_id
        self._current_enc = ""
        self._workers = []
        self._request_counter = 0
        self._last_processed_request = 0
        self._poll_in_progress = False
        self._end_time_ms = end_time_ms  # 结束时间（毫秒时间戳），0表示不判断

        self.setWindowTitle(f"签到二维码 - {title}" if title else "签到二维码")
        self.setFixedSize(660, 760)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        # 标题
        title_lbl = QLabel(f"📍 {title}" if title else "📍 签到二维码")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        # 二维码显示区域
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(600, 600)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("""
            background-color: #ffffff;
            border-radius: 10px;
        """)
        self.qr_label.setText("加载中...")
        self.qr_label.setStyleSheet("""
            background-color: #2d2d2d;
            border-radius: 10px;
            color: #888888;
            font-size: 14px;
        """)
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 状态栏
        status_layout = QHBoxLayout()
        self.status_lbl = QLabel("正在获取二维码...")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #888888;")
        status_layout.addWidget(self.status_lbl)

        self.refresh_lbl = QLabel("")
        self.refresh_lbl.setStyleSheet("font-size: 11px; color: #555555;")
        status_layout.addStretch()
        status_layout.addWidget(self.refresh_lbl)
        layout.addLayout(status_layout)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #444444;
                color: #ffffff;
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #555555; }
        """)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 轮询定时器 - 1秒刷新
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_qrcode)

        # 首次获取
        self._poll_qrcode()
        self._poll_timer.start()

    def _poll_qrcode(self):
        """轮询获取二维码 enc，enc 变化时重新生成。"""
        # 检查是否已到结束时间
        if self._end_time_ms > 0:
            import time
            now_ms = int(time.time() * 1000)
            if now_ms >= self._end_time_ms:
                self._poll_timer.stop()
                self.qr_label.setPixmap(QPixmap())
                self.qr_label.setText("签到已结束")
                self.qr_label.setStyleSheet("""
                    background-color: #2d2d2d;
                    border-radius: 10px;
                    color: #ff6b6b;
                    font-size: 20px;
                    font-weight: bold;
                """)
                self.status_lbl.setText("⏰ 签到已结束，不再刷新")
                return

        if self._poll_in_progress:
            return
        self._poll_in_progress = True
        from ui.workers import RefreshQRCodeWorker

        self._request_counter += 1
        request_id = self._request_counter

        worker = RefreshQRCodeWorker(self.crawler, self.active_id)
        self._workers.append(worker)
        worker.qrcode_ready.connect(lambda success, message, enc, rid=request_id: self._on_qrcode_ready(success, message, enc, rid))
        worker.finished.connect(self._cleanup_finished_worker)
        worker.start()

    def _cleanup_finished_worker(self):
        sender = self.sender()
        if sender in self._workers:
            self._workers.remove(sender)
        self._poll_in_progress = False

    def _on_qrcode_ready(self, success, message, enc, request_id):
        # 忽略过期的请求结果，只处理最新的
        if request_id < self._last_processed_request:
            return
        self._last_processed_request = request_id

        if not success:
            self.status_lbl.setText(f"❌ {message}")
            return

        # 去除空白，严格比较 enc 是否真正变化
        enc_clean = str(enc).strip() if enc else ""
        current_clean = str(self._current_enc).strip() if self._current_enc else ""

        if not enc_clean:
            self.status_lbl.setText("❌ 获取到的 enc 为空")
            return

        if enc_clean == current_clean:
            # enc 未变化，不重新生成
            self.status_lbl.setText("二维码有效")
            return

        # enc 真正变化，重新生成二维码
        self._current_enc = enc_clean
        self._generate_qr_image(enc_clean)

    def _generate_qr_image(self, enc: str):
        """用 qrcode 库生成二维码并显示。"""
        try:
            import qrcode
            from datetime import datetime

            # 生成二维码内容：签到 URL
            qr_url = f"https://mobilelearn.chaoxing.com/widget/sign/pcTeaSignController/signIn?enc={enc}"

            qr = qrcode.QRCode(
                version=5,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=12,
                border=2,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # PIL Image -> QPixmap
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            qimage = QImage()
            qimage.loadFromData(buf.read(), "PNG")
            pixmap = QPixmap.fromImage(qimage)

            # 缩放到标签大小
            scaled = pixmap.scaled(
                580, 580,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.qr_label.setPixmap(scaled)
            self.qr_label.setStyleSheet("""
                background-color: #ffffff;
                border-radius: 10px;
            """)

            now = datetime.now().strftime("%H:%M:%S")
            self.status_lbl.setText("✅ 二维码已刷新")
            self.refresh_lbl.setText(f"更新于 {now}")

        except ImportError:
            self.status_lbl.setText("❌ qrcode 库未安装")
        except Exception as e:
            self.status_lbl.setText(f"❌ 生成失败: {e}")

    def reject(self):
        """关闭时停止定时器。"""
        self._poll_timer.stop()
        super().reject()

    def closeEvent(self, event):
        self._poll_timer.stop()
        super().closeEvent(event)

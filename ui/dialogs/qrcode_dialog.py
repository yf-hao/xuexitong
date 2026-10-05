"""签到二维码弹窗，1秒轮询刷新。"""

import io
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QStackedLayout, QLabel,
    QPushButton, QSizePolicy, QWidget,
)
from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage
from ui.theme import apply_theme_stylesheet, refresh_theme_styles


def _qr_dialog_style(palette) -> str:
    return f"""
        QDialog {{ background-color: {palette.panel_bg}; }}
        QLabel {{ color: {palette.text}; }}
    """


def _qr_display_style(palette, state: str = "loading") -> str:
    if state == "ready":
        return "background-color: #ffffff; border-radius: 10px;"
    if state == "ended":
        return (
            f"background-color: {palette.disabled_bg}; border-radius: 10px; "
            f"color: {palette.danger}; font-size: 20px; font-weight: bold;"
        )
    return (
        f"background-color: {palette.disabled_bg}; border-radius: 10px; "
        f"color: {palette.text_muted}; font-size: 14px;"
    )


def _qr_close_button_style(palette) -> str:
    return f"""
        QPushButton {{
            background-color: {palette.border_strong};
            color: {palette.text};
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
        }}
        QPushButton:hover {{ background-color: {palette.text_muted}; }}
    """


def _qr_details_link_style(palette) -> str:
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {palette.accent};
            border: none;
            padding: 2px 4px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            color: {palette.accent_hover};
            text-decoration: underline;
        }}
    """


class _CompanionMoveFilter(QObject):
    def __init__(self, qr_dialog):
        super().__init__(qr_dialog)
        self.qr_dialog = qr_dialog

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.Move
            and not self.qr_dialog._syncing_companion
        ):
            self.qr_dialog._sync_companion_position()
        return False


class QRCodeDialog(QDialog):
    """显示签到二维码的弹窗，每秒轮询 enc 变化自动刷新。"""

    def __init__(
        self,
        crawler,
        active_id: str,
        title: str = "",
        end_time_ms: int = 0,
        parent=None,
        details_callback=None,
    ):
        super().__init__(parent)
        self.crawler = crawler
        self.active_id = active_id
        self._current_enc = ""
        self._current_sign_code = ""
        self._workers = []
        self._request_counter = 0
        self._last_processed_request = 0
        self._poll_in_progress = False
        self._end_time_ms = end_time_ms  # 结束时间（毫秒时间戳），0表示不判断
        self._details_dialog = None
        self._details_move_filter = None
        self._syncing_companion = False
        self.details_btn = None

        self.setWindowTitle(f"签到二维码 - {title}" if title else "签到二维码")
        self.setFixedSize(572, 672)
        apply_theme_stylesheet(self, _qr_dialog_style)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        # 标题
        title_lbl = QLabel(f"📍 {title}" if title else "📍 签到二维码")
        apply_theme_stylesheet(title_lbl, "font-size: 18px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        # 二维码显示区域
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(512, 512)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setProperty("_qr_state", "loading")
        self.qr_label.setText("加载中...")
        apply_theme_stylesheet(
            self.qr_label,
            lambda palette, label=self.qr_label: _qr_display_style(
                palette, str(label.property("_qr_state") or "loading")
            ),
        )
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 状态栏
        status_bar = QWidget(self)
        status_stack = QStackedLayout(status_bar)
        status_stack.setContentsMargins(0, 0, 0, 0)
        status_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        status_content = QWidget(status_bar)
        status_layout = QHBoxLayout(status_content)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_lbl = QLabel("正在获取二维码...")
        apply_theme_stylesheet(self.status_lbl, "font-size: 12px; color: #888888;")
        status_layout.addWidget(self.status_lbl)

        self.refresh_lbl = QLabel("")
        apply_theme_stylesheet(self.refresh_lbl, "font-size: 11px; color: #555555;")
        status_layout.addStretch()
        status_layout.addWidget(self.refresh_lbl)
        status_stack.addWidget(status_content)

        if details_callback:
            details_btn = QPushButton("签到详情")
            details_btn.setFlat(True)
            details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            details_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            apply_theme_stylesheet(details_btn, _qr_details_link_style)
            details_btn.clicked.connect(
                lambda _checked=False: details_callback(self)
            )
            self.details_btn = details_btn
            button_overlay = QWidget(status_bar)
            button_layout = QHBoxLayout(button_overlay)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addWidget(
                details_btn, alignment=Qt.AlignmentFlag.AlignCenter
            )
            status_stack.addWidget(button_overlay)
            status_stack.setCurrentWidget(button_overlay)
        layout.addWidget(status_bar)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setFixedWidth(100)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_theme_stylesheet(close_btn, _qr_close_button_style)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 轮询定时器 - 1秒刷新
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_qrcode)
        self.finished.connect(self._on_dialog_finished)

        # 首次获取
        self._poll_qrcode()
        self._poll_timer.start()

    def set_details_loading(self, loading: bool):
        if self.details_btn is not None:
            self.details_btn.setEnabled(not loading)

    def attach_details_dialog(self, dialog):
        if self._details_dialog is dialog:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()

        self._details_dialog = dialog
        self._details_move_filter = _CompanionMoveFilter(self)
        dialog.installEventFilter(self._details_move_filter)
        dialog.finished.connect(
            lambda _result, attached=dialog: self.detach_details_dialog(attached)
        )
        self._position_companion_pair()
        dialog.show()

    def detach_details_dialog(self, dialog):
        if self._details_dialog is not dialog:
            return
        if self._details_move_filter is not None:
            dialog.removeEventFilter(self._details_move_filter)
            self._details_move_filter.deleteLater()
        self._details_dialog = None
        self._details_move_filter = None
        self.set_details_loading(False)

    def _position_companion_pair(self):
        dialog = self._details_dialog
        if dialog is None:
            return

        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None

        self._syncing_companion = True
        try:
            if available is not None:
                qr_width = self.frameGeometry().width()
                details_width = dialog.frameGeometry().width() or dialog.width()
                max_details_width = available.width() - qr_width
                if 0 < max_details_width < details_width:
                    dialog.resize(max_details_width, dialog.height())

                group_width = qr_width + (dialog.frameGeometry().width() or dialog.width())
                group_height = max(
                    self.frameGeometry().height(),
                    dialog.frameGeometry().height() or dialog.height(),
                )
                x = available.left() + max(0, (available.width() - group_width) // 2)
                y = available.top() + max(0, (available.height() - group_height) // 2)
                self.move(x, y)

            self._move_companion_to_anchor()
        finally:
            self._syncing_companion = False

    def _move_companion_to_anchor(self):
        if self._details_dialog is None:
            return
        frame = self.frameGeometry()
        target = QPoint(frame.right() + 1, frame.top())
        if self._details_dialog.frameGeometry().topLeft() != target:
            self._details_dialog.move(target)

    def _sync_companion_position(self):
        if self._syncing_companion or self._details_dialog is None:
            return
        self._syncing_companion = True
        try:
            self._move_companion_to_anchor()
        finally:
            self._syncing_companion = False

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_companion_position()

    def _on_dialog_finished(self, _result):
        self._poll_timer.stop()
        dialog = self._details_dialog
        if dialog is not None:
            self.detach_details_dialog(dialog)
            dialog.close()

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
                self.qr_label.setProperty("_qr_state", "ended")
                refresh_theme_styles(self.qr_label)
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
        worker.qrcode_ready.connect(
            lambda success, message, enc, sign_code, rid=request_id: self._on_qrcode_ready(success, message, enc, sign_code, rid)
        )
        worker.finished.connect(self._cleanup_finished_worker)
        worker.start()

    def _cleanup_finished_worker(self):
        sender = self.sender()
        if sender in self._workers:
            self._workers.remove(sender)
        self._poll_in_progress = False

    def _on_qrcode_ready(self, success, message, enc, sign_code, request_id):
        # 忽略过期的请求结果，只处理最新的
        if request_id < self._last_processed_request:
            return
        self._last_processed_request = request_id

        if not success:
            self.status_lbl.setText(f"❌ {message}")
            return

        # 去除空白，严格比较 enc 是否真正变化
        enc_clean = str(enc).strip() if enc else ""
        sign_code_clean = str(sign_code).strip() if sign_code else ""
        current_clean = str(self._current_enc).strip() if self._current_enc else ""
        current_sign_code = str(self._current_sign_code).strip() if self._current_sign_code else ""

        if not enc_clean:
            self.status_lbl.setText("❌ 获取到的 enc 为空")
            return

        if not sign_code_clean:
            sign_code_clean = str(self.active_id).strip()

        if enc_clean == current_clean and sign_code_clean == current_sign_code:
            self.status_lbl.setText("二维码有效")
            return

        self._current_enc = enc_clean
        self._current_sign_code = sign_code_clean
        self._generate_qr_image(enc_clean, sign_code_clean)

    @staticmethod
    def _build_qr_url(active_id: str, enc: str, sign_code: str) -> str:
        active_id = str(active_id or "").strip()
        enc = str(enc or "").strip()
        sign_code = str(sign_code or "").strip() or active_id
        return (
            "https://mobilelearn.chaoxing.com/widget/sign/e"
            f"?id={active_id}&c={sign_code}&enc={enc}"
            "&DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=id"
        )

    def _generate_qr_image(self, enc: str, sign_code: str):
        """用 qrcode 库生成二维码并显示。"""
        try:
            import qrcode
            from datetime import datetime

            qr_url = self._build_qr_url(self.active_id, enc, sign_code)

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
                492, 492,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.qr_label.setPixmap(scaled)
            self.qr_label.setProperty("_qr_state", "ready")
            refresh_theme_styles(self.qr_label)

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

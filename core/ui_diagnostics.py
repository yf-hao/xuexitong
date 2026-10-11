import logging
import re
import sys
import threading
import time
import traceback

from pathlib import Path

from PyQt6.QtCore import QTimer, QtMsgType, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QDialog

from core.logger import get_logger


_logger = get_logger()
_installed = False
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"(?i)\b(cookie|authorization|token|password)\b\s*[:=]\s*\S+"
)


def _safe_qt_message(message):
    message = _URL_PATTERN.sub("[URL]", str(message))
    message = _SECRET_PATTERN.sub(r"\1=[redacted]", message)
    return message[:600]


def log_dialog_state(event, dialog=None):
    app = QApplication.instance()
    active_window = app.activeWindow() if app is not None else None
    active_modal = app.activeModalWidget() if app is not None else None

    if dialog is None:
        dialog_state = "none"
    else:
        is_dialog = isinstance(dialog, QDialog)
        dialog_state = (
            f"class={type(dialog).__name__} "
            f"visible={dialog.isVisible()} enabled={dialog.isEnabled()} "
            f"modal={dialog.isModal() if is_dialog else False}"
        )

    _logger.info(
        "UI_DIAG %s dialog[%s] active_window=%s active_modal=%s",
        event,
        dialog_state,
        type(active_window).__name__ if active_window is not None else "none",
        type(active_modal).__name__ if active_modal is not None else "none",
    )


def log_exception_frames(event, exception):
    frames = traceback.extract_tb(exception.__traceback__)
    frame_summary = " <- ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in frames[-12:]
    )
    _logger.error(
        "UI_DIAG %s exception_type=%s frames=%s",
        event,
        type(exception).__name__,
        frame_summary or "unavailable",
    )


def install_ui_diagnostics(app, stall_after_seconds=4.0):
    global _installed
    if _installed:
        return
    _installed = True

    previous_sys_hook = sys.excepthook

    def exception_hook(exception_type, exception, tb):
        stack = "".join(traceback.format_tb(tb))
        _logger.critical(
            "UI_DIAG unhandled_python_exception type=%s\n%s",
            exception_type.__name__,
            stack[-8000:],
        )
        previous_sys_hook(exception_type, exception, tb)

    sys.excepthook = exception_hook

    previous_thread_hook = threading.excepthook

    def thread_exception_hook(args):
        stack = "".join(traceback.format_tb(args.exc_traceback))
        _logger.critical(
            "UI_DIAG unhandled_thread_exception thread=%s type=%s\n%s",
            args.thread.name if args.thread is not None else "unknown",
            args.exc_type.__name__,
            stack[-8000:],
        )
        previous_thread_hook(args)

    threading.excepthook = thread_exception_hook

    def qt_message_handler(message_type, context, message):
        if message_type == QtMsgType.QtDebugMsg:
            return
        level = (
            logging.CRITICAL
            if message_type in {
                QtMsgType.QtCriticalMsg,
                QtMsgType.QtFatalMsg,
            }
            else logging.WARNING
        )
        _logger.log(
            level,
            "UI_DIAG qt_message type=%s category=%s message=%s",
            message_type.name,
            getattr(context, "category", ""),
            _safe_qt_message(message),
        )

    qInstallMessageHandler(qt_message_handler)

    main_thread_id = threading.get_ident()
    last_heartbeat = [time.monotonic()]
    stop_watchdog = threading.Event()
    heartbeat_timer = QTimer(app)
    heartbeat_timer.setInterval(500)
    heartbeat_timer.timeout.connect(
        lambda: last_heartbeat.__setitem__(0, time.monotonic())
    )
    heartbeat_timer.start()

    def watch_event_loop():
        last_report = 0.0
        while not stop_watchdog.wait(1.0):
            now = time.monotonic()
            stalled_for = now - last_heartbeat[0]
            if (
                stalled_for < stall_after_seconds
                or now - last_report < 10.0
            ):
                continue

            frame = sys._current_frames().get(main_thread_id)
            stack = "".join(traceback.format_stack(frame)) if frame else "unavailable"
            _logger.error(
                "UI_DIAG event_loop_stalled seconds=%.1f thread=main\n%s",
                stalled_for,
                stack[-10000:],
            )
            last_report = now

    watchdog = threading.Thread(
        target=watch_event_loop,
        name="ui-event-loop-watchdog",
        daemon=True,
    )
    watchdog.start()
    app.aboutToQuit.connect(stop_watchdog.set)
    _logger.info(
        "UI_DIAG installed stall_threshold_seconds=%.1f",
        stall_after_seconds,
    )
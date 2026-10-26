"""Shared UI orchestration for preparing group member caches."""
from collections.abc import Callable

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog, QWidget

from ui.workers import GroupMembersCachePrepareWorker


class GroupMembersCachePreparation(QObject):
    """Run cache preparation in the background and report its result."""

    progress = pyqtSignal(str)

    def __init__(self, crawler, parent_widget: QWidget):
        super().__init__(parent_widget)
        self._crawler = crawler
        self._parent_widget = parent_widget
        self._worker = None
        self._progress_dialog = None
        self._on_finished: Callable[[object], None] | None = None

    @property
    def is_running(self) -> bool:
        return self._worker is not None

    def start(
        self,
        course_name: str,
        class_name: str,
        course_id: str,
        class_id: str,
        on_finished: Callable[[object], None],
    ) -> bool:
        if self._worker is not None:
            return False

        worker = GroupMembersCachePrepareWorker(
            self._crawler,
            course_name,
            class_name,
            course_id,
            class_id,
        )
        dialog = QProgressDialog("正在准备群成员缓存...", "", 0, 0, self._parent_widget)
        dialog.setWindowTitle("准备群成员缓存")
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumWidth(360)

        self._worker = worker
        self._progress_dialog = dialog
        self._on_finished = on_finished
        worker.progress.connect(dialog.setLabelText)
        worker.progress.connect(self.progress.emit)
        worker.finished_signal.connect(self._on_preparation_finished)
        worker.finished.connect(self._on_worker_finished)
        dialog.show()
        worker.start()
        return True

    def _on_preparation_finished(self, result):
        dialog = self._progress_dialog
        self._progress_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()

        callback = self._on_finished
        self._on_finished = None
        if callback is not None:
            callback(result)

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

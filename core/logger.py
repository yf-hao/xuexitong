"""统一日志配置，输出到 ~/Library/Application Support/XuexitongManager/xuexitong.log"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.expanduser("~/Library/Application Support/XuexitongManager")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "xuexitong.log")
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
IS_RELEASE_BUILD = bool(getattr(sys, "frozen", False))
FILE_LOG_LEVEL = logging.ERROR if IS_RELEASE_BUILD else logging.DEBUG
_ORIGINAL_STDERR = sys.stderr
_ORIGINAL_STDOUT = sys.stdout
_STREAMS_REDIRECTED = False

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = RotatingFileHandler(
    LOG_FILE,
    encoding="utf-8",
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
)
_file_handler.setFormatter(_formatter)
_file_handler.setLevel(FILE_LOG_LEVEL)

# 可选：同时输出到 stderr（保留少量终端信息）
_console_handler = logging.StreamHandler(_ORIGINAL_STDERR)
_console_handler.setFormatter(_formatter)
_console_handler.setLevel(logging.WARNING)

logger = logging.getLogger("xuexitong")
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)
logger.propagate = False


class _LoggerStream:
    def __init__(self, target_logger: logging.Logger, level: int):
        self._logger = target_logger
        self._level = level
        self._buffer = ""

    def write(self, message: str):
        if not isinstance(message, str):
            message = str(message or "")
        if not message:
            return 0

        self._buffer += message
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self._logger.log(self._level, line)
        return len(message)

    def flush(self):
        line = self._buffer.rstrip()
        self._buffer = ""
        if line:
            self._logger.log(self._level, line)

    def isatty(self):
        return False


def redirect_standard_streams():
    global _STREAMS_REDIRECTED
    if _STREAMS_REDIRECTED:
        return

    sys.stdout = _LoggerStream(logger, logging.INFO)
    sys.stderr = _LoggerStream(logger, logging.ERROR)
    _STREAMS_REDIRECTED = True

def get_logger(name: str = "xuexitong") -> logging.Logger:
    return logging.getLogger(name)

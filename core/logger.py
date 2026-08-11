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
_file_handler.setLevel(logging.ERROR)

logger = logging.getLogger("xuexitong")
logger.setLevel(logging.ERROR)
logger.addHandler(_file_handler)
logger.propagate = False


def get_logger(name: str = "xuexitong") -> logging.Logger:
    return logging.getLogger(name)

"""统一日志配置，输出到 ~/Library/Application Support/XuexitongManager/xuexitong.log"""
import logging
import os
import sys
from datetime import datetime

LOG_DIR = os.path.expanduser("~/Library/Application Support/XuexitongManager")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "xuexitong.log")

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
_file_handler.setFormatter(_formatter)

# 可选：同时输出到 stderr（保留少量终端信息）
_console_handler = logging.StreamHandler(sys.stderr)
_console_handler.setFormatter(_formatter)
_console_handler.setLevel(logging.WARNING)

logger = logging.getLogger("xuexitong")
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)
logger.propagate = False

def get_logger(name: str = "xuexitong") -> logging.Logger:
    return logging.getLogger(name)

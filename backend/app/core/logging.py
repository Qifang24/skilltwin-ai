"""结构化日志（零第三方依赖，stdlib logging + JSON formatter）。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """把日志渲染成单行 JSON，便于后续采集与排查。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # logger.info("...", extra={"job_id": ...}) 里的自定义字段一并带出
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class HumanFormatter(logging.Formatter):
    """开发期可读格式。"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
            datefmt="%H:%M:%S",
        )


def force_utf8_stdio() -> None:
    """把 stdout/stderr 强制切到 UTF-8。

    Windows 控制台默认 cp936/cp1252，本项目日志与数据大量为中文，
    不做这一步会在打印中文时抛 UnicodeEncodeError。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # 流已被重定向或不支持，忽略即可
                pass


def setup_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    force_utf8_stdio()
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else HumanFormatter())
    root.addHandler(handler)

    # 第三方库降噪
    for noisy in (
        "httpx",
        "httpcore",
        "urllib3",
        "chromadb",
        "sentence_transformers",
        "jieba",  # 每次分词都会打印词典加载过程
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

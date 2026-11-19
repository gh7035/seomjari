"""구조화 로그. LOG_JSON=true면 JSON 한 줄, 아니면 사람 읽는 형식."""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

from .config import settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def request_id() -> str | None:
    return _request_id.get()


def set_request_id(rid: str | None) -> None:
    _request_id.set(rid)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = _request_id.get()
        if rid:
            payload["rid"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


class _HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = _request_id.get()
        prefix = f"[{rid}] " if rid else ""
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:5s} {record.name}: {prefix}{record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    s = settings()
    root = logging.getLogger()
    root.handlers = []
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if s.log_json else _HumanFormatter())
    root.addHandler(handler)
    root.setLevel(s.log_level)
    # uvicorn 로거 조정
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, msg: str, **extra: Any) -> None:
    """키-값 extra를 구조화 로그에 실어 보낸다."""
    logger.log(level, msg, extra={"extra": extra})

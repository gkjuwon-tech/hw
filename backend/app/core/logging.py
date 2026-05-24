"""Structured JSON logging.

In production all logs are emitted as line-delimited JSON so they can be
ingested by Datadog / CloudWatch / Loki without a regex grok step. Locally
we keep the standard human-readable formatter.

Every log line picked up inside a request gets a ``request_id`` field
injected by ``RequestContextMiddleware``.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

from pythonjsonlogger import jsonlogger

from app.core.config import settings

# ContextVar set by RequestContextMiddleware so every log inside a request
# automatically carries the request id, the resolved org, and the path.
request_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "request_context", default=None
)


def _context() -> dict[str, Any]:
    value = request_context.get()
    return value if value is not None else {}


class ContextFilter(logging.Filter):
    """Inject ContextVar fields into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in _context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class _JsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("service", settings.service_name)
        log_record.setdefault("env", settings.environment)
        log_record.setdefault("level", record.levelname)
        log_record.setdefault("logger", record.name)
        # Promote context vars into the top-level payload.
        for key, value in _context().items():
            log_record.setdefault(key, value)


def configure_logging() -> None:
    """Idempotently configure the root logger."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        fmt = _JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level"},
        )
    else:
        fmt = logging.Formatter(  # type: ignore[assignment]
            "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
        )
    handler.setFormatter(fmt)
    handler.addFilter(ContextFilter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Quiet libraries that are otherwise noisy.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(logging.INFO, root.level))


def bind_request_context(**kwargs: Any) -> None:
    """Merge ``kwargs`` into the per-request context (called by middleware)."""
    base = dict(_context())
    base.update({k: v for k, v in kwargs.items() if v is not None})
    request_context.set(base)


def clear_request_context() -> None:
    request_context.set(None)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

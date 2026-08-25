"""Structured logging with a content-redaction filter (task T073).

NFR-SEC-04 and FR-042: logs carry identifiers, never document content, client-bearing
prompt text, or credentials. Log aggregation ships wherever it ships, and a client's
financial position in a log line is a data incident regardless of how the log was
later handled.

The filter drops offending fields rather than raising. That is the opposite of the
audit payload guard, which raises — and the difference is deliberate. An audit record
that silently lost a field would be a false record. A log line that silently lost a
field is a slightly less useful log line, and taking down a request over a logging
concern would be the wrong trade.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings

_FORBIDDEN_KEY_RE = re.compile(
    r"content|prompt|notes?$|excerpt|body|secret|password|token|api[_-]?key|credential|authorization",
    re.IGNORECASE,
)

_MAX_VALUE_LENGTH = 200

# Standard LogRecord attributes, excluded when collecting structured extras.
_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


class ContentRedactionFilter(logging.Filter):
    """Strip content-bearing and credential-bearing fields from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if key in _RESERVED:
                continue

            value = record.__dict__[key]

            if _FORBIDDEN_KEY_RE.search(key):
                record.__dict__[key] = "[redacted]"
                continue

            if isinstance(value, str) and len(value) > _MAX_VALUE_LENGTH:
                record.__dict__[key] = f"[redacted: {len(value)} chars]"

        return True


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            # The type and message only. A traceback can carry local variables, and
            # local variables in this codebase can carry document content.
            exc_type, exc_value, _ = record.exc_info
            payload["error_type"] = exc_type.__name__ if exc_type else None
            payload["error_message"] = str(exc_value)[:200] if exc_value else None

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Install the JSON formatter and redaction filter on the root logger."""
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContentRedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # SQLAlchemy echoes bound parameters at INFO, and bound parameters are client data.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

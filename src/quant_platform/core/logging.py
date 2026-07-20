"""Structured JSON logging with secret redaction.

Log records are emitted as single-line JSON with UTC timestamps and an
optional correlation ID, so they can be shipped to any log pipeline without
parsing heuristics. A redaction filter masks values whose keys look like
credentials; logs must never contain secrets (specification section 16).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(token|secret|password|passwd|api_key|apikey|credential|authorization|private_key)",
    re.IGNORECASE,
)
REDACTED = "***REDACTED***"


def redact(payload: Any) -> Any:
    """Recursively mask values of any mapping key that looks like a secret."""
    if isinstance(payload, dict):
        return {
            key: (REDACTED if SECRET_KEY_PATTERN.search(str(key)) else redact(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(item) for item in payload]
    return payload


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line, redacting secret-like keys."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id is not None:
            entry["correlation_id"] = correlation_id
        extra_fields = getattr(record, "fields", None)
        if isinstance(extra_fields, dict):
            entry.update(redact(extra_fields))
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

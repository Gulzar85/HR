"""Structured (JSON-lines) logging formatter. Use ``logging.getLogger("ems.app")`` etc., never print()."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(kind: str = "app") -> logging.Logger:
    """kind: app | security | audit | celery | api"""
    return logging.getLogger(f"ems.{kind}")

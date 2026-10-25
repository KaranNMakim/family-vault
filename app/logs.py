"""Structured JSON logging with redaction of sensitive fields.

Anything logged under a sensitive key is replaced with "[REDACTED]", and long digit runs
in any string are scrubbed, so an accidental `log.info(..., extra={"payload": body})`
cannot leak identifiers.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "passphrase",
    "password",
    "pin",
    "otp",
    "masked_id",
    "notes",
    "dob",
    "phone",
    "email",
    "address",
    "location",
    "key",
    "token",
    "authorization",
    "ciphertext",
}

_DIGITS = re.compile(r"\d{5,}")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _DIGITS.sub("[#]", value)
    return value


_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _STD_ATTRS:
                payload[k] = v
        return json.dumps(redact(payload), default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("vault")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"vault.{name}")

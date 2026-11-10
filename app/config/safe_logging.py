"""Security-focused, structured logging: never serialize arbitrary log messages.

This formatter deliberately ignores record.msg, args, exc_info, request
objects, headers and URLs even when supplied by Django or third-party loggers.
Only a strictly validated, fixed-size allowlist reaches stdout/stderr.
"""
import json
import logging
import re
from datetime import datetime, timezone

_ALLOWED_EVENTS = {"http_error", "framework_error"}
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_REQUEST_ID = re.compile(r"^[0-9a-f]{16}$")


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        event = getattr(record, "event", "framework_error")
        if event not in _ALLOWED_EVENTS:
            event = "framework_error"

        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z"),
            "level": (
                record.levelname
                if record.levelname in {"WARNING", "ERROR", "CRITICAL"}
                else "WARNING"
            ),
            "event": event,
        }

        status = getattr(record, "status_code", None)
        if type(status) is int and 400 <= status <= 599:
            data["status_code"] = status

        method = getattr(record, "http_method", None)
        if method in _ALLOWED_METHODS:
            data["method"] = method

        request_id = getattr(record, "request_id", None)
        if isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id):
            data["request_id"] = request_id

        return json.dumps(data, separators=(",", ":"), ensure_ascii=True)

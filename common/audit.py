"""Safe log rendering: preserve message text while redacting credentials and sessions."""

from __future__ import annotations

import json
from typing import Any


SENSITIVE_FIELDS = {"password", "password_hash", "token", "session", "session_token", "avatar", "avatar_data"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "<redacted>" if key.lower() in SENSITIVE_FIELDS else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def render_for_log(raw_message: str) -> str:
    """Render JSON requests/responses safely; non-JSON messages are returned unchanged."""
    try:
        return json.dumps(_redact(json.loads(raw_message)), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw_message

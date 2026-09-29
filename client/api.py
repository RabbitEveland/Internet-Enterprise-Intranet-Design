"""JSON API client for the TLS messaging service."""

from __future__ import annotations

import json
from typing import Any

from common.client_connection import send_request
from common.config import Settings


class ApiError(RuntimeError):
    """A server response that could not complete the requested operation."""


class MessengerApi:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def call(self, action: str, **payload: Any) -> dict[str, Any]:
        request = json.dumps({"action": action, **payload}, ensure_ascii=False, separators=(",", ":"))
        try:
            response = json.loads(send_request(self.settings, request))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ApiError(f"无法连接服务端：{exc}") from exc
        if not isinstance(response, dict) or not response.get("ok"):
            error = response.get("error") if isinstance(response, dict) else None
            raise ApiError(error if isinstance(error, str) else "服务端返回了无效响应。")
        data = response.get("data", {})
        if not isinstance(data, dict):
            raise ApiError("服务端返回了无效数据。")
        return data

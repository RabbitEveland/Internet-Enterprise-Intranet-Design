"""Authorization and request routing for the TLS/MySQL messaging service."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
from typing import Any, Callable

from server.database import DuplicateUsernameError, MySQLRepository, RecordNotFoundError, RepositoryError
from server.security import CredentialValidationError, hash_password, validate_password, validate_username, verify_password


class ApplicationError(ValueError):
    """An expected request error that is safe to return to the client."""


class SecureMessengerApplication:
    MAX_AVATAR_BYTES = 512 * 1024
    AVATAR_SIGNATURES = {
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
        "image/gif": b"GIF8",
    }
    # These are business events, rather than transport/debug events.  Keeping the
    # list explicit prevents page refreshes from filling the audit trail.
    AUDITED_ACTIONS = frozenset({
        "register",
        "login",
        "logout",
        "send_message",
        "admin_create_user",
        "admin_update_user",
        "admin_delete_user",
        "admin_reset_password",
        "admin_moderate_message",
        "update_profile",
    })

    def __init__(self, repository: MySQLRepository) -> None:
        self.repository = repository
        self.actions: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "register": self._register,
            "login": self._login,
            "logout": self._logout,
            "get_profile": self._get_profile,
            "get_user_profile": self._get_user_profile,
            "update_profile": self._update_profile,
            "conversation": self._conversation,
            "send_message": self._send_message,
            "user_list_contacts": self._user_list_contacts,
            "admin_list_users": self._admin_list_users,
            "admin_create_user": self._admin_create_user,
            "admin_update_user": self._admin_update_user,
            "admin_delete_user": self._admin_delete_user,
            "admin_reset_password": self._admin_reset_password,
            "admin_review_messages": self._admin_review_messages,
            "admin_moderate_message": self._admin_moderate_message,
            "admin_list_operation_logs": self._admin_list_operation_logs,
        }

    def handle(self, raw_request: str) -> str:
        request: dict[str, Any] | None = None
        action: str | None = None
        actor_id: int | None = None
        actor_username: str | None = None
        try:
            request = json.loads(raw_request)
            if not isinstance(request, dict):
                raise ApplicationError("请求格式必须是 JSON 对象。")
            action = request.get("action")
            if not isinstance(action, str) or action not in self.actions:
                raise ApplicationError("不支持的操作。")
            actor = self._audit_actor(request)
            actor_id = int(actor["id"]) if actor is not None else None
            actor_username = str(actor["username"]) if actor is not None else None
            data = self.actions[action](request)
            if action in self.AUDITED_ACTIONS:
                # A new session's owner is known only after a successful login/registration.
                result_user = self._result_user(data)
                if result_user is not None:
                    actor_id, actor_username = result_user
                self._write_audit_log(action, True, actor_id, actor_username, request, data)
            return self._response(True, data=data)
        except (json.JSONDecodeError, ApplicationError, CredentialValidationError, DuplicateUsernameError, RecordNotFoundError) as exc:
            self._write_failed_audit_log(action, actor_id, actor_username, request)
            return self._response(False, error=str(exc))
        except RepositoryError:
            self._write_failed_audit_log(action, actor_id, actor_username, request)
            return self._response(False, error="数据库操作失败，请稍后重试。")
        except Exception:
            self._write_failed_audit_log(action, actor_id, actor_username, request)
            return self._response(False, error="服务端处理请求时发生未知错误。")

    def _audit_actor(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Best effort only: audit availability must never block the requested action."""
        token = request.get("token")
        if not isinstance(token, str) or not token:
            return None
        try:
            user = self.repository.get_session_user(token)
            return user
        except Exception:
            return None

    @staticmethod
    def _result_user(data: dict[str, Any]) -> tuple[int, str] | None:
        user = data.get("user")
        if isinstance(user, dict) and type(user.get("id")) is int and isinstance(user.get("username"), str):
            return int(user["id"]), user["username"]
        return None

    @staticmethod
    def _audit_positive_id(value: Any) -> int | None:
        return int(value) if type(value) is int and value > 0 else None

    def _write_failed_audit_log(
        self, action: str | None, actor_id: int | None, actor_username: str | None, request: dict[str, Any] | None
    ) -> None:
        if action in self.AUDITED_ACTIONS and request is not None:
            self._write_audit_log(action, False, actor_id, actor_username, request, {})

    def _write_audit_log(
        self,
        action: str,
        success: bool,
        actor_id: int | None,
        actor_username: str | None,
        request: dict[str, Any],
        data: dict[str, Any],
    ) -> None:
        """Persist deliberately non-sensitive audit metadata without changing request outcome."""
        target_user_id = self._audit_positive_id(request.get("user_id"))
        message_id = self._audit_positive_id(data.get("message_id"))
        if message_id is None:
            message_id = self._audit_positive_id(request.get("message_id"))
        if action == "admin_create_user":
            target_user_id = self._audit_positive_id(data.get("user_id"))
        elif action == "register" and success:
            target_user_id = actor_id
        elif action == "update_profile":
            target_user_id = actor_id

        detail_by_action = {
            "register": "用户注册",
            "login": "登录系统",
            "logout": "退出登录",
            "send_message": "发送消息",
            "admin_create_user": "创建用户",
            "admin_update_user": "修改用户",
            "admin_delete_user": "删除用户",
            "admin_reset_password": "重置用户密码",
            "admin_moderate_message": "调整消息屏蔽状态",
            "update_profile": "更新个人资料",
        }
        detail = detail_by_action.get(action, "执行操作") if success else "操作未完成"
        try:
            self.repository.create_operation_log(
                actor_id=actor_id,
                actor_username=actor_username,
                action=action,
                success=success,
                target_user_id=target_user_id,
                message_id=message_id,
                detail=detail,
            )
        except Exception:
            # The operation itself has already completed.  A temporary audit write
            # failure must not turn a password reset or moderation action into a lie.
            pass

    @staticmethod
    def _response(ok: bool, data: dict[str, Any] | None = None, error: str | None = None) -> str:
        response: dict[str, Any] = {"ok": ok}
        if data is not None:
            response["data"] = data
        if error is not None:
            response["error"] = error
        return json.dumps(response, ensure_ascii=False, separators=(",", ":"), default=SecureMessengerApplication._json_default)

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (dt.datetime, dt.date)):
            return value.isoformat(sep=" ", timespec="seconds")
        raise TypeError(f"Unsupported JSON value: {type(value)!r}")

    @staticmethod
    def _request_text(request: dict[str, Any], field: str, maximum: int = 4000) -> str:
        value = request.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ApplicationError(f"{field} 必须是 1–{maximum} 个字符的文本。")
        return value.strip()

    @staticmethod
    def _request_id(request: dict[str, Any], field: str = "user_id") -> int:
        value = request.get(field)
        if type(value) is not int or value <= 0:
            raise ApplicationError(f"{field} 编号无效。")
        return value

    @staticmethod
    def _public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "is_active": bool(user["is_active"]),
            "created_at": user.get("created_at"),
        }

    @staticmethod
    def _profile_text(value: Any, field: str, maximum: int) -> str:
        if not isinstance(value, str) or len(value.strip()) > maximum:
            raise ApplicationError(f"{field} 必须是最多 {maximum} 个字符的文本。")
        return value.strip()

    @classmethod
    def _decode_avatar(cls, value: Any) -> tuple[str, bytes] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ApplicationError("头像数据格式无效。")
        mime = value.get("mime")
        encoded = value.get("data")
        if mime not in cls.AVATAR_SIGNATURES or not isinstance(encoded, str):
            raise ApplicationError("头像仅支持 PNG、JPEG 或 GIF 格式。")
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
            raise ApplicationError("头像文件编码无效。") from exc
        if not raw or len(raw) > cls.MAX_AVATAR_BYTES or not raw.startswith(cls.AVATAR_SIGNATURES[mime]):
            raise ApplicationError("头像文件无效或超过 512 KB。")
        return mime, raw

    @classmethod
    def _profile_user(cls, user: dict[str, Any]) -> dict[str, Any]:
        public = cls._public_user(user)
        public.update({
            "gender_identity": user.get("gender_identity", ""),
            "job_title": user.get("job_title", ""),
            "bio": user.get("bio", ""),
            "avatar": None,
        })
        raw_avatar = user.get("avatar_data")
        avatar_mime = user.get("avatar_mime")
        if isinstance(raw_avatar, (bytes, bytearray)) and isinstance(avatar_mime, str):
            public["avatar"] = {"mime": avatar_mime, "data": base64.b64encode(raw_avatar).decode("ascii")}
        return public

    def _current_user(self, request: dict[str, Any]) -> dict[str, Any]:
        token = request.get("token")
        if not isinstance(token, str) or not token:
            raise ApplicationError("请先登录。")
        user = self.repository.get_session_user(token)
        if user is None:
            raise ApplicationError("登录已失效，请重新登录。")
        return user

    def _require_admin(self, request: dict[str, Any]) -> dict[str, Any]:
        user = self._current_user(request)
        if user["role"] != "admin":
            raise ApplicationError("此操作仅管理员可用。")
        return user

    def _register(self, request: dict[str, Any]) -> dict[str, Any]:
        username = validate_username(request.get("username"))
        password = validate_password(request.get("password"))
        user_id = self.repository.create_user(username, hash_password(password), "user")
        token = self.repository.create_session(user_id)
        return {"token": token, "user": {"id": user_id, "username": username, "role": "user", "is_active": True}}

    def _login(self, request: dict[str, Any]) -> dict[str, Any]:
        username = validate_username(request.get("username"))
        password = request.get("password")
        if not isinstance(password, str):
            raise ApplicationError("用户名或密码错误。")
        user = self.repository.find_user_by_username(username)
        if user is None or not user["is_active"] or not verify_password(password, user["password_hash"]):
            raise ApplicationError("用户名或密码错误。")
        token = self.repository.create_session(int(user["id"]))
        return {"token": token, "user": self._public_user(user)}

    def _logout(self, request: dict[str, Any]) -> dict[str, Any]:
        token = request.get("token")
        if isinstance(token, str) and token:
            self.repository.delete_session(token)
        return {}

    def _get_profile(self, request: dict[str, Any]) -> dict[str, Any]:
        current_user = self._current_user(request)
        user = self.repository.find_user(int(current_user["id"]))
        if user is None:
            raise ApplicationError("用户不存在。")
        return {"user": self._profile_user(user)}

    def _get_user_profile(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return the deliberately public profile fields of another active account."""
        current_user = self._current_user(request)
        user_id = self._request_id(request)
        user = self.repository.find_user(user_id)
        if user is None or not user["is_active"]:
            raise ApplicationError("该用户不存在或已被停用。")
        if current_user["role"] != "admin" and user_id == int(current_user["id"]):
            raise ApplicationError("请在个人中心查看自己的资料。")
        return {"user": self._profile_user(user)}

    def _update_profile(self, request: dict[str, Any]) -> dict[str, Any]:
        current_user = self._current_user(request)
        gender_identity = self._profile_text(request.get("gender_identity", ""), "性别认同", 64)
        job_title = self._profile_text(request.get("job_title", ""), "职位", 80)
        bio = self._profile_text(request.get("bio", ""), "个人简介", 500)
        replace_avatar = "avatar" in request
        avatar = self._decode_avatar(request.get("avatar")) if replace_avatar else None
        self.repository.update_profile(
            int(current_user["id"]), gender_identity, job_title, bio,
            avatar_data=avatar[1] if avatar else None,
            avatar_mime=avatar[0] if avatar else None,
            replace_avatar=replace_avatar,
        )
        user = self.repository.find_user(int(current_user["id"]))
        if user is None:
            raise ApplicationError("用户不存在。")
        return {"user": self._profile_user(user)}

    def _conversation(self, request: dict[str, Any]) -> dict[str, Any]:
        current_user = self._current_user(request)
        if current_user["role"] == "admin":
            if "user_id" not in request:
                raise ApplicationError("请选择一个普通用户查看消息。")
            target_id = self._request_id(request)
            target_user = self.repository.find_user(target_id)
            if target_user is None or target_user["role"] != "user":
                raise ApplicationError("请选择一个普通用户查看消息。")
            return {"messages": self.repository.get_user_admin_conversation(target_id, int(current_user["id"]))}

        current_user_id = int(current_user["id"])
        if "user_id" not in request:
            return {"messages": self._visible_messages(self.repository.get_admin_conversation(current_user_id))}
        target_id = self._request_id(request)
        target_user = self.repository.find_user(target_id)
        if target_id == current_user_id or target_user is None or not target_user["is_active"]:
            raise ApplicationError("该用户不可联系。")
        if target_user["role"] == "admin":
            messages = self.repository.get_user_admin_conversation(current_user_id, target_id)
        else:
            messages = self.repository.get_direct_conversation(current_user_id, target_id)
        return {"messages": self._visible_messages(messages)}

    @staticmethod
    def _visible_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Replace the body before serialization: hiding a widget is not access control.
        result = []
        for message in messages:
            public = {key: message[key] for key in (
                "id", "sender_id", "recipient_id", "body", "created_at", "sender_username", "sender_role"
            ) if key in message}
            public["is_blocked"] = bool(message.get("is_blocked", False))
            if public["is_blocked"]:
                public["body"] = "[该消息因违规已被管理员屏蔽]"
            result.append(public)
        return result

    def _admin_review_messages(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_admin(request)
        user_id = self._request_id(request) if "user_id" in request else None
        after_id = request.get("after_id", 0)
        if type(after_id) is not int or after_id < 0:
            raise ApplicationError("分页编号无效。")
        rows = self.repository.review_messages(user_id, after_id)
        return {"messages": rows[:40], "has_more": len(rows) > 40}

    def _admin_moderate_message(self, request: dict[str, Any]) -> dict[str, Any]:
        admin = self._require_admin(request)
        message_id = self._request_id(request, "message_id")
        blocked = request.get("is_blocked")
        if not isinstance(blocked, bool):
            raise ApplicationError("屏蔽状态必须是布尔值。")
        reason = self._request_text(request, "reason", 500)
        self.repository.moderate_message(message_id, int(admin["id"]), blocked, reason)
        return {"message_id": message_id, "is_blocked": blocked}

    def _admin_list_operation_logs(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_admin(request)
        after_id = request.get("after_id", 0)
        if type(after_id) is not int or after_id < 0:
            raise ApplicationError("分页编号无效。")
        search = request.get("search", "")
        if not isinstance(search, str) or len(search) > 64:
            raise ApplicationError("搜索关键词无效。")
        rows = self.repository.list_operation_logs(after_id, search.strip())
        public_rows = []
        for row in rows[:50]:
            public = dict(row)
            public["success"] = bool(public.get("success"))
            public_rows.append(public)
        return {"logs": public_rows, "has_more": len(rows) > 50}

    def _send_message(self, request: dict[str, Any]) -> dict[str, Any]:
        current_user = self._current_user(request)
        body = self._request_text(request, "body")
        if current_user["role"] == "admin":
            recipient_id = self._request_id(request)
            recipient = self.repository.find_user(recipient_id)
            if recipient is None or recipient["role"] != "user" or not recipient["is_active"]:
                raise ApplicationError("消息接收用户不存在或已被停用。")
        else:
            recipient_id = None
            if "user_id" in request:
                recipient_id = self._request_id(request)
                recipient = self.repository.find_user(recipient_id)
                if (
                    recipient_id == int(current_user["id"])
                    or recipient is None
                    or not recipient["is_active"]
                ):
                    raise ApplicationError("该用户不可联系。")
        message_id = self.repository.create_message(int(current_user["id"]), recipient_id, body)
        return {"message_id": message_id}

    def _user_list_contacts(self, request: dict[str, Any]) -> dict[str, Any]:
        current_user = self._current_user(request)
        if current_user["role"] != "user":
            raise ApplicationError("此操作仅普通用户可用。")
        search = request.get("search", "")
        if not isinstance(search, str) or len(search) > 32:
            raise ApplicationError("搜索关键词无效。")
        contacts = self.repository.list_contactable_users(int(current_user["id"]), search.strip())
        return {"users": [self._public_user(user) for user in contacts]}

    def _admin_list_users(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_admin(request)
        search = request.get("search", "")
        if not isinstance(search, str) or len(search) > 32:
            raise ApplicationError("搜索关键词无效。")
        users = []
        for user in self.repository.list_users(search):
            public = self._public_user(user)
            public.update({
                "gender_identity": user.get("gender_identity", ""),
                "job_title": user.get("job_title", ""),
                "bio": user.get("bio", ""),
            })
            users.append(public)
        return {"users": users}

    def _admin_create_user(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_admin(request)
        username = validate_username(request.get("username"))
        password = validate_password(request.get("password"))
        role = request.get("role", "user")
        if role not in {"admin", "user"}:
            raise ApplicationError("角色无效。")
        user_id = self.repository.create_user(username, hash_password(password), role)
        return {"user_id": user_id}

    def _admin_update_user(self, request: dict[str, Any]) -> dict[str, Any]:
        current_admin = self._require_admin(request)
        user_id = self._request_id(request)
        username = validate_username(request.get("username"))
        role = request.get("role")
        is_active = request.get("is_active")
        if role not in {"admin", "user"} or not isinstance(is_active, bool):
            raise ApplicationError("用户角色或状态无效。")
        existing = self.repository.find_user(user_id)
        if existing is None:
            raise ApplicationError("用户不存在。")
        if int(current_admin["id"]) == user_id and (role != "admin" or not is_active):
            raise ApplicationError("管理员不能移除或停用自己的管理员账户。")
        if existing["role"] == "admin" and existing["is_active"] and (role != "admin" or not is_active):
            if self.repository.count_active_admins() <= 1:
                raise ApplicationError("系统至少需要保留一个启用的管理员。")
        self.repository.update_user(user_id, username, role, is_active)
        return {}

    def _admin_delete_user(self, request: dict[str, Any]) -> dict[str, Any]:
        current_admin = self._require_admin(request)
        user_id = self._request_id(request)
        existing = self.repository.find_user(user_id)
        if existing is None:
            raise ApplicationError("用户不存在。")
        if int(current_admin["id"]) == user_id:
            raise ApplicationError("管理员不能删除自己的账户。")
        if existing["role"] == "admin" and existing["is_active"] and self.repository.count_active_admins() <= 1:
            raise ApplicationError("系统至少需要保留一个启用的管理员。")
        self.repository.delete_user(user_id)
        return {}

    def _admin_reset_password(self, request: dict[str, Any]) -> dict[str, Any]:
        self._require_admin(request)
        user_id = self._request_id(request)
        password = validate_password(request.get("password"))
        self.repository.reset_password(user_id, hash_password(password))
        return {}

from __future__ import annotations

import json
import unittest
import base64

from server.application import SecureMessengerApplication
from server.security import hash_password


class MemoryRepository:
    """Small repository double for verifying authorization and request routing without MySQL."""

    def __init__(self) -> None:
        self.users: dict[int, dict] = {}
        self.sessions: dict[str, int] = {}
        self.messages: list[dict] = []
        self.next_user_id = 1
        self.moderation_events: list[dict] = []
        self.operation_logs: list[dict] = []
        self.next_operation_log_id = 1

    def has_admin(self) -> bool:
        return any(user["role"] == "admin" for user in self.users.values())

    def count_active_admins(self) -> int:
        return sum(user["role"] == "admin" and user["is_active"] for user in self.users.values())

    def create_user(self, username: str, password_hash: str, role: str = "user") -> int:
        if any(user["username"] == username for user in self.users.values()):
            from server.database import DuplicateUsernameError

            raise DuplicateUsernameError("该用户名已被使用。")
        user_id = self.next_user_id
        self.next_user_id += 1
        self.users[user_id] = {
            "id": user_id, "username": username, "password_hash": password_hash, "role": role, "is_active": True,
            "avatar_data": None, "avatar_mime": None, "gender_identity": "", "job_title": "", "bio": "", "created_at": None,
        }
        return user_id

    def find_user_by_username(self, username: str):
        return next((dict(user) for user in self.users.values() if user["username"] == username), None)

    def find_user(self, user_id: int):
        user = self.users.get(user_id)
        if user is None:
            return None
        public = dict(user)
        public.pop("password_hash", None)
        return public

    def list_users(self, search: str = ""):
        return [self.find_user(user_id) for user_id, user in self.users.items() if search in user["username"]]

    def list_contactable_users(self, current_user_id: int, search: str = ""):
        return [
            self.find_user(user_id)
            for user_id, user in self.users.items()
            if user_id != current_user_id and user["is_active"] and (search in user["username"] or search in user["job_title"])
        ]

    def update_user(self, user_id: int, username: str, role: str, is_active: bool) -> None:
        self.users[user_id].update(username=username, role=role, is_active=is_active)

    def update_profile(self, user_id, gender_identity, job_title, bio, avatar_data=None, avatar_mime=None, replace_avatar=False):
        from server.database import RecordNotFoundError
        if user_id not in self.users:
            raise RecordNotFoundError("用户不存在。")
        values = dict(gender_identity=gender_identity, job_title=job_title, bio=bio)
        if replace_avatar:
            values.update(avatar_data=avatar_data, avatar_mime=avatar_mime)
        self.users[user_id].update(values)

    def reset_password(self, user_id: int, password_hash: str) -> None:
        self.users[user_id]["password_hash"] = password_hash
        self.sessions = {token: owner for token, owner in self.sessions.items() if owner != user_id}

    def delete_user(self, user_id: int) -> None:
        del self.users[user_id]

    def create_session(self, user_id: int) -> str:
        token = f"token-{user_id}-{len(self.sessions)}"
        self.sessions[token] = user_id
        return token

    def get_session_user(self, token: str):
        user = self.users.get(self.sessions.get(token, 0))
        if user is None or not user["is_active"]:
            return None
        return {key: user[key] for key in ("id", "username", "role", "is_active")}

    def delete_session(self, token: str) -> None:
        self.sessions.pop(token, None)

    def create_message(self, sender_id: int, recipient_id: int | None, body: str) -> int:
        message_id = len(self.messages) + 1
        self.messages.append({"id": message_id, "sender_id": sender_id, "recipient_id": recipient_id, "body": body, "created_at": "now", "sender_username": self.users[sender_id]["username"], "sender_role": self.users[sender_id]["role"]})
        return message_id

    def get_admin_conversation(self, user_id: int):
        return [
            message
            for message in self.messages
            if (message["sender_id"] == user_id and message["recipient_id"] is None)
            or (message["recipient_id"] == user_id and message["sender_role"] == "admin")
        ]

    def get_direct_conversation(self, first_user_id: int, second_user_id: int):
        return [
            message
            for message in self.messages
            if (message["sender_id"] == first_user_id and message["recipient_id"] == second_user_id)
            or (message["sender_id"] == second_user_id and message["recipient_id"] == first_user_id)
        ]

    def get_user_admin_conversation(self, user_id: int, admin_id: int):
        return [
            message
            for message in self.messages
            if (message["sender_id"] == user_id and message["recipient_id"] == admin_id)
            or (message["sender_id"] == admin_id and message["recipient_id"] == user_id)
            or (message["sender_id"] == user_id and message["recipient_id"] is None)
        ]

    def review_messages(self, user_id, after_id):
        return [dict(message, recipient_username=self.users.get(message["recipient_id"], {}).get("username"))
                for message in self.messages if message["id"] > after_id
                and (user_id is None or user_id in (message["sender_id"], message["recipient_id"]))][:41]

    def moderate_message(self, message_id, moderator_id, blocked, reason):
        from server.database import RecordNotFoundError
        message = next((message for message in self.messages if message["id"] == message_id), None)
        if message is None:
            raise RecordNotFoundError("消息不存在或已被删除。")
        message.update(is_blocked=blocked, reason=reason, moderated_at="now", moderator_username=self.users[moderator_id]["username"])
        self.moderation_events.append(dict(message_id=message_id, moderator_id=moderator_id, is_blocked=blocked, reason=reason))

    def create_operation_log(self, actor_id, action, success, target_user_id=None, message_id=None, detail="", actor_username=None):
        self.operation_logs.append({
            "id": self.next_operation_log_id,
            "actor_id": actor_id,
            "actor_username": actor_username,
            "action": action,
            "success": success,
            "target_user_id": target_user_id,
            "message_id": message_id,
            "detail": detail,
            "created_at": "now",
        })
        self.next_operation_log_id += 1

    def list_operation_logs(self, after_id, search=""):
        result = []
        for record in self.operation_logs:
            if record["id"] <= after_id:
                continue
            row = dict(record)
            row["actor_username"] = row.get("actor_username") or self.users.get(row["actor_id"], {}).get("username")
            row["target_username"] = self.users.get(row["target_user_id"], {}).get("username")
            searchable = " ".join(str(row.get(key) or "") for key in ("action", "detail", "actor_username", "target_username"))
            if search not in searchable:
                result.append(None)
                continue
            result.append(row)
            if len([item for item in result if item is not None]) >= 51:
                break
        return [item for item in result if item is not None]


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = MemoryRepository()
        self.admin_id = self.repository.create_user("admin_01", hash_password("admin-password"), "admin")
        self.application = SecureMessengerApplication(self.repository)

    def call(self, action: str, **payload):
        return json.loads(self.application.handle(json.dumps({"action": action, **payload}, ensure_ascii=False)))

    def test_user_registration_message_and_admin_reply(self) -> None:
        registration = self.call("register", username="user_01", password="user-password")
        self.assertTrue(registration["ok"])
        user_token = registration["data"]["token"]
        user_id = registration["data"]["user"]["id"]
        self.assertTrue(self.call("send_message", token=user_token, body="管理员您好")["ok"])

        admin_login = self.call("login", username="admin_01", password="admin-password")
        admin_token = admin_login["data"]["token"]
        conversation = self.call("conversation", token=admin_token, user_id=user_id)
        self.assertEqual(conversation["data"]["messages"][0]["body"], "管理员您好")
        self.assertTrue(self.call("send_message", token=admin_token, user_id=user_id, body="已收到")["ok"])
        user_conversation = self.call("conversation", token=user_token)
        self.assertEqual([item["body"] for item in user_conversation["data"]["messages"]], ["管理员您好", "已收到"])

    def test_admin_password_reset_invalidates_old_session(self) -> None:
        registration = self.call("register", username="user_02", password="old-password")
        user_id = registration["data"]["user"]["id"]
        old_token = registration["data"]["token"]
        admin_token = self.call("login", username="admin_01", password="admin-password")["data"]["token"]
        self.assertTrue(self.call("admin_reset_password", token=admin_token, user_id=user_id, password="new-password")["ok"])
        self.assertFalse(self.call("conversation", token=old_token)["ok"])
        self.assertFalse(self.call("login", username="user_02", password="old-password")["ok"])
        self.assertTrue(self.call("login", username="user_02", password="new-password")["ok"])

    def test_moderation_redacts_both_participants_but_retains_admin_evidence(self):
        alice = self.call("register", username="alice", password="user-password")["data"]
        bob = self.call("register", username="bobby", password="user-password")["data"]
        admin = self.repository.create_session(self.admin_id)
        message_id = self.call("send_message", token=alice["token"], user_id=bob["user"]["id"], body="违规测试原文")["data"]["message_id"]
        result = self.call("admin_moderate_message", token=admin, message_id=message_id, is_blocked=True, reason="含违规内容")
        self.assertTrue(result["ok"], result)
        for sender, recipient in ((alice, bob), (bob, alice)):
            result = self.call("conversation", token=sender["token"], user_id=recipient["user"]["id"])
            message = result["data"]["messages"][0]
            self.assertTrue(message["is_blocked"])
            self.assertNotIn("违规测试原文", json.dumps(result, ensure_ascii=False))
            self.assertNotIn("reason", message)
            self.assertNotIn("moderator_username", message)
        reviewed = self.call("admin_review_messages", token=admin, user_id=bob["user"]["id"])["data"]["messages"][0]
        self.assertEqual(reviewed["body"], "违规测试原文")
        self.assertEqual(reviewed["reason"], "含违规内容")
        self.assertTrue(self.call("admin_moderate_message", token=admin, message_id=message_id, is_blocked=False, reason="复核解除")["ok"])
        restored = self.call("conversation", token=bob["token"], user_id=alice["user"]["id"])["data"]["messages"][0]
        self.assertEqual(restored["body"], "违规测试原文")
        self.assertFalse(restored["is_blocked"])
        self.assertEqual(len(self.repository.moderation_events), 2)

    def test_moderation_denies_ordinary_expired_and_anonymous_callers(self):
        user = self.call("register", username="alice", password="user-password")["data"]
        for token in (None, "invalid", user["token"]):
            self.assertFalse(self.call("admin_review_messages", token=token)["ok"])
            self.assertFalse(self.call("admin_moderate_message", token=token, message_id=1, is_blocked=True, reason="test")["ok"])
        admin = self.repository.create_session(self.admin_id)
        for message_id, state, reason in ((True, True, "test"), (1, "true", "test"), (1, True, ""), (1, True, "a" * 501)):
            self.assertFalse(self.call("admin_moderate_message", token=admin, message_id=message_id, is_blocked=state, reason=reason)["ok"])
        self.assertFalse(self.call("admin_moderate_message", token=admin, message_id=999, is_blocked=True, reason="test")["ok"])
        for cursor in (True, -1, "1"):
            self.assertFalse(self.call("admin_review_messages", token=admin, after_id=cursor)["ok"])

    def test_support_redaction_and_review_pagination(self):
        user = self.call("register", username="alice", password="user-password")["data"]
        other = self.call("register", username="bobby", password="user-password")["data"]
        admin = self.repository.create_session(self.admin_id)
        for i in range(42):
            self.repository.create_message(user["user"]["id"], None, f"支持消息{i}")
        self.repository.create_message(other["user"]["id"], None, "其他人的消息")
        first = self.call("admin_review_messages", token=admin, user_id=user["user"]["id"])["data"]
        self.assertEqual(len(first["messages"]), 40)
        self.assertTrue(first["has_more"])
        last = self.call("admin_review_messages", token=admin, user_id=user["user"]["id"], after_id=40)["data"]
        self.assertEqual([row["id"] for row in last["messages"]], [41, 42])
        self.assertFalse(last["has_more"])
        self.assertTrue(self.call("admin_moderate_message", token=admin, message_id=1, is_blocked=True, reason="违规")["ok"])
        self.assertNotEqual(self.call("conversation", token=user["token"])["data"]["messages"][0]["body"], "支持消息0")
        self.assertEqual(self.call("conversation", token=admin, user_id=user["user"]["id"])["data"]["messages"][0]["body"], "支持消息0")

    def test_users_discover_contacts_and_exchange_private_messages(self) -> None:
        first = self.call("register", username="user_03", password="user-password")
        second = self.call("register", username="user_04", password="user-password")
        first_token = first["data"]["token"]
        first_id = first["data"]["user"]["id"]
        second_token = second["data"]["token"]
        second_id = second["data"]["user"]["id"]

        contacts = self.call("user_list_contacts", token=first_token)
        self.assertTrue(contacts["ok"])
        self.assertEqual([user["username"] for user in contacts["data"]["users"]], ["admin_01", "user_04"])
        self.assertEqual(contacts["data"]["users"][0]["role"], "admin")
        self.assertFalse(self.call("user_list_contacts", token=self.call("login", username="admin_01", password="admin-password")["data"]["token"])["ok"])

        self.assertTrue(self.call("send_message", token=first_token, user_id=self.admin_id, body="管理员也在联系人里。 ")["ok"])
        admin_view = self.call("conversation", token=first_token, user_id=self.admin_id)
        self.assertEqual([message["body"] for message in admin_view["data"]["messages"]], ["管理员也在联系人里。"])

        self.assertTrue(self.call("send_message", token=first_token, user_id=second_id, body="你好，想交流一下。 ")["ok"])
        self.assertTrue(self.call("send_message", token=second_token, user_id=first_id, body="你好，当然可以。 ")["ok"])
        first_view = self.call("conversation", token=first_token, user_id=second_id)
        second_view = self.call("conversation", token=second_token, user_id=first_id)
        expected = ["你好，想交流一下。", "你好，当然可以。"]
        self.assertEqual([message["body"] for message in first_view["data"]["messages"]], expected)
        self.assertEqual([message["body"] for message in second_view["data"]["messages"]], expected)
        self.assertFalse(self.call("send_message", token=first_token, user_id=first_id, body="给自己发消息")["ok"])

    def test_admin_can_read_safe_database_audit_log(self) -> None:
        user = self.call("register", username="audit_user", password="audit-password")["data"]
        secret_body = "这段私密消息绝不能进入操作日志"
        self.assertTrue(self.call("send_message", token=user["token"], body=secret_body)["ok"])
        self.assertFalse(self.call("login", username="audit_user", password="wrong-password")["ok"])
        admin_token = self.repository.create_session(self.admin_id)

        before_read = len(self.repository.operation_logs)
        response = self.call("admin_list_operation_logs", token=admin_token)
        self.assertTrue(response["ok"])
        self.assertEqual(len(self.repository.operation_logs), before_read, "查看日志本身不应制造无限日志")
        logs = response["data"]["logs"]
        self.assertEqual([row["action"] for row in logs], ["register", "send_message", "login"])
        self.assertEqual([row["success"] for row in logs], [True, True, False])
        self.assertEqual(logs[1]["actor_username"], "audit_user")
        self.assertEqual(logs[1]["message_id"], 1)
        rendered = json.dumps(logs, ensure_ascii=False)
        self.assertNotIn(secret_body, rendered)
        self.assertNotIn("audit-password", rendered)
        self.assertNotIn("wrong-password", rendered)
        self.repository.delete_user(user["user"]["id"])
        after_delete = self.call("admin_list_operation_logs", token=admin_token)["data"]["logs"]
        self.assertEqual(after_delete[1]["actor_username"], "audit_user")

    def test_operation_log_is_admin_only_and_paged(self) -> None:
        user = self.call("register", username="log_user", password="user-password")["data"]
        self.assertFalse(self.call("admin_list_operation_logs", token=user["token"])["ok"])
        admin_token = self.repository.create_session(self.admin_id)
        self.repository.operation_logs.clear()
        self.repository.next_operation_log_id = 1
        for _ in range(51):
            self.repository.create_operation_log(self.admin_id, "login", True, detail="登录系统")
        first = self.call("admin_list_operation_logs", token=admin_token, after_id=0)["data"]
        self.assertEqual(len(first["logs"]), 50)
        self.assertTrue(first["has_more"])
        second = self.call("admin_list_operation_logs", token=admin_token, after_id=50)["data"]
        self.assertEqual([row["id"] for row in second["logs"]], [51])
        self.assertFalse(second["has_more"])
        self.assertFalse(self.call("admin_list_operation_logs", token=admin_token, after_id=True)["ok"])
        self.assertFalse(self.call("admin_list_operation_logs", token=admin_token, search="x" * 65)["ok"])

    def test_personal_profile_supports_diverse_gender_and_safe_avatar(self) -> None:
        user = self.call("register", username="profile_user", password="user-password")["data"]
        avatar_bytes = b"\x89PNG\r\n\x1a\nprofile-test-avatar"
        avatar = {"mime": "image/png", "data": base64.b64encode(avatar_bytes).decode("ascii")}
        updated = self.call(
            "update_profile", token=user["token"], gender_identity="非二元性别", job_title="产品设计师",
            bio="喜欢做无障碍设计。", avatar=avatar,
        )
        self.assertTrue(updated["ok"], updated)
        profile = updated["data"]["user"]
        self.assertEqual(profile["gender_identity"], "非二元性别")
        self.assertEqual(profile["job_title"], "产品设计师")
        self.assertEqual(profile["avatar"], avatar)
        self.assertEqual(self.call("get_profile", token=user["token"])["data"]["user"], profile)
        self.assertFalse(self.call("update_profile", token=user["token"], gender_identity="x" * 65, job_title="", bio="")["ok"])
        self.assertFalse(self.call("update_profile", token=user["token"], gender_identity="", job_title="", bio="", avatar={"mime": "image/jpeg", "data": avatar["data"]})["ok"])
        audit = self.repository.operation_logs[-3]
        self.assertEqual(audit["action"], "update_profile")
        self.assertNotIn(avatar["data"], json.dumps(audit, ensure_ascii=False))

    def test_other_users_can_view_public_profiles_including_administrators(self) -> None:
        first = self.call("register", username="profile_first", password="user-password")["data"]
        second = self.call("register", username="profile_second", password="user-password")["data"]
        self.assertTrue(self.call(
            "update_profile", token=first["token"], gender_identity="无性别", job_title="工程师", bio="公开资料"
        )["ok"])
        viewed = self.call("get_user_profile", token=second["token"], user_id=first["user"]["id"])
        self.assertTrue(viewed["ok"])
        self.assertEqual(viewed["data"]["user"]["bio"], "公开资料")
        self.assertFalse(self.call("get_user_profile", token=first["token"], user_id=first["user"]["id"])["ok"])
        admin_profile = self.call("get_user_profile", token=second["token"], user_id=self.admin_id)
        self.assertTrue(admin_profile["ok"])
        self.assertEqual(admin_profile["data"]["user"]["username"], "admin_01")


if __name__ == "__main__":
    unittest.main()

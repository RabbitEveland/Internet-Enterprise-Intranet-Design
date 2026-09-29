"""MySQL persistence for users, sessions, support messages, and direct messages."""

from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import hashlib
import re
import secrets
from typing import Any, Iterator

try:
    import mysql.connector as mysql_connector
    from mysql.connector import Error, IntegrityError, pooling
except ModuleNotFoundError:  # Allows the non-database test suite to run before dependency installation.
    mysql_connector = None

    class Error(Exception):
        pass

    class IntegrityError(Error):
        pass

    pooling = None

from common.config import Settings


DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")
SESSION_HOURS = 8


class RepositoryError(RuntimeError):
    """Base class for persistence errors safe to show to the application layer."""


class DuplicateUsernameError(RepositoryError):
    pass


class RecordNotFoundError(RepositoryError):
    pass


class MySQLRepository:
    def __init__(self, settings: Settings, password: str) -> None:
        if not DATABASE_NAME_PATTERN.fullmatch(settings.database_name):
            raise RepositoryError("数据库名称只能包含字母、数字和下划线。")
        self.settings = settings
        self.password = password
        self.pool: Any = None

    def initialize(self) -> None:
        """Connect to the provisioned schema and create application tables if needed."""
        if mysql_connector is None or pooling is None:
            raise RepositoryError("缺少 mysql-connector-python，请在 PyCharm 当前解释器中安装 requirements.txt。")
        try:
            self.pool = pooling.MySQLConnectionPool(
                pool_name=f"secure_messenger_{id(self)}",
                pool_size=5,
                host=self.settings.database_host,
                port=self.settings.database_port,
                database=self.settings.database_name,
                user=self.settings.database_user,
                password=self.password,
                connection_timeout=self.settings.database_connect_timeout_seconds,
                charset="utf8mb4",
                collation="utf8mb4_unicode_ci",
            )
            self._create_tables()
        except Error as exc:
            raise RepositoryError(f"无法连接或初始化用户与消息表：{exc}") from exc

    @contextmanager
    def _cursor(self, dictionary: bool = True) -> Iterator[Any]:
        if self.pool is None:
            raise RepositoryError("数据库连接池尚未初始化。")
        connection = self.pool.get_connection()
        cursor = connection.cursor(dictionary=dictionary)
        try:
            yield connection, cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def _create_tables(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(32) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                avatar_data MEDIUMBLOB NULL,
                avatar_mime VARCHAR(32) NULL,
                gender_identity VARCHAR(64) NOT NULL DEFAULT '',
                job_title VARCHAR(80) NOT NULL DEFAULT '',
                bio VARCHAR(500) NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash CHAR(64) NOT NULL PRIMARY KEY,
                user_id BIGINT UNSIGNED NOT NULL,
                expires_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_sessions_expiry (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                sender_id BIGINT UNSIGNED NOT NULL,
                recipient_id BIGINT UNSIGNED NULL,
                body TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_messages_sender FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                CONSTRAINT fk_messages_recipient FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_messages_sender_recipient_time (sender_id, recipient_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        )
        with self._cursor(dictionary=False) as (_connection, cursor):
            for statement in statements:
                cursor.execute(statement)
            # Add profile columns for installations created before the personal center.
            for column, definition in (
                ("avatar_data", "MEDIUMBLOB NULL"),
                ("avatar_mime", "VARCHAR(32) NULL"),
                ("gender_identity", "VARCHAR(64) NOT NULL DEFAULT ''"),
                ("job_title", "VARCHAR(80) NOT NULL DEFAULT ''"),
                ("bio", "VARCHAR(500) NOT NULL DEFAULT ''"),
            ):
                cursor.execute(f"SHOW COLUMNS FROM users LIKE '{column}'")
                if cursor.fetchone() is None:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_moderation (
                    message_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
                    is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
                    reason VARCHAR(500) NOT NULL,
                    moderator_id BIGINT UNSIGNED NULL,
                    moderated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    FOREIGN KEY (moderator_id) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS moderation_events (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    message_id BIGINT UNSIGNED NOT NULL,
                    moderator_id BIGINT UNSIGNED NULL,
                    is_blocked BOOLEAN NOT NULL,
                    reason VARCHAR(500) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    FOREIGN KEY (moderator_id) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    actor_id BIGINT UNSIGNED NULL,
                    actor_username VARCHAR(32) NULL,
                    action VARCHAR(64) NOT NULL,
                    success BOOLEAN NOT NULL,
                    target_user_id BIGINT UNSIGNED NULL,
                    message_id BIGINT UNSIGNED NULL,
                    detail VARCHAR(500) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_operation_logs_actor FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL,
                    CONSTRAINT fk_operation_logs_target_user FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL,
                    INDEX idx_operation_logs_created (created_at, id),
                    INDEX idx_operation_logs_actor (actor_id, id),
                    INDEX idx_operation_logs_action (action, id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Existing deployments may have created the first audit-table version
            # before the account-name snapshot was introduced.
            cursor.execute("SHOW COLUMNS FROM operation_logs LIKE 'actor_username'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE operation_logs ADD COLUMN actor_username VARCHAR(32) NULL AFTER actor_id")

    def has_admin(self) -> bool:
        with self._cursor() as (_connection, cursor):
            cursor.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1")
            return cursor.fetchone() is not None

    def count_active_admins(self) -> int:
        with self._cursor() as (_connection, cursor):
            cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = TRUE")
            return int(cursor.fetchone()["count"])

    def create_user(self, username: str, password_hash: str, role: str = "user") -> int:
        try:
            with self._cursor() as (_connection, cursor):
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, password_hash, role),
                )
                return int(cursor.lastrowid)
        except IntegrityError as exc:
            raise DuplicateUsernameError("该用户名已被使用。") from exc

    def find_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT id, username, password_hash, role, is_active, created_at FROM users WHERE username = %s",
                (username,),
            )
            return cursor.fetchone()

    def find_user(self, user_id: int) -> dict[str, Any] | None:
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT id, username, role, is_active, avatar_data, avatar_mime, gender_identity, job_title, bio, created_at "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            return cursor.fetchone()

    def list_users(self, search: str = "") -> list[dict[str, Any]]:
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT id, username, role, is_active, gender_identity, job_title, bio, created_at FROM users "
                "WHERE username LIKE %s ORDER BY role DESC, username ASC",
                (f"%{search}%",),
            )
            return list(cursor.fetchall())

    def list_contactable_users(self, current_user_id: int, search: str = "") -> list[dict[str, Any]]:
        """Return every active account a normal user may contact, including administrators."""
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT id, username, role, is_active, gender_identity, job_title, bio, created_at FROM users "
                "WHERE id <> %s AND is_active = TRUE AND (username LIKE %s OR job_title LIKE %s) "
                "ORDER BY job_title ASC, role DESC, username ASC",
                (current_user_id, f"%{search}%", f"%{search}%"),
            )
            return list(cursor.fetchall())

    def update_user(self, user_id: int, username: str, role: str, is_active: bool) -> None:
        try:
            with self._cursor() as (_connection, cursor):
                cursor.execute(
                    "UPDATE users SET username = %s, role = %s, is_active = %s WHERE id = %s",
                    (username, role, is_active, user_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
                    if cursor.fetchone() is None:
                        raise RecordNotFoundError("用户不存在。")
        except IntegrityError as exc:
            raise DuplicateUsernameError("该用户名已被使用。") from exc

    def update_profile(
        self,
        user_id: int,
        gender_identity: str,
        job_title: str,
        bio: str,
        avatar_data: bytes | None = None,
        avatar_mime: str | None = None,
        replace_avatar: bool = False,
    ) -> None:
        with self._cursor() as (_connection, cursor):
            if replace_avatar:
                cursor.execute(
                    "UPDATE users SET gender_identity = %s, job_title = %s, bio = %s, avatar_data = %s, avatar_mime = %s "
                    "WHERE id = %s",
                    (gender_identity, job_title, bio, avatar_data, avatar_mime, user_id),
                )
            else:
                cursor.execute(
                    "UPDATE users SET gender_identity = %s, job_title = %s, bio = %s WHERE id = %s",
                    (gender_identity, job_title, bio, user_id),
                )
            if cursor.rowcount == 0:
                cursor.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
                if cursor.fetchone() is None:
                    raise RecordNotFoundError("用户不存在。")

    def reset_password(self, user_id: int, password_hash: str) -> None:
        with self._cursor() as (_connection, cursor):
            cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))
            if cursor.rowcount == 0:
                raise RecordNotFoundError("用户不存在。")
            cursor.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))

    def delete_user(self, user_id: int) -> None:
        with self._cursor() as (_connection, cursor):
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            if cursor.rowcount == 0:
                raise RecordNotFoundError("用户不存在。")

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = dt.datetime.utcnow() + dt.timedelta(hours=SESSION_HOURS)
        with self._cursor() as (_connection, cursor):
            cursor.execute("DELETE FROM sessions WHERE expires_at < UTC_TIMESTAMP()")
            cursor.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user_id, expires_at),
            )
        return token

    def get_session_user(self, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._cursor() as (_connection, cursor):
            cursor.execute("DELETE FROM sessions WHERE expires_at < UTC_TIMESTAMP()")
            cursor.execute(
                "SELECT u.id, u.username, u.role, u.is_active FROM sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.token_hash = %s AND u.is_active = TRUE",
                (token_hash,),
            )
            return cursor.fetchone()

    def delete_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._cursor() as (_connection, cursor):
            cursor.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))

    def create_message(self, sender_id: int, recipient_id: int | None, body: str) -> int:
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "INSERT INTO messages (sender_id, recipient_id, body) VALUES (%s, %s, %s)",
                (sender_id, recipient_id, body),
            )
            return int(cursor.lastrowid)

    def get_admin_conversation(self, user_id: int) -> list[dict[str, Any]]:
        """Return the support conversation between one user and any administrator."""
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT m.id, m.sender_id, m.recipient_id, m.body, m.created_at, "
                "sender.username AS sender_username, sender.role AS sender_role, "
                "COALESCE(review.is_blocked, FALSE) AS is_blocked "
                "FROM messages m JOIN users sender ON sender.id = m.sender_id "
                "LEFT JOIN message_moderation review ON review.message_id = m.id "
                "WHERE (m.sender_id = %s AND m.recipient_id IS NULL) "
                "OR (m.recipient_id = %s AND sender.role = 'admin') "
                "ORDER BY m.created_at ASC, m.id ASC",
                (user_id, user_id),
            )
            return list(cursor.fetchall())

    def get_direct_conversation(self, first_user_id: int, second_user_id: int) -> list[dict[str, Any]]:
        """Return messages exchanged exclusively between two ordinary users."""
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT m.id, m.sender_id, m.recipient_id, m.body, m.created_at, "
                "sender.username AS sender_username, sender.role AS sender_role, "
                "COALESCE(review.is_blocked, FALSE) AS is_blocked "
                "FROM messages m JOIN users sender ON sender.id = m.sender_id "
                "LEFT JOIN message_moderation review ON review.message_id = m.id "
                "WHERE (m.sender_id = %s AND m.recipient_id = %s) "
                "OR (m.sender_id = %s AND m.recipient_id = %s) "
                "ORDER BY m.created_at ASC, m.id ASC",
                (first_user_id, second_user_id, second_user_id, first_user_id),
            )
            return list(cursor.fetchall())

    def get_user_admin_conversation(self, user_id: int, admin_id: int) -> list[dict[str, Any]]:
        """Direct messages plus a user's legacy unaddressed support requests to that admin."""
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT m.id, m.sender_id, m.recipient_id, m.body, m.created_at, "
                "sender.username AS sender_username, sender.role AS sender_role, "
                "COALESCE(review.is_blocked, FALSE) AS is_blocked "
                "FROM messages m JOIN users sender ON sender.id = m.sender_id "
                "LEFT JOIN message_moderation review ON review.message_id = m.id "
                "WHERE (m.sender_id = %s AND m.recipient_id = %s) "
                "OR (m.sender_id = %s AND m.recipient_id = %s) "
                "OR (m.sender_id = %s AND m.recipient_id IS NULL) "
                "ORDER BY m.created_at ASC, m.id ASC",
                (user_id, admin_id, admin_id, user_id, user_id),
            )
            return list(cursor.fetchall())

    def review_messages(self, user_id: int | None, after_id: int) -> list[dict[str, Any]]:
        """Administrator-only caller; bounded pages retain original text for review."""
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT m.id, m.sender_id, m.recipient_id, m.body, m.created_at, "
                "sender.username AS sender_username, recipient.username AS recipient_username, "
                "COALESCE(review.is_blocked, FALSE) AS is_blocked, review.reason, "
                "review.moderated_at, moderator.username AS moderator_username "
                "FROM messages m JOIN users sender ON sender.id = m.sender_id "
                "LEFT JOIN users recipient ON recipient.id = m.recipient_id "
                "LEFT JOIN message_moderation review ON review.message_id = m.id "
                "LEFT JOIN users moderator ON moderator.id = review.moderator_id "
                "WHERE m.id > %s AND (%s IS NULL OR m.sender_id = %s OR m.recipient_id = %s) "
                "ORDER BY m.id ASC LIMIT 41",
                (after_id, user_id, user_id, user_id),
            )
            return list(cursor.fetchall())

    def moderate_message(self, message_id: int, moderator_id: int, blocked: bool, reason: str) -> None:
        with self._cursor(dictionary=False) as (_connection, cursor):
            cursor.execute("SELECT id FROM messages WHERE id = %s FOR UPDATE", (message_id,))
            if cursor.fetchone() is None:
                raise RecordNotFoundError("消息不存在或已被删除。")
            cursor.execute(
                "INSERT INTO message_moderation (message_id, is_blocked, reason, moderator_id) "
                "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                "is_blocked = %s, reason = %s, moderator_id = %s, moderated_at = CURRENT_TIMESTAMP",
                (message_id, blocked, reason, moderator_id, blocked, reason, moderator_id),
            )
            cursor.execute(
                "INSERT INTO moderation_events (message_id, moderator_id, is_blocked, reason) VALUES (%s, %s, %s, %s)",
                (message_id, moderator_id, blocked, reason),
            )

    def create_operation_log(
        self,
        actor_id: int | None,
        action: str,
        success: bool,
        target_user_id: int | None = None,
        message_id: int | None = None,
        detail: str = "",
        actor_username: str | None = None,
    ) -> None:
        """Store safe, structured audit metadata; callers must never pass secrets or message text."""
        with self._cursor(dictionary=False) as (_connection, cursor):
            cursor.execute(
                "INSERT INTO operation_logs "
                "(actor_id, actor_username, action, success, target_user_id, message_id, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (actor_id, actor_username, action, success, target_user_id, message_id, detail[:500]),
            )

    def list_operation_logs(self, after_id: int, search: str = "") -> list[dict[str, Any]]:
        """Return a bounded chronological audit page with account names resolved when available."""
        pattern = f"%{search}%"
        with self._cursor() as (_connection, cursor):
            cursor.execute(
                "SELECT log.id, log.actor_id, COALESCE(log.actor_username, actor.username) AS actor_username, "
                "log.action, log.success, log.target_user_id, "
                "log.message_id, log.detail, log.created_at, "
                "target.username AS target_username "
                "FROM operation_logs log "
                "LEFT JOIN users actor ON actor.id = log.actor_id "
                "LEFT JOIN users target ON target.id = log.target_user_id "
                "WHERE log.id > %s AND (log.action LIKE %s OR log.detail LIKE %s "
                "OR COALESCE(log.actor_username, actor.username, '') LIKE %s OR COALESCE(target.username, '') LIKE %s) "
                "ORDER BY log.id ASC LIMIT 51",
                (after_id, pattern, pattern, pattern, pattern),
            )
            return list(cursor.fetchall())

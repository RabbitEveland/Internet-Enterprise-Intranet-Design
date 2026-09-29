"""Opt-in integration test using a NEW disposable D-drive MySQL instance.

MYSQL_TEST_BASEDIR names installed binaries. MYSQL_TEST_TEMP_PARENT names an
ASCII-only temporary directory parent. No existing server/data is accessed.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from dataclasses import replace

from common.config import load_settings
from server.application import SecureMessengerApplication
from server.database import MySQLRepository


@unittest.skipUnless(os.environ.get("MYSQL_TEST_BASEDIR"), "isolated MySQL integration is opt-in")
class MySQLModerationTests(unittest.TestCase):
    def test_old_messages_survive_and_masking_is_persisted(self):
        import mysql.connector

        base = Path(os.environ["MYSQL_TEST_BASEDIR"]).resolve()
        parent = Path(os.environ["MYSQL_TEST_TEMP_PARENT"]).resolve()
        temporary = tempfile.TemporaryDirectory(prefix="moderation-test-", dir=parent)
        directory = Path(temporary.name).resolve()
        self.assertEqual(directory.parent, parent)
        self.assertTrue(directory.name.startswith("moderation-test-"))
        process = None
        connection = None
        binary = str(base / "bin" / "mysqld.exe")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        args = [binary, "--no-defaults", f"--basedir={base}", f"--datadir={directory / 'data'}",
                f"--log-error={directory / 'mysql.log'}"]
        try:
            subprocess.run(args + ["--initialize-insecure"], check=True, timeout=60, creationflags=flags,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen(args + [f"--port={port}", "--bind-address=127.0.0.1", "--mysqlx=OFF"],
                                       creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 25
            while connection is None:
                try:
                    connection = mysql.connector.connect(host="127.0.0.1", port=port, user="root", connection_timeout=1)
                except mysql.connector.Error:
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail("Disposable MySQL failed to start")
                    time.sleep(0.2)
            with connection.cursor() as cursor:
                cursor.execute("CREATE DATABASE moderation_test")
                cursor.execute("USE moderation_test")
                # Pre-upgrade schema and an existing conversation, with no moderation tables.
                cursor.execute("""CREATE TABLE users (
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, username VARCHAR(32) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL, role ENUM('admin','user') NOT NULL DEFAULT 'user',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB""")
                cursor.execute("""CREATE TABLE messages (
                    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, sender_id BIGINT UNSIGNED NOT NULL,
                    recipient_id BIGINT UNSIGNED NULL, body TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB""")
                cursor.execute("INSERT INTO users (username,password_hash,role) VALUES ('admin','unused','admin'), ('alice','unused','user'), ('bobby','unused','user')")
                cursor.execute("INSERT INTO messages (sender_id,recipient_id,body) VALUES (2,3,'original-private-text'), (2,NULL,'support-text')")
            connection.commit()
            settings = replace(load_settings(), database_host="127.0.0.1", database_port=port,
                               database_name="moderation_test", database_user="root")
            repository = MySQLRepository(settings, "")
            repository.initialize()
            repository._create_tables()  # Restart/idempotence must preserve existing history.
            application = SecureMessengerApplication(repository)
            admin = repository.create_session(1)
            alice = repository.create_session(2)
            bob = repository.create_session(3)

            def call(action, **payload):
                result = json.loads(application.handle(json.dumps(dict(action=action, **payload))))
                self.assertTrue(result["ok"], result)
                return result["data"]

            profile = call("update_profile", token=alice, gender_identity="非二元性别", job_title="测试职位", bio="测试简介")["user"]
            self.assertEqual(profile["gender_identity"], "非二元性别")
            self.assertEqual(call("get_profile", token=alice)["user"]["job_title"], "测试职位")
            self.assertEqual(len(call("admin_review_messages", token=admin)["messages"]), 2)
            self.assertEqual(len(call("admin_review_messages", token=admin, user_id=3)["messages"]), 1)
            call("admin_moderate_message", token=admin, message_id=1, is_blocked=True, reason="review reason")
            for token, partner in ((alice, 3), (bob, 2)):
                rows = call("conversation", token=token, user_id=partner)["messages"]
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0]["is_blocked"])
                self.assertNotIn("original-private-text", json.dumps(rows))
            reviewed = call("admin_review_messages", token=admin)["messages"][0]
            self.assertEqual(reviewed["body"], "original-private-text")
            self.assertEqual(reviewed["moderator_username"], "admin")
            self.assertEqual(reviewed["reason"], "review reason")
            call("admin_moderate_message", token=admin, message_id=1, is_blocked=False, reason="restored")
            self.assertEqual(call("conversation", token=bob, user_id=2)["messages"][0]["body"], "original-private-text")
            self.assertEqual(len(call("conversation", token=alice)["messages"]), 1)
            call("admin_moderate_message", token=admin, message_id=2, is_blocked=True, reason="support moderation")
            self.assertNotIn("support-text", json.dumps(call("conversation", token=alice)))
            logs = call("admin_list_operation_logs", token=admin)["logs"]
            self.assertEqual([row["action"] for row in logs], ["update_profile"] + ["admin_moderate_message"] * 3)
            self.assertEqual([row["actor_username"] for row in logs], ["alice"] + ["admin"] * 3)
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM moderation_events")
                self.assertEqual(cursor.fetchone()[0], 3)
                cursor.execute("SELECT action, success, detail FROM operation_logs ORDER BY id")
                self.assertEqual(cursor.fetchall(), [
                    ("update_profile", 1, "更新个人资料"),
                    ("admin_moderate_message", 1, "调整消息屏蔽状态"),
                    ("admin_moderate_message", 1, "调整消息屏蔽状态"),
                    ("admin_moderate_message", 1, "调整消息屏蔽状态"),
                ])
        finally:
            if connection is not None:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SHUTDOWN")
                except mysql.connector.Error:
                    pass
                connection.close()
            if process is not None:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            # Only the unique directory created by this test may be removed.
            if directory.parent == parent and directory.name.startswith("moderation-test-"):
                temporary.cleanup()


if __name__ == "__main__":
    unittest.main()

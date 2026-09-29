from __future__ import annotations

import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest

from cryptography.hazmat.primitives import serialization

from common.client_connection import send_request
from common.config import Settings
from common.protocol import ProtocolError, receive_text, send_text
from common.tls import generate_development_certificate
from server.server import serve


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProtocolTests(unittest.TestCase):
    def test_round_trip_handles_unicode_larger_than_one_recv_chunk(self) -> None:
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        message = "你好，TLS！" * 500
        send_text(left, message, max_message_bytes=16_384)
        self.assertEqual(receive_text(right, max_message_bytes=16_384), message)

    def test_rejects_oversized_declared_message_before_reading_body(self) -> None:
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.sendall(struct.pack("!I", 129))
        with self.assertRaises(ProtocolError):
            receive_text(right, max_message_bytes=128)


class VerifiedTlsIntegrationTests(unittest.TestCase):
    password = "test-password-which-is-long-enough"

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        root = Path(self.temp_directory.name)
        cert_file = root / "server-cert.pem"
        key_file = root / "server-key.pem"
        generate_development_certificate(
            cert_file=cert_file,
            key_file=key_file,
            password=self.password,
            hosts=("127.0.0.1", "localhost"),
            valid_days=7,
        )
        self.settings = Settings(
            host="127.0.0.1",
            port=_free_port(),
            socket_timeout_seconds=1,
            max_connections=2,
            max_message_bytes=4096,
            max_response_bytes=8192,
            cert_file=cert_file,
            key_file=key_file,
            ca_file=cert_file,
            key_password_env="TLS_KEY_PASSWORD",
            server_log_file=root / "server.log",
            client_log_file=root / "client.log",
            database_host="127.0.0.1",
            database_port=3306,
            database_name="test_secure_messenger",
            database_user="test",
            database_password_env="MYSQL_PASSWORD",
            database_connect_timeout_seconds=1,
        )
        self.old_password = os.environ.get(self.settings.key_password_env)
        os.environ[self.settings.key_password_env] = self.password
        self.stop_event = threading.Event()
        self.server_thread = threading.Thread(target=serve, args=(self.settings, self.stop_event), daemon=True)
        self.server_thread.start()
        time.sleep(0.1)

    def tearDown(self) -> None:
        self.stop_event.set()
        self.server_thread.join(timeout=3)
        if self.old_password is None:
            os.environ.pop(self.settings.key_password_env, None)
        else:
            os.environ[self.settings.key_password_env] = self.old_password
        self.assertFalse(self.server_thread.is_alive(), "server did not stop within the timeout")

    def test_verified_client_round_trip_and_bad_tls_peer_do_not_stop_server(self) -> None:
        self.assertEqual(send_request(self.settings, "你好"), "你好")

        with socket.create_connection((self.settings.host, self.settings.port), timeout=1) as malformed_peer:
            malformed_peer.sendall(b"not a TLS handshake")
        time.sleep(0.1)

        self.assertEqual(send_request(self.settings, "稳定性测试"), "稳定性测试")
        self.assertIn("稳定性测试", self.settings.server_log_file.read_text(encoding="utf-8"))
        self.assertIn("稳定性测试", self.settings.client_log_file.read_text(encoding="utf-8"))

    def test_private_key_is_encrypted(self) -> None:
        with self.assertRaises(TypeError):
            serialization.load_pem_private_key(self.settings.key_file.read_bytes(), password=None)


if __name__ == "__main__":
    unittest.main()

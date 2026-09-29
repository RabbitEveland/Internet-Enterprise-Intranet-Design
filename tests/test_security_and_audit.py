from __future__ import annotations

import unittest

from common.audit import render_for_log
from server.security import hash_password, validate_username, verify_password


class PasswordAndAuditTests(unittest.TestCase):
    def test_scrypt_hash_verifies_only_the_original_password(self) -> None:
        encoded = hash_password("correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("wrong password", encoded))
        self.assertNotIn("correct horse battery staple", encoded)

    def test_username_policy(self) -> None:
        self.assertEqual(validate_username("user_01"), "user_01")
        with self.assertRaises(ValueError):
            validate_username("中文用户名")

    def test_logs_keep_message_content_but_redact_credentials_and_tokens(self) -> None:
        rendered = render_for_log('{"action":"login","password":"secret","token":"abc","avatar":{"data":"image-base64"},"body":"保留这条消息"}')
        self.assertIn("保留这条消息", rendered)
        self.assertNotIn("secret", rendered)
        self.assertNotIn('"abc"', rendered)
        self.assertNotIn("image-base64", rendered)


if __name__ == "__main__":
    unittest.main()

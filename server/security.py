"""Password validation and scrypt storage for account credentials."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DERIVED_KEY_LENGTH = 32


class CredentialValidationError(ValueError):
    """Raised for usernames or passwords that do not meet the local policy."""


def validate_username(username: object) -> str:
    if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
        raise CredentialValidationError("用户名只能使用 3–32 位字母、数字或下划线。")
    return username


def validate_password(password: object) -> str:
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise CredentialValidationError("密码长度必须为 8–128 个字符。")
    return password


def hash_password(password: str) -> str:
    password = validate_password(password)
    salt = secrets.token_bytes(16)
    derived_key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DERIVED_KEY_LENGTH,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(derived_key).decode("ascii"),
        )
    )


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, expected_value = encoded_password.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError, TypeError, binascii.Error):
        return False

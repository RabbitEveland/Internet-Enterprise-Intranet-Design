"""Generate encrypted local-development TLS material outside version control."""

from __future__ import annotations

import argparse

from common.config import load_settings
from common.secrets import get_private_key_password
from common.tls import generate_development_certificate


def _read_password(environment_variable: str) -> str:
    return get_private_key_password(environment_variable, confirm=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local self-signed TLS certificate.")
    parser.add_argument("--config", help="Path to the canonical config.ini file.")
    parser.add_argument("--days", type=int, default=365, help="Certificate validity, from 1 to 825 days.")
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        password = _read_password(settings.key_password_env)
        generate_development_certificate(
            cert_file=settings.cert_file,
            key_file=settings.key_file,
            password=password,
            hosts=(settings.host, "localhost", "127.0.0.1"),
            valid_days=args.days,
        )
    except (OSError, ValueError) as exc:
        print(f"Certificate generation failed: {exc}")
        return 1

    print(f"Certificate written to {settings.cert_file}")
    print(f"Encrypted private key written to {settings.key_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

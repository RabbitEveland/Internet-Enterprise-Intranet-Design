"""Configuration loading for the secure echo client and server."""

from __future__ import annotations

from configparser import ConfigParser, Error as ConfigParserError
from dataclasses import dataclass
import os
from pathlib import Path
import sys


# Installed executables live in ``<app>\\client`` / ``<app>\\server`` / ``<app>\\tools``.
# Source runs keep the original repository-relative layout.
PROJECT_ROOT = (
    Path(sys.executable).resolve().parent.parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)


class ConfigurationError(ValueError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    socket_timeout_seconds: float
    max_connections: int
    max_message_bytes: int
    max_response_bytes: int
    cert_file: Path
    key_file: Path
    ca_file: Path
    key_password_env: str
    server_log_file: Path
    client_log_file: Path
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password_env: str
    database_connect_timeout_seconds: int


def _resolve_path(value: str, base_directory: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_directory / path).resolve()


def _require_range(name: str, value: int | float, minimum: int | float, maximum: int | float) -> None:
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}; got {value}.")


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load one canonical config file, optionally selected with APP_CONFIG."""
    selected_path = config_path or os.environ.get("APP_CONFIG") or PROJECT_ROOT / "config.ini"
    path = Path(selected_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"Configuration file was not found: {path}")

    parser = ConfigParser()
    parser.read(path, encoding="utf-8")
    required_sections = {"server", "protocol", "tls", "logging", "database"}
    missing_sections = required_sections.difference(parser.sections())
    if missing_sections:
        raise ConfigurationError(f"Configuration is missing section(s): {', '.join(sorted(missing_sections))}")

    try:
        host = parser.get("server", "host").strip()
        port = parser.getint("server", "port")
        timeout = parser.getfloat("server", "socket_timeout_seconds")
        max_connections = parser.getint("server", "max_connections")
        max_message_bytes = parser.getint("protocol", "max_message_bytes")
        max_response_bytes = parser.getint("protocol", "max_response_bytes")
        cert_file = _resolve_path(parser.get("tls", "cert_file"), path.parent)
        key_file = _resolve_path(parser.get("tls", "key_file"), path.parent)
        ca_file = _resolve_path(parser.get("tls", "ca_file"), path.parent)
        key_password_env = parser.get("tls", "key_password_env").strip()
        server_log_file = _resolve_path(parser.get("logging", "server_log_file"), path.parent)
        client_log_file = _resolve_path(parser.get("logging", "client_log_file"), path.parent)
        database_host = parser.get("database", "host").strip()
        database_port = parser.getint("database", "port")
        database_name = parser.get("database", "database").strip()
        database_user = parser.get("database", "user").strip()
        database_password_env = parser.get("database", "password_env").strip()
        database_connect_timeout_seconds = parser.getint("database", "connect_timeout_seconds")
    except (ConfigParserError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid configuration value in {path}: {exc}") from exc

    if not host:
        raise ConfigurationError("server.host must not be empty.")
    if not key_password_env:
        raise ConfigurationError("tls.key_password_env must not be empty.")
    if not all((database_host, database_name, database_user, database_password_env)):
        raise ConfigurationError("database host, name, user, and password_env must not be empty.")
    _require_range("server.port", port, 1, 65535)
    _require_range("server.socket_timeout_seconds", timeout, 0.1, 300)
    _require_range("server.max_connections", max_connections, 1, 256)
    _require_range("protocol.max_message_bytes", max_message_bytes, 1, 16 * 1024 * 1024)
    _require_range("protocol.max_response_bytes", max_response_bytes, 1, 16 * 1024 * 1024)
    _require_range("database.port", database_port, 1, 65535)
    _require_range("database.connect_timeout_seconds", database_connect_timeout_seconds, 1, 120)

    return Settings(
        host=host,
        port=port,
        socket_timeout_seconds=timeout,
        max_connections=max_connections,
        max_message_bytes=max_message_bytes,
        max_response_bytes=max_response_bytes,
        cert_file=cert_file,
        key_file=key_file,
        ca_file=ca_file,
        key_password_env=key_password_env,
        server_log_file=server_log_file,
        client_log_file=client_log_file,
        database_host=database_host,
        database_port=database_port,
        database_name=database_name,
        database_user=database_user,
        database_password_env=database_password_env,
        database_connect_timeout_seconds=database_connect_timeout_seconds,
    )

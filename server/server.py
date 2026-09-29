"""Bounded-concurrency TLS server for the MySQL-backed messaging application."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
import socket
import ssl
import sys
import threading

# PyCharm's existing configuration runs this file directly. Put the project
# root ahead of this file's directory so ``server.application`` resolves to
# the package instead of mistaking this entrypoint for a top-level module.
if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root in sys.path:
        sys.path.remove(project_root)
    sys.path.insert(0, project_root)

from common.audit import render_for_log
from common.config import Settings, load_settings
from common.logger import close_logger, setup_logger
from common.protocol import ProtocolError, receive_text, send_text
from common.secrets import get_database_password, get_new_account_password, get_text_input
from common.tls import TLSConfigurationError, create_server_context
from server.database import RepositoryError


RequestHandler = Callable[[str], str]


def _handle_connection(
    raw_socket: socket.socket,
    address: tuple[str, int],
    context: ssl.SSLContext,
    settings: Settings,
    logger: logging.Logger,
    slots: threading.BoundedSemaphore,
    request_handler: RequestHandler,
) -> None:
    try:
        with raw_socket:
            raw_socket.settimeout(settings.socket_timeout_seconds)
            with context.wrap_socket(raw_socket, server_side=True) as tls_socket:
                request = receive_text(tls_socket, settings.max_message_bytes)
                logger.info("Received request from %s:%s: %s", address[0], address[1], render_for_log(request))
                response = request_handler(request)
                if not isinstance(response, str):
                    raise ProtocolError("Request handler returned a non-text response.")
                send_text(tls_socket, response, settings.max_response_bytes)
                logger.info("Sent response to %s:%s: %s", address[0], address[1], render_for_log(response))
    except socket.timeout:
        logger.warning("Connection from %s:%s timed out.", address[0], address[1])
    except ssl.SSLError as exc:
        logger.warning("TLS handshake/request failed from %s:%s: %s", address[0], address[1], exc)
    except (OSError, ProtocolError) as exc:
        logger.warning("Request failed from %s:%s: %s", address[0], address[1], exc)
    finally:
        slots.release()


def serve(
    settings: Settings,
    stop_event: threading.Event | None = None,
    request_handler: RequestHandler | None = None,
) -> None:
    """Run the TLS listener until interrupted or an optional stop event is set."""
    context = create_server_context(settings)
    logger = setup_logger("secure_messenger_server", settings.server_log_file)
    slots = threading.BoundedSemaphore(settings.max_connections)
    request_handler = request_handler or (lambda request: request)

    try:
        with ThreadPoolExecutor(max_workers=settings.max_connections, thread_name_prefix="tls-client") as executor:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((settings.host, settings.port))
                server_socket.listen(settings.max_connections)
                server_socket.settimeout(0.5)
                logger.info("Server listening on %s:%s.", settings.host, settings.port)

                while stop_event is None or not stop_event.is_set():
                    try:
                        client_socket, address = server_socket.accept()
                    except socket.timeout:
                        continue
                    except OSError as exc:
                        logger.error("Accept failed: %s", exc)
                        continue

                    if not slots.acquire(blocking=False):
                        logger.warning("Connection limit reached; rejecting %s:%s.", address[0], address[1])
                        client_socket.close()
                        continue
                    executor.submit(
                        _handle_connection,
                        client_socket,
                        address,
                        context,
                        settings,
                        logger,
                        slots,
                        request_handler,
                    )
    finally:
        close_logger(logger)


def _initialize_application(settings: Settings) -> RequestHandler:
    """Connect MySQL, create tables, and create the one required initial administrator."""
    from server.application import SecureMessengerApplication
    from server.database import MySQLRepository
    from server.security import hash_password, validate_username

    database_password = get_database_password(settings.database_password_env)
    repository = MySQLRepository(settings, database_password)
    repository.initialize()
    if not repository.has_admin():
        username = validate_username(get_text_input("创建初始管理员", "管理员用户名（3–32 位字母、数字或下划线）"))
        password = get_new_account_password("初始管理员密码")
        repository.create_user(username, hash_password(password), "admin")
    return SecureMessengerApplication(repository).handle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the verified TLS/MySQL messaging server.")
    parser.add_argument("--config", help="Path to the canonical config.ini file.")
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        request_handler = _initialize_application(settings)
        serve(settings, request_handler=request_handler)
    except KeyboardInterrupt:
        return 0
    except (OSError, TLSConfigurationError, ValueError, RuntimeError, RepositoryError) as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")
        logging.error("Server did not start: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

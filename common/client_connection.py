"""Verified TLS request helper shared by the GUI and CLI clients."""

from __future__ import annotations

import socket

from common.audit import render_for_log
from common.config import Settings
from common.logger import close_logger, setup_logger
from common.protocol import receive_text, send_text
from common.tls import create_client_context


def send_request(settings: Settings, message: str) -> str:
    """Send one framed message through a verified TLS connection."""
    logger = setup_logger("secure_echo_client", settings.client_log_file)
    try:
        context = create_client_context(settings)
        with socket.create_connection((settings.host, settings.port), timeout=settings.socket_timeout_seconds) as raw_socket:
            raw_socket.settimeout(settings.socket_timeout_seconds)
            with context.wrap_socket(raw_socket, server_hostname=settings.host) as tls_socket:
                logger.info("Sending request to %s:%s: %s", settings.host, settings.port, render_for_log(message))
                send_text(tls_socket, message, settings.max_message_bytes)
                response = receive_text(tls_socket, settings.max_response_bytes)
                logger.info("Received response from %s:%s: %s", settings.host, settings.port, render_for_log(response))
                return response
    except Exception as exc:
        logger.error("Request to %s:%s failed: %s", settings.host, settings.port, exc)
        raise
    finally:
        close_logger(logger)

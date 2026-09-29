"""A small length-prefixed UTF-8 protocol for one request and one response."""

from __future__ import annotations

import socket
import struct


HEADER_SIZE = 4


class ProtocolError(ValueError):
    """Raised for invalid, incomplete, or oversized protocol messages."""


def _receive_exact(sock: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ProtocolError("Connection closed before a complete message was received.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_text(sock: socket.socket, message: str, max_message_bytes: int) -> None:
    if not isinstance(message, str):
        raise ProtocolError("Messages must be text.")
    payload = message.encode("utf-8")
    if not payload:
        raise ProtocolError("Messages must not be empty.")
    if len(payload) > max_message_bytes:
        raise ProtocolError(f"Message is {len(payload)} bytes; maximum is {max_message_bytes} bytes.")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def receive_text(sock: socket.socket, max_message_bytes: int) -> str:
    declared_size = struct.unpack("!I", _receive_exact(sock, HEADER_SIZE))[0]
    if declared_size == 0:
        raise ProtocolError("Messages must not be empty.")
    if declared_size > max_message_bytes:
        raise ProtocolError(f"Peer declared {declared_size} bytes; maximum is {max_message_bytes} bytes.")
    payload = _receive_exact(sock, declared_size)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("Message payload is not valid UTF-8.") from exc

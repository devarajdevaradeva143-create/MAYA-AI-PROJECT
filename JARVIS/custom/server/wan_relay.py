"""WAN remote transport skeleton (relay + TLS).

Design: `docs/WAN-REMOTE-DESIGN.md`. This module defines the client/server
interfaces and a length-prefixed framing codec. It is intentionally a
compilable skeleton — the relay endpoint and NAT traversal are not deployed.

Message framing (4-byte big-endian length + payload)::

    +----------------+----------------+
    | length (uint32)| payload bytes  |
    +----------------+----------------+
"""

from __future__ import annotations

import socket
import struct
import threading

LENGTH_PREFIX = 4
MAX_FRAME_BYTES = 16 * 1024 * 1024
_MAGIC = b"MYWN"


def encode_frame(payload: bytes) -> bytes:
    """Wrap ``payload`` with the 4-byte length prefix + magic."""
    if len(payload) > MAX_FRAME_BYTES:
        raise ValueError("frame exceeds maximum size")
    return _MAGIC + struct.pack(">I", len(payload)) + payload


def decode_frame(buffer: bytes) -> tuple[bytes, bytes] | None:
    """Return ``(payload, remainder)`` or ``None`` when more bytes are needed."""
    if len(buffer) < LENGTH_PREFIX + len(_MAGIC):
        return None
    if buffer[: len(_MAGIC)] != _MAGIC:
        raise ValueError("bad frame magic")
    length = struct.unpack(">I", buffer[len(_MAGIC) : LENGTH_PREFIX + len(_MAGIC)])[0]
    if length > MAX_FRAME_BYTES:
        raise ValueError("frame length too large")
    total = LENGTH_PREFIX + len(_MAGIC) + length
    if len(buffer) < total:
        return None
    return buffer[LENGTH_PREFIX + len(_MAGIC) : total], buffer[total:]


class RelayClient:
    """Skeleton client that frames messages over an existing socket."""

    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        # Bytes read from the socket but not yet consumed by receive(). A
        # single recv() can contain several frames (or a partial frame), so the
        # remainder must survive across calls instead of being discarded.
        self._buffer = b""

    def connect(self, relay_url: str, token: str) -> bool:
        """Connect to ``relay_url`` (``host:port``) and authenticate with ``token``."""
        host, port = _split_host_port(relay_url)
        self._buffer = b""
        try:
            self._sock = socket.create_connection((host, port), timeout=10)
        except OSError:
            return False
        # Skeleton: token is sent as a one-line handshake.
        try:
            self._sock.sendall(encode_frame(b"AUTH " + token.encode("utf-8")))
        except OSError:
            return False
        return True

    def send(self, message: bytes) -> bool:
        if self._sock is None:
            return False
        try:
            with self._lock:
                self._sock.sendall(encode_frame(message))
            return True
        except OSError:
            return False

    def receive(self) -> bytes | None:
        if self._sock is None:
            return None
        try:
            while True:
                frame = decode_frame(self._buffer)
                if frame is not None:
                    payload, self._buffer = frame
                    return payload
                chunk = self._sock.recv(65536)
                if not chunk:
                    return None
                self._buffer += chunk
        except (OSError, ValueError):
            return None

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._buffer = b""

    def is_connected(self) -> bool:
        return self._sock is not None


def _split_host_port(relay_url: str) -> tuple[str, int]:
    """Parse ``host:port`` (or ``ws://host:port``) into host and port."""
    text = relay_url.strip()
    for scheme in ("wss://", "ws://", "https://", "http://"):
        if text.startswith(scheme):
            text = text[len(scheme) :]
            break
    if "/" in text:
        text = text.split("/", 1)[0]
    if ":" in text:
        host, port_text = text.rsplit(":", 1)
        try:
            return host, int(port_text)
        except ValueError:
            return text, 443
    return text, 443


class RelayServer:
    """Skeleton relay server (length-framed pass-through).

    Not deployed; provided so the design can be exercised locally.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9443) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._running = False

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self._running = True

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass


__all__ = ["RelayClient", "RelayServer", "decode_frame", "encode_frame"]

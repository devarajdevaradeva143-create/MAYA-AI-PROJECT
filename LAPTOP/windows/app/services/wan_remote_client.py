"""WAN Remote Client for laptop (Windows) - connects to relay server via WSS."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import websockets

logger = logging.getLogger("maya.wan_remote")


@dataclass
class WanSession:
    session_id: str
    phone_device_id: str
    connected_at: float


class WanRemoteClient:
    """Client for laptop to connect to phone via relay server (WAN)."""

    def __init__(
        self,
        relay_url: str,
        cert_path: str,
        key_path: str,
        pairing_token: str,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_phone_frame: Callable[[bytes], None] | None = None,
        on_phone_input: Callable[[list], None] | None = None,
    ) -> None:
        self.relay_url = relay_url
        self.cert_path = cert_path
        self.key_path = key_path
        self.pairing_token = pairing_token
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._on_phone_frame = on_phone_frame
        self._on_phone_input = on_phone_input

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_ws = threading.Event()
        self._session: WanSession | None = None
        self._ssl_context: ssl.SSLContext | None = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    def _build_ssl_context(self) -> ssl.SSLContext:
        """Build SSL context with client cert + key."""
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(self.cert_path, self.key_path)
        # For self-signed relay, disable hostname verification
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def connect(self) -> bool:
        """Connect to relay server via WSS."""
        try:
            self._ssl_context = self._build_ssl_context()
            self._stop_ws.clear()
            self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
            self._ws_thread.start()
            return True
        except Exception as e:
            logger.error("WAN connect failed: %s", e)
            self._on_error and self._on_error(str(e))
            return False

    def _ws_loop(self) -> None:
        """WebSocket loop in background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_connect())
        except Exception as e:
            logger.error("WAN WS loop error: %s", e)
            self._on_error and self._on_error(str(e))
        finally:
            loop.close()

    async def _ws_connect(self) -> None:
        """Connect to relay and handle messages."""
        url = f"{self.relay_url}/wan/laptop?token={self.pairing_token}"

        try:
            async with websockets.connect(
                url,
                ssl=self._ssl_context,
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                self._ws = ws
                logger.info("WAN connected to relay: %s", self.relay_url)
                self._on_connected and self._on_connected()

                # Register as laptop
                await ws.send(json.dumps({
                    "type": "register",
                    "role": "laptop",
                    "capabilities": ["phone_remote", "chat", "monitor", "pc_control"]
                }))

                async for msg in ws:
                    if self._stop_ws.is_set():
                        break

                    if isinstance(msg, bytes):
                        # Binary screen frame from phone
                        self._on_phone_frame and self._on_phone_frame(msg)
                    elif isinstance(msg, str):
                        # JSON message
                        try:
                            data = json.loads(msg)
                            await self._handle_message(data)
                        except json.JSONDecodeError:
                            pass

        except websockets.ConnectionClosed:
            logger.info("WAN connection closed")
        except Exception as e:
            logger.error("WAN connection error: %s", e)
            self._on_error and self._on_error(str(e))
        finally:
            self._ws = None
            self._on_disconnected and self._on_disconnected()

    async def _handle_message(self, data: dict) -> None:
        """Handle incoming JSON message from relay."""
        msg_type = data.get("type")

        if msg_type == "registered":
            self._session = WanSession(
                session_id=data.get("wan_id", ""),
                phone_device_id=data.get("phone_id", ""),
                connected_at=time.time(),
            )
            logger.info("WAN session registered: %s", self._session.session_id)

        elif msg_type == "screen":
            # Screen frame forwarded from phone (base64)
            import base64
            frame_b64 = data.get("data", "")
            try:
                frame_bytes = base64.b64decode(frame_b64)
                self._on_phone_frame and self._on_phone_frame(frame_bytes)
            except Exception as e:
                logger.warning("Failed to decode screen frame: %s", e)

        elif msg_type == "input":
            # Input events from laptop UI → forward to phone
            events = data.get("events", [])
            self._on_phone_input and self._on_phone_input(events)

        elif msg_type == "error":
            self._on_error and self._on_error(data.get("message", "Unknown error"))

        elif msg_type == "pong":
            pass  # Keep-alive

    def send_input(self, events: list[dict]) -> None:
        """Send input events to phone via relay."""
        if not self._ws:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(json.dumps({"type": "input", "events": events})),
                self._ws.loop if hasattr(self._ws, 'loop') else asyncio.get_event_loop()
            )
        except Exception as e:
            logger.warning("WAN send failed: %s", e)

    def send_ping(self) -> None:
        """Send ping to keep connection alive."""
        if not self._ws:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(json.dumps({"type": "ping"})),
                self._ws.loop if hasattr(self._ws, 'loop') else asyncio.get_event_loop()
            )
        except Exception:
            pass

    def disconnect(self) -> None:
        """Disconnect from relay."""
        self._stop_ws.set()
        if self._ws:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._ws.close(),
                    self._ws.loop if hasattr(self._ws, 'loop') else asyncio.get_event_loop()
                )
            except Exception:
                pass
        if self._ws_thread:
            self._ws_thread.join(timeout=2)
        self._ws = None
        self._session = None


# Singleton
_wan_client: WanRemoteClient | None = None
_client_lock = threading.Lock()


def get_wan_client(
    relay_url: str,
    cert_path: str,
    key_path: str,
    pairing_token: str,
    on_connected: Callable[[], None] | None = None,
    on_disconnected: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_phone_frame: Callable[[bytes], None] | None = None,
    on_phone_input: Callable[[list], None] | None = None,
) -> WanRemoteClient:
    global _wan_client
    with _client_lock:
        if _wan_client is None:
            _wan_client = WanRemoteClient(
                relay_url, cert_path, key_path, pairing_token,
                on_connected, on_disconnected, on_error,
                on_phone_frame, on_phone_input
            )
        return _wan_client


def reset_wan_client() -> None:
    global _wan_client
    with _client_lock:
        if _wan_client:
            _wan_client.disconnect()
        _wan_client = None
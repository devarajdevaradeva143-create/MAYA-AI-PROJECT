"""Phone Remote Client: WebSocket screen stream + HTTP input/files for laptop ↔ phone control."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import requests
import websockets
from websockets.client import WebSocketClientProtocol

from app.services.server_service import shared_server_service

logger = logging.getLogger("maya.phone_remote")


@dataclass
class PhoneRemoteSession:
    session_token: str
    ws_url: str
    expires_at: float
    screen_width: int
    screen_height: int
    density: float


class PhoneRemoteClient:
    """Client for controlling a paired phone from the laptop."""

    def __init__(
        self,
        on_frame: Callable[[bytes], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_status: Callable[[dict], None] | None = None,
    ) -> None:
        self._on_frame = on_frame
        self._on_error = on_error
        self._on_status = on_status
        self._session: PhoneRemoteSession | None = None
        self._ws: WebSocketClientProtocol | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_ws = threading.Event()
        self._phone_base_url: str | None = None

    @property
    def is_active(self) -> bool:
        return self._session is not None and time.time() < self._session.expires_at

    @property
    def session(self) -> PhoneRemoteSession | None:
        return self._session

    def _get_phone_url(self, host: str, port: int = 8421) -> str:
        return f"http://{host}:{port}"

    def _get_paired_phone_ip(self) -> str | None:
        """Get the IP of the currently paired phone from the laptop server."""
        service = shared_server_service()
        if not service.running:
            return None
        tokens = service.app.state.tokens
        devices = tokens.list_active()
        for d in devices:
            if d.last_seen > 0:
                return d.host if hasattr(d, 'host') else None
        return None

    def start_session(
        self,
        phone_host: str,
        max_width: int = 1280,
        quality: int = 60,
        fps: int = 10,
    ) -> dict:
        """Start a remote session on the phone. Returns confirm_token for user approval."""
        url = f"{self._get_phone_url(phone_host)}/phone/remote/start"
        payload = {"max_width": max_width, "quality": quality, "fps": fps}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("confirm_token"):
                return {"status": "needs_confirmation", "confirm_token": data["confirm_token"]}
            elif resp.status_code == 200 and data.get("session_token"):
                self._session = PhoneRemoteSession(
                    session_token=data["session_token"],
                    ws_url=data["ws_url"],
                    expires_at=time.time() + data["expires_in"],
                    screen_width=data["screen"]["width"],
                    screen_height=data["screen"]["height"],
                    density=data["screen"]["density"],
                )
                self._phone_base_url = self._get_phone_url(phone_host)
                self._start_ws()
                return {"status": "started", **data}
            else:
                raise RuntimeError(data.get("detail", f"HTTP {resp.status_code}"))
        except Exception as e:
            logger.error("Failed to start phone remote session: %s", e)
            raise

    def confirm_session(self, phone_host: str, confirm_token: str) -> dict:
        """Confirm the session on phone (user tapped Allow)."""
        url = f"{self._get_phone_url(phone_host)}/phone/remote/confirm"
        payload = {"confirm_token": confirm_token}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("session_token"):
                self._session = PhoneRemoteSession(
                    session_token=data["session_token"],
                    ws_url=data["ws_url"],
                    expires_at=time.time() + data["expires_in"],
                    screen_width=data["screen"]["width"],
                    screen_height=data["screen"]["height"],
                    density=data["screen"]["density"],
                )
                self._phone_base_url = self._get_phone_url(phone_host)
                self._start_ws()
                return {"status": "started", **data}
            raise RuntimeError(data.get("detail", f"HTTP {resp.status_code}"))
        except Exception as e:
            logger.error("Failed to confirm phone remote session: %s", e)
            raise

    def stop_session(self) -> None:
        """Stop the remote session."""
        if not self._session or not self._phone_base_url:
            return

        url = f"{self._phone_base_url}/phone/remote/stop"
        try:
            requests.post(
                url,
                json={"session_token": self._session.session_token},
                timeout=5,
            )
        except Exception as e:
            logger.warning("Stop session request failed: %s", e)
        finally:
            self._stop_ws.set()
            if self._ws_thread:
                self._ws_thread.join(timeout=2)
            self._session = None
            self._phone_base_url = None

    def send_input(self, events: list[dict]) -> int:
        """Send input events to phone."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/input"
        payload = {"session_token": self._session.session_token, "events": events}

        try:
            resp = requests.post(url, json=payload, timeout=5)
            data = resp.json()
            return data.get("applied", 0)
        except Exception as e:
            logger.error("Failed to send input: %s", e)
            raise

    def list_files(self, path: str) -> dict:
        """List files in phone's allowed root."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/list"
        payload = {"session_token": self._session.session_token, "path": path}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error("Failed to list files: %s", e)
            raise

    def download_file(self, path: str, dest_path: str) -> None:
        """Download a file from phone."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/download"
        params = {"session_token": self._session.session_token, "path": path}

        try:
            resp = requests.get(url, params=params, stream=True, timeout=30)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            logger.error("Failed to download file: %s", e)
            raise

    def upload_file(self, local_path: str, remote_path: str) -> dict:
        """Upload a file to phone (placeholder - phone returns 501)."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/upload"
        with open(local_path, "rb") as f:
            files = {"file": (local_path, f, "application/octet-stream")}
            data = {"session_token": self._session.session_token, "path": remote_path}
            try:
                resp = requests.post(url, files=files, data=data, timeout=30)
                return resp.json()
            except Exception as e:
                logger.error("Failed to upload file: %s", e)
                raise

    def _start_ws(self) -> None:
        """Start WebSocket connection for screen stream."""
        if not self._session:
            return

        self._stop_ws.clear()
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def _ws_loop(self) -> None:
        """WebSocket loop in background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ws_connect())
        except Exception as e:
            logger.error("WS loop error: %s", e)
            self._on_error and self._on_error(str(e))
        finally:
            loop.close()

    async def _ws_connect(self) -> None:
        """Connect to WebSocket and receive frames."""
        ws_url = self._session.ws_url if self._session else ""
        if not ws_url:
            return

        try:
            async with websockets.connect(ws_url) as ws:
                self._ws = ws
                logger.info("Phone remote WS connected: %s", ws_url)

                while not self._stop_ws.is_set() and self.is_active:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        if isinstance(msg, bytes):
                            # Binary JPEG frame
                            self._on_frame and self._on_frame(msg)
                        elif isinstance(msg, str):
                            # JSON message
                            try:
                                data = json.loads(msg)
                                if data.get("type") == "screen_info":
                                    if self._session:
                                        self._session.screen_width = data.get("width", self._session.screen_width)
                                        self._session.screen_height = data.get("height", self._session.screen_height)
                                        self._session.density = data.get("density", self._session.density)
                                elif data.get("type") == "error":
                                    self._on_error and self._on_error(data.get("message", "Phone error"))
                            except json.JSONDecodeError:
                                pass
                    except TimeoutError:
                        # Send ping
                        await ws.send(json.dumps({"type": "ping"}))
                    except websockets.ConnectionClosed:
                        break
        except Exception as e:
            logger.error("WS connection failed: %s", e)
            self._on_error and self._on_error(str(e))
        finally:
            self._ws = None

    def send_ws_input(self, events: list[dict]) -> None:
        """Send input via WebSocket (lower latency than HTTP)."""
        if not self._ws:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._ws.send(json.dumps({"type": "input", "events": events})),
                self._ws.loop if hasattr(self._ws, 'loop') else asyncio.get_event_loop()
            )
        except Exception as e:
            logger.warning("WS send failed, falling back to HTTP: %s", e)
            self.send_input(events)


# Singleton instance
_phone_remote_client: PhoneRemoteClient | None = None
_client_lock = threading.Lock()


def get_phone_remote_client(
    on_frame: Callable[[bytes], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_status: Callable[[dict], None] | None = None,
) -> PhoneRemoteClient:
    """Get or create the singleton PhoneRemoteClient."""
    global _phone_remote_client
    with _client_lock:
        if _phone_remote_client is None:
            _phone_remote_client = PhoneRemoteClient(on_frame, on_error, on_status)
        else:
            # Update callbacks
            if on_frame:
                _phone_remote_client._on_frame = on_frame
            if on_error:
                _phone_remote_client._on_error = on_error
            if on_status:
                _phone_remote_client._on_status = on_status
        return _phone_remote_client


def reset_phone_remote_client() -> None:
    """Reset the singleton (e.g., on settings change)."""
    global _phone_remote_client
    with _client_lock:
        if _phone_remote_client:
            _phone_remote_client.stop_session()
        _phone_remote_client = None
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
from websockets.asyncio.client import ClientConnection

from app.services.server_service import shared_server_service

logger = logging.getLogger("maya.phone_remote")

# Keep urllib3 from spamming retry chatter into the logs; the friendly
# messages below are what callers actually want to see.
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


def _describe_remote_error(exc: Exception, host: str | None = None) -> str:
    """Short, actionable text for phone-side network failures.

    urllib3 renders a connection failure as a paragraph of retry chatter, which
    is useless in the status label / logs. Collapse it into one sentence.
    """
    target = f"http://{host}:8421" if host else "the phone"

    is_conn = False
    is_timeout = False

    # Type-based detection.
    try:
        import requests

        if isinstance(exc, requests.exceptions.ConnectionError):
            is_conn = True
        if isinstance(exc, requests.exceptions.Timeout):
            is_timeout = True
    except Exception:  # pragma: no cover - requests always present
        pass
    try:
        import urllib3

        if isinstance(exc, getattr(urllib3.exceptions, "MaxRetryError", ())):
            is_conn = True
        if isinstance(exc, getattr(urllib3.exceptions, "NewConnectionError", ())):
            is_conn = True
        if isinstance(exc, getattr(urllib3.exceptions, "ConnectTimeoutError", ())):
            is_timeout = True
        if isinstance(exc, getattr(urllib3.exceptions, "ReadTimeoutError", ())):
            is_timeout = True
    except Exception:  # pragma: no cover
        pass

    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, BrokenPipeError)):
        is_conn = True
    if isinstance(exc, TimeoutError):
        is_timeout = True

    # String-based fallback for wrapped / unknown exception types.
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        is_timeout = is_timeout or not is_conn
    if (
        "refused" in text
        or "retries exceeded" in text
        or "newconnectionerror" in text
        or "failed to establish" in text
        or "name or service not known" in text
        or "no route to host" in text
    ):
        is_conn = True

    if is_conn:
        return (
            f"No answer from {target} - open the Maya app on the phone and enable "
            "Accessibility + Phone Remote."
        )
    if is_timeout:
        return f"Phone timed out at {target} - check both devices are on the same Wi-Fi."
    return str(exc)


# Back-compat alias used by some callers / tests.
describe_remote_error = _describe_remote_error

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
        self._ws: ClientConnection | None = None
        self._ws_thread: threading.Thread | None = None
        self._stop_ws = threading.Event()
        self._phone_base_url: str | None = None
        self._phone_host: str | None = None

    @property
    def is_active(self) -> bool:
        return self._session is not None and time.time() < self._session.expires_at

    @property
    def session(self) -> PhoneRemoteSession | None:
        return self._session

    def _get_phone_url(self, host: str, port: int = 8421) -> str:
        return f"http://{host}:{port}"

    def _get_paired_phone_ip(self) -> str | None:
        """Get the last known LAN IP of the most recently seen paired phone."""
        service = shared_server_service()
        if not service.running:
            return None
        tokens = service.app.state.tokens
        devices = sorted(
            tokens.list_active(),
            key=lambda d: getattr(d, "last_seen", 0) or 0,
            reverse=True,
        )
        for d in devices:
            ip = (getattr(d, "last_ip", "") or "").strip()
            if ip:
                return ip
        return None

    def _get_auth_headers(self) -> dict[str, str]:
        # Best-effort: use server-side paired device token is not exposed to Windows UI.
        # The phone server accepts Bearer token of any paired device; Windows client can
        # provide it via env/config later. For now, try to reuse server app state token if present.
        try:
            service = shared_server_service()
            if service.running:
                tokens = service.app.state.tokens.list_active()
                if tokens:
                    # TokenRegistry stores token hashes, not raw tokens. Cannot send raw token.
                    pass
        except Exception:
            pass
        token = getattr(self, "_auth_token", None) or ""
        return {"Authorization": f"Bearer {token}"} if token else {}

    def set_auth_token(self, token: str | None) -> None:
        self._auth_token = (token or "").strip() or None

    def start_session(
        self,
        phone_host: str,
        max_width: int = 1280,
        quality: int = 60,
        fps: int = 10,
    ) -> dict:
        """Start a remote session on the phone. Returns pending request id."""
        url = f"{self._get_phone_url(phone_host)}/phone/remote/start"
        payload = {"max_width": max_width, "quality": quality, "fps": fps}
        try:
            resp = requests.post(url, json=payload, headers=self._get_auth_headers(), timeout=10)
        except Exception as e:  # noqa: BLE001 - convert to a clean error
            raise RuntimeError(_describe_remote_error(e, phone_host)) from e
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and data.get("status") == "pending":
            return {"status": "pending", "request_id": data.get("request_id"), "expires_in": data.get("expires_in", 60)}
        if resp.status_code == 200 and data.get("status") == "needs_confirmation":
            # Back-compat with old phone server
            return {"status": "pending", "request_id": data.get("confirm_token"), "expires_in": data.get("expires_in", 30), "legacy": True}
        if resp.status_code == 200 and data.get("session_token"):
            self._set_session(phone_host, data)
            return {"status": "started", **data}
        raise RuntimeError(data.get("description") or data.get("detail") or f"HTTP {resp.status_code}")

    def get_request_status(self, phone_host: str, request_id: str) -> dict:
        url = f"{self._get_phone_url(phone_host)}/phone/remote/request/{request_id}"
        try:
            resp = requests.get(url, headers=self._get_auth_headers(), timeout=10)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(_describe_remote_error(e, phone_host)) from e
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(data.get("description") or f"HTTP {resp.status_code}")
        if data.get("status") == "started" and data.get("session_token"):
            self._set_session(phone_host, data)
        return data

    def _set_session(self, phone_host: str, data: dict) -> None:
        self._session = PhoneRemoteSession(
            session_token=data["session_token"],
            ws_url=data["ws_url"],
            expires_at=time.time() + int(data.get("expires_in", 300)),
            screen_width=data.get("screen", {}).get("width", 1080),
            screen_height=data.get("screen", {}).get("height", 1920),
            density=data.get("screen", {}).get("density", 420),
        )
        self._phone_base_url = self._get_phone_url(phone_host)
        self._phone_host = phone_host
        self._start_ws()

    def confirm_session(self, phone_host: str, confirm_token: str) -> dict:
        """Back-compat: older flow polled confirm endpoint."""
        data = self.get_request_status(phone_host, confirm_token)
        if data.get("status") == "started":
            return data
        if data.get("status") in {"pending"}:
            return data
        raise RuntimeError(data.get("description") or data.get("status") or "Confirmation failed")

    def stop_session(self) -> None:
        """Stop the remote session."""
        if not self._session or not self._phone_base_url:
            return

        url = f"{self._phone_base_url}/phone/remote/stop"
        try:
            requests.post(
                url,
                json={"session_token": self._session.session_token},
                headers=self._get_auth_headers(),
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
            resp = requests.post(url, json=payload, headers=self._get_auth_headers(), timeout=5)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(_describe_remote_error(e, self._phone_host)) from e
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(data.get("description") or f"HTTP {resp.status_code}")
        return data.get("applied", 0)

    def list_files(self, path: str) -> dict:
        """List files in phone's allowed root."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/list"
        payload = {"session_token": self._session.session_token, "path": path}

        try:
            resp = requests.post(url, json=payload, headers=self._get_auth_headers(), timeout=10)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(_describe_remote_error(e, self._phone_host)) from e
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(data.get("description") or f"HTTP {resp.status_code}")
        return data

    def download_file(self, path: str, dest_path: str) -> None:
        """Download a file from phone."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/download"
        params = {"session_token": self._session.session_token, "path": path}

        try:
            resp = requests.get(url, params=params, headers=self._get_auth_headers(), stream=True, timeout=30)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(_describe_remote_error(e, self._phone_host)) from e
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    def upload_file(self, local_path: str, remote_path: str) -> dict:
        """Upload a file to phone (placeholder - phone returns 501)."""
        if not self._session or not self._phone_base_url:
            raise RuntimeError("No active session")

        url = f"{self._phone_base_url}/phone/remote/files/upload"
        with open(local_path, "rb") as f:
            files = {"file": (local_path, f, "application/octet-stream")}
            data = {"session_token": self._session.session_token, "path": remote_path}
            try:
                resp = requests.post(url, files=files, data=data, headers=self._get_auth_headers(), timeout=30)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(_describe_remote_error(e, self._phone_host)) from e
            out = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                raise RuntimeError(out.get("description") or f"HTTP {resp.status_code}")
            return out

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

        headers = self._get_auth_headers()
        try:
            async with websockets.connect(ws_url, additional_headers=headers) as ws:
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
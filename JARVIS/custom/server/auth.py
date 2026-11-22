"""Token auth, hashed token store and sliding-window rate limiting.

Security rules (contract section 16):
- plain tokens never touch disk
- revoked / expired tokens fail immediately
- auth failures are rate limited per client IP
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Request, WebSocket

from custom.server.errors import ApiError

TOKEN_PREFIX = "maya_"
TOKEN_BYTES = 32
LAST_SEEN_THROTTLE_S = 60


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def default_token_path() -> Path:
    override = os.environ.get("MAYA_TOKENS_STORE")
    if override:
        return Path(override).expanduser()
    try:
        from custom.config import PROJECT_ROOT

        root = Path(PROJECT_ROOT)
    except Exception:  # noqa: BLE001 - path fallback only
        root = Path(__file__).resolve().parents[3]
    return root / "MAYA AI" / "memory" / "offline" / "devices" / "api_tokens.json"


@dataclass
class DeviceRecord:
    device_id: str
    name: str
    token_hash: str
    paired_at: int
    last_seen: int
    expires_at: int
    app_version: str = ""
    last_ip: str = ""
    revoked: bool = False
    # Phone stats (additive, optional)
    phone_battery_percent: int | None = None
    phone_storage_used_percent: int | None = None
    phone_ram_used_percent: int | None = None
    phone_uptime_hours: int | None = None
    phone_stats_updated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceRecord:
        return cls(
            device_id=str(data["device_id"]),
            name=str(data.get("name", "")),
            token_hash=str(data.get("token_hash", "")),
            paired_at=int(data.get("paired_at", 0)),
            last_seen=int(data.get("last_seen", 0)),
            expires_at=int(data.get("expires_at", 0)),
            app_version=str(data.get("app_version", "")),
            last_ip=str(data.get("last_ip", "")),
            revoked=bool(data.get("revoked", False)),
            phone_battery_percent=data.get("phone_battery_percent"),
            phone_storage_used_percent=data.get("phone_storage_used_percent"),
            phone_ram_used_percent=data.get("phone_ram_used_percent"),
            phone_uptime_hours=data.get("phone_uptime_hours"),
            phone_stats_updated=int(data.get("phone_stats_updated", 0)),
        )

    def is_expired(self, now: float | None = None) -> bool:
        return self.expires_at <= (now if now is not None else time.time())


class TokenStore:
    """File-backed device/token store. JSON contains SHA-256 hashes only."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_token_path()
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceRecord] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        devices = data.get("devices", {}) if isinstance(data, dict) else {}
        for device_id, raw in devices.items():
            try:
                self._devices[str(device_id)] = DeviceRecord.from_dict(raw)
            except (KeyError, TypeError, ValueError):
                continue

    def _save(self) -> None:
        """Atomic write; never logs the contents."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "devices": {key: record.to_dict() for key, record in self._devices.items()},
        }
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def add(
        self,
        *,
        device_id: str,
        name: str,
        token_hash: str,
        expires_at: int,
        app_version: str = "",
        now: float | None = None,
    ) -> DeviceRecord:
        with self._lock:
            self._load()
            stamp = int(now if now is not None else time.time())
            existing = self._devices.get(device_id)
            record = DeviceRecord(
                device_id=device_id,
                name=name,
                token_hash=token_hash,
                paired_at=existing.paired_at if existing else stamp,
                last_seen=stamp,
                expires_at=expires_at,
                app_version=app_version,
                last_ip=existing.last_ip if existing else "",
                revoked=False,
            )
            self._devices[device_id] = record
            self._save()
            return record

    def find_by_hash(self, token_hash: str) -> DeviceRecord | None:
        with self._lock:
            self._load()
            for record in self._devices.values():
                if record.token_hash and secrets.compare_digest(record.token_hash, token_hash):
                    return record
        return None

    def get(self, device_id: str) -> DeviceRecord | None:
        with self._lock:
            self._load()
            return self._devices.get(device_id)

    def list_active(self) -> list[DeviceRecord]:
        with self._lock:
            self._load()
            return sorted(
                (record for record in self._devices.values() if not record.revoked),
                key=lambda record: record.paired_at,
                reverse=True,
            )

    def count_active(self) -> int:
        return len(self.list_active())

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            self._load()
            record = self._devices.get(device_id)
            if record is None:
                raise ApiError(2004, "Device not found")
            if not record.revoked:
                record.revoked = True
                self._save()
            return True

    def touch(
        self,
        device_id: str,
        now: float | None = None,
        ip: str | None = None,
    ) -> None:
        with self._lock:
            self._load()
            record = self._devices.get(device_id)
            if record is None:
                return
            stamp = int(now if now is not None else time.time())
            ip_changed = bool(ip) and ip != "unknown" and ip != record.last_ip
            if not ip_changed and stamp - record.last_seen < LAST_SEEN_THROTTLE_S:
                return
            record.last_seen = stamp
            if ip_changed:
                # Remember where the paired phone connects from so the
                # laptop can reach the phone's remote server (port 8421).
                record.last_ip = str(ip)
            self._save()

    def update_token(
        self,
        device_id: str,
        token_hash: str,
        expires_at: int,
        now: float | None = None,
    ) -> DeviceRecord:
        with self._lock:
            self._load()
            record = self._devices.get(device_id)
            if record is None:
                raise ApiError(1007, "Device revoked")
            stamp = int(now if now is not None else time.time())
            record.token_hash = token_hash
            record.expires_at = expires_at
            record.last_seen = stamp
            record.revoked = False
            self._save()
            return record

    def update_phone_stats(self, device_id: str, stats: dict) -> None:
        """Store phone-reported stats (battery, storage, RAM, uptime)."""
        with self._lock:
            self._load()
            record = self._devices.get(device_id)
            if record is None:
                return
            stamp = int(time.time())
            record.phone_battery_percent = stats.get("battery_percent")
            record.phone_storage_used_percent = stats.get("storage_used_percent")
            record.phone_ram_used_percent = stats.get("ram_used_percent")
            record.phone_uptime_hours = stats.get("uptime_hours")
            record.phone_stats_updated = stamp
            self._save()


class RateLimiter:
    """In-memory sliding window; one bucket per key."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = self._clock()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                raise ApiError(1005, "Too many requests", 429)
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request | WebSocket) -> str:
    client = request.client
    return client.host if client else "unknown"


def _auth_failure(limiter: RateLimiter, ip: str, code: int, message: str) -> ApiError:
    limiter.hit(f"authfail:{ip}", 10, 60)
    return ApiError(code, message)


def authenticate(
    authorization: str | None,
    *,
    tokens: TokenStore,
    limiter: RateLimiter,
    ip: str,
    now: float | None = None,
) -> DeviceRecord:
    if not authorization:
        raise _auth_failure(limiter, ip, 1001, "Missing token")
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        raise _auth_failure(limiter, ip, 1001, "Invalid token")

    record = tokens.find_by_hash(hash_token(raw.strip()))
    if record is None:
        raise _auth_failure(limiter, ip, 1001, "Invalid token")
    if record.revoked:
        raise _auth_failure(limiter, ip, 1007, "Device revoked")
    if record.is_expired(now):
        raise _auth_failure(limiter, ip, 1006, "Token expired")

    tokens.touch(record.device_id, now, ip=ip)
    return record


def require_device(request: Request) -> DeviceRecord:
    """FastAPI dependency: valid Bearer token + general rate limit."""
    state = request.app.state
    record = authenticate(
        request.headers.get("authorization"),
        tokens=state.tokens,
        limiter=state.limiter,
        ip=client_ip(request),
    )
    state.limiter.hit(f"general:{record.device_id}", 120, 60)
    return record


DeviceDep = Annotated[DeviceRecord, Depends(require_device)]


def authenticate_websocket(websocket: WebSocket) -> DeviceRecord:
    """WS auth accepts `?token=` or the Authorization header."""
    raw = websocket.query_params.get("token")
    authorization = websocket.headers.get("authorization")
    if raw:
        authorization = f"Bearer {raw}"
    return authenticate(
        authorization,
        tokens=websocket.app.state.tokens,
        limiter=websocket.app.state.limiter,
        ip=client_ip(websocket),
    )

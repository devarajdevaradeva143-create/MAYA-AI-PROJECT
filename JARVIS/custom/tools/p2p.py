"""Local-first internet P2P core for Maya AI.

No cloud service, no data retention, no autonomous action. This module owns:

    * a local Ed25519 identity + pairing code (private key never leaves the device)
    * manual offer/answer signaling payloads (QR or copy/paste)
    * a framed data-channel protocol (control/chat/files/screen)
    * an optional WebRTC session backed by ``aiortc``

``aiortc`` is imported lazily. When it is missing, WebRTC methods fail with
``P2PError('aiortc_missing')`` instead of breaking import or silently falling
back to a cloud relay.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from custom.config import PROJECT_ROOT, load_settings

VERSION = 2
INVITE_KIND = "maya-p2p-invite"
OFFER_KIND = "maya-p2p-offer"
ANSWER_KIND = "maya-p2p-answer"
CHANNELS = ("control", "chat", "files", "screen")
MAX_FRAME_BYTES = 16 * 1024 * 1024
ICE_WAIT_SECONDS = 12.0


class P2PError(Exception):
    """P2P failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# -- base64url JSON payloads -------------------------------------------------

def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text:
        raise P2PError("bad_payload", "Payload is empty")
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as exc:
        raise P2PError("bad_payload", "Payload is not valid base64url") from exc


def encode_payload(obj: dict[str, Any]) -> str:
    """Encode a signaling object as compact base64url JSON."""
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _b64u_encode(raw)


def decode_payload(text: str) -> dict[str, Any]:
    """Decode a signaling object. Never raises for malformed input."""
    try:
        obj = json.loads(_b64u_decode(text).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise P2PError("bad_payload", "Payload is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise P2PError("bad_payload", "Payload must be a JSON object")
    return obj


def fingerprint(public_key_b64: str) -> str:
    """Stable 32-hex-char fingerprint of a raw Ed25519 public key."""
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise P2PError("bad_identity", "Public key is invalid") from exc
    return hashlib.sha256(raw).hexdigest()[:32]


# -- local identity + invite -------------------------------------------------

@dataclass(frozen=True)
class Identity:
    device_id: str
    public_key_b64: str
    fingerprint: str
    private_key_b64: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "public_key": self.public_key_b64,
            "fingerprint": self.fingerprint,
            "private_key": self.private_key_b64,
        }


@dataclass(frozen=True)
class Invite:
    device_id: str
    public_key_b64: str
    fingerprint: str
    host: str
    port: int
    code: str
    session_id: str
    expires_at: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": VERSION,
            "kind": INVITE_KIND,
            "did": self.device_id,
            "pub": self.public_key_b64,
            "fp": self.fingerprint,
            "host": self.host,
            "port": self.port,
            "code": self.code,
            "sid": self.session_id,
            "exp": self.expires_at,
        }

    def to_text(self) -> str:
        return encode_payload(self.to_dict())


def encode_invite(invite: Invite) -> str:
    return invite.to_text()


def decode_invite(text: str) -> Invite:
    obj = decode_payload(text)
    if obj.get("v") != VERSION or obj.get("kind") != INVITE_KIND:
        raise P2PError("bad_invite", "Not a Maya P2P invite")
    try:
        pub = str(obj["pub"])
        fp = str(obj["fp"])
        port = int(obj.get("port", 0))
        expires = int(obj["exp"])
        code = str(obj["code"])
    except (KeyError, TypeError, ValueError) as exc:
        raise P2PError("bad_invite", "Invite fields are invalid") from exc
    if fingerprint(pub) != fp:
        raise P2PError("bad_fingerprint", "Invite fingerprint mismatch")
    if expires <= int(time.time()):
        raise P2PError("expired", "Invite expired")
    if not code.isdigit() or len(code) != 6:
        raise P2PError("bad_code", "Invite code must be 6 digits")
    if port < 0 or port > 65535:
        raise P2PError("bad_invite", "Invite port is invalid")
    return Invite(
        device_id=str(obj.get("did", "")),
        public_key_b64=pub,
        fingerprint=fp,
        host=str(obj.get("host", "")),
        port=port,
        code=code,
        session_id=str(obj.get("sid", "")),
        expires_at=expires,
    )


def _identity_path() -> Path:
    memory = load_settings().get("memory", {})
    base = memory.get("offline", "memory/offline") if isinstance(memory, dict) else "memory/offline"
    root = Path(base)
    if not root.is_absolute():
        root = PROJECT_ROOT / "MAYA AI" / root
    return root / "devices" / "p2p_identity.json"


class IdentityStore:
    """Creates and loads the device's local P2P identity."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else _identity_path()

    def _generate(self) -> Identity:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519
        except ImportError as exc:  # pragma: no cover - dependency declared
            raise P2PError("cryptography_missing", "cryptography is required") from exc
        private = ed25519.Ed25519PrivateKey.generate()
        priv_raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        pub_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        pub_b64 = base64.b64encode(pub_raw).decode("ascii")
        fp = fingerprint(pub_b64)
        return Identity(
            device_id=f"maya-{fp[:12]}",
            public_key_b64=pub_b64,
            fingerprint=fp,
            private_key_b64=base64.b64encode(priv_raw).decode("ascii"),
        )

    def load_or_create(self) -> Identity:
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise P2PError("identity_corrupt", "Identity file is unreadable") from exc
            try:
                pub = str(data["public_key"])
                priv = str(data["private_key"])
                fp = fingerprint(pub)
                identity = Identity(
                    device_id=str(data.get("device_id") or f"maya-{fp[:12]}"),
                    public_key_b64=pub,
                    fingerprint=fp,
                    private_key_b64=priv,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise P2PError("identity_corrupt", "Identity file has invalid fields") from exc
            if str(data.get("fingerprint", fp)) != fp:
                raise P2PError("identity_corrupt", "Identity fingerprint mismatch")
            return identity

        identity = self._generate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(identity.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:  # best effort on Windows; not all filesystems support chmod
            self.path.chmod(0o600)
        except OSError:
            pass
        return identity

    def create_invite(
        self,
        host: str = "",
        port: int = 0,
        ttl_seconds: int = 120,
        identity: Identity | None = None,
    ) -> Invite:
        ident = identity or self.load_or_create()
        try:
            ttl = max(30, min(int(ttl_seconds), 600))
        except (TypeError, ValueError):
            ttl = 120
        try:
            safe_port = max(0, min(int(port), 65535))
        except (TypeError, ValueError):
            safe_port = 0
        return Invite(
            device_id=ident.device_id,
            public_key_b64=ident.public_key_b64,
            fingerprint=ident.fingerprint,
            host=str(host or ""),
            port=safe_port,
            code=f"{secrets.randbelow(1_000_000):06d}",
            session_id=_b64u_encode(secrets.token_bytes(12)),
            expires_at=int(time.time()) + ttl,
        )


# -- data-channel framing ----------------------------------------------------

def encode_frame(channel: str, payload: dict[str, Any]) -> bytes:
    """Frame a JSON payload with a 4-byte big-endian length prefix."""
    if channel not in CHANNELS:
        raise P2PError("bad_channel", f"Unknown channel: {channel}")
    body = json.dumps(
        {"channel": channel, "payload": payload},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise P2PError("too_large", "Frame exceeds 16 MiB")
    return len(body).to_bytes(4, "big") + body


def decode_frame(buffer: bytes) -> tuple[dict[str, Any], bytes] | None:
    """Return ``(frame, remainder)``, or None while the frame is incomplete."""
    if len(buffer) < 4:
        return None
    size = int.from_bytes(buffer[:4], "big")
    if size <= 0 or size > MAX_FRAME_BYTES:
        raise P2PError("bad_frame", "Frame length is invalid")
    if len(buffer) < 4 + size:
        return None
    body = buffer[4 : 4 + size]
    try:
        obj = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise P2PError("bad_frame", "Frame is not valid UTF-8 JSON") from exc
    if not isinstance(obj, dict) or obj.get("channel") not in CHANNELS or "payload" not in obj:
        raise P2PError("bad_frame", "Frame header is invalid")
    if not isinstance(obj["payload"], dict):
        raise P2PError("bad_frame", "Frame payload must be an object")
    return obj, buffer[4 + size :]


def _as_frame(item: Any) -> dict[str, Any]:
    if isinstance(item, (bytes, bytearray)):
        result = decode_frame(bytes(item))
        if result is None:
            raise P2PError("bad_frame", "Incomplete file frame")
        frame, remainder = result
        if remainder:
            raise P2PError("bad_frame", "File frame has trailing bytes")
        return frame
    if isinstance(item, dict) and item.get("channel") == "files" and isinstance(item.get("payload"), dict):
        return item
    raise P2PError("bad_frame", "Not a file frame")


def chunk_file(path: str | Path, chunk_id: str, chunk_size: int = 16 * 1024) -> Iterator[bytes]:
    """Yield framed, SHA-256-verifiable chunks of a local file."""
    data = Path(path).read_bytes()
    try:
        size = max(1024, min(int(chunk_size), 1024 * 1024))
    except (TypeError, ValueError):
        size = 16 * 1024
    total = max(1, (len(data) + size - 1) // size)
    digest = hashlib.sha256(data).hexdigest()
    name = Path(path).name
    for index in range(total):
        part = data[index * size : (index + 1) * size]
        yield encode_frame(
            "files",
            {
                "type": "chunk",
                "chunk_id": chunk_id,
                "name": name,
                "index": index,
                "total": total,
                "data_b64": base64.b64encode(part).decode("ascii"),
                "sha256": digest,
            },
        )


def reassemble_chunks(frames: Any) -> bytes:
    """Reassemble and verify chunks. Accepts encoded bytes or frame dicts."""
    parts: dict[int, bytes] = {}
    digest = ""
    chunk_id = ""
    total = 0
    for item in frames:
        frame = _as_frame(item)
        payload = frame["payload"]
        if payload.get("type") != "chunk":
            raise P2PError("bad_chunk", "Unexpected file frame type")
        cid = str(payload.get("chunk_id", ""))
        if chunk_id and cid != chunk_id:
            raise P2PError("bad_chunk", "Mixed chunk ids")
        chunk_id = cid
        try:
            index = int(payload["index"])
            expected_total = int(payload["total"])
        except (KeyError, TypeError, ValueError) as exc:
            raise P2PError("bad_chunk", "Chunk index/total invalid") from exc
        if total and expected_total != total:
            raise P2PError("bad_chunk", "Chunk total mismatch")
        total = expected_total
        sha = str(payload.get("sha256", ""))
        if digest and sha != digest:
            raise P2PError("bad_chunk", "Chunk hash mismatch")
        digest = sha
        try:
            parts[index] = base64.b64decode(str(payload.get("data_b64", "")), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise P2PError("bad_chunk", "Chunk data invalid") from exc
    if not total or len(parts) != total:
        raise P2PError("bad_chunk", "Missing chunks")
    try:
        missing = sorted(set(range(total)) - set(parts))
    except TypeError as exc:
        raise P2PError("bad_chunk", "Chunk indices invalid") from exc
    if missing:
        raise P2PError("bad_chunk", f"Missing chunks: {missing[:5]}")
    data = b"".join(parts[i] for i in range(total))
    if hashlib.sha256(data).hexdigest() != digest:
        raise P2PError("bad_chunk", "File hash mismatch")
    return data


# -- WebRTC session ----------------------------------------------------------

def _ice_servers(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = (settings if settings is not None else load_settings()).get("p2p", {})
    if not isinstance(cfg, dict):
        cfg = {}
    raw_stun = cfg.get("stun") or ["stun:stun.l.google.com:19302"]
    if isinstance(raw_stun, str):
        raw_stun = [raw_stun]
    servers: list[dict[str, Any]] = []
    for item in raw_stun:
        if str(item or "").strip():
            servers.append({"urls": str(item).strip()})

    turn = cfg.get("turn", {})
    if isinstance(turn, dict) and turn.get("enabled"):
        host = str(turn.get("host") or "").strip()
        if not host:
            raise P2PError("turn_config_missing", "TURN enabled but host is empty")
        user = os.environ.get(str(turn.get("username_env") or "MAYA_TURN_USERNAME"), "")
        cred = os.environ.get(str(turn.get("credential_env") or "MAYA_TURN_CREDENTIAL"), "")
        if not user or not cred:
            raise P2PError("turn_credentials_missing", "TURN credentials are not set in the environment")
        urls = host if host.startswith(("turn:", "turns:")) else f"turn:{host}"
        servers.append({"urls": urls, "username": user, "credential": cred})
    return servers


def _import_aiortc() -> Any:
    try:
        import aiortc  # type: ignore[import-not-found]
    except ImportError as exc:
        raise P2PError("aiortc_missing", "aiortc is not installed") from exc
    return aiortc


def _session_payload(kind: str, sdp: str, fp: str, sid: str) -> str:
    return encode_payload(
        {
            "v": VERSION,
            "kind": kind,
            "sdp": sdp,
            "type": "offer" if kind == OFFER_KIND else "answer",
            "fp": fp,
            "sid": sid,
            "exp": int(time.time()) + 120,
        }
    )


def _decode_session(text: str, expected_kind: str) -> dict[str, Any]:
    obj = decode_payload(text)
    if obj.get("v") != VERSION or obj.get("kind") != expected_kind:
        raise P2PError("bad_signal", "Not a Maya P2P signal")
    try:
        sdp = str(obj["sdp"])
        fp = str(obj["fp"])
        sid = str(obj["sid"])
        exp = int(obj["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise P2PError("bad_signal", "Signal fields are invalid") from exc
    if exp <= int(time.time()):
        raise P2PError("expired", "Signal expired")
    return {"sdp": sdp, "fp": fp, "sid": sid}


class P2PSession:
    """A single manual-signaled WebRTC session. No auto-connect, no cloud."""

    def __init__(
        self,
        identity: Identity | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.identity = identity or IdentityStore().load_or_create()
        self.settings = settings if settings is not None else load_settings()
        self.on_message: Callable[[str, dict[str, Any]], None] | None = None
        self._pc: Any | None = None
        self._channels: dict[str, Any] = {}
        self._state = "new"
        self._incoming: bytes = b""
        self._expected_sid: str | None = None

    @property
    def state(self) -> str:
        return self._state

    def _new_pc(self, aiortc: Any) -> Any:
        pc = aiortc.RTCPeerConnection(iceServers=_ice_servers(self.settings))
        pc.on("connectionstatechange", lambda: self._on_state(getattr(pc, "connectionState", "new")))
        pc.on("datachannel", self._on_datachannel)
        self._pc = pc
        self._state = "connecting"
        for name in CHANNELS:
            channel = pc.createDataChannel(name)
            self._bind_channel(channel)
            self._channels[name] = channel
        return pc

    def _on_state(self, raw: str) -> None:
        raw = str(raw or "new")
        if raw in {"connected"}:
            self._state = "connected"
        elif raw in {"failed", "disconnected", "closed"}:
            self._state = "failed" if raw == "disconnected" else raw
        else:
            self._state = "connecting"

    def _bind_channel(self, channel: Any) -> None:
        label = str(getattr(channel, "label", "control"))

        def _message(data: Any) -> None:
            if isinstance(data, (bytes, bytearray)):
                self._incoming += bytes(data)
                while True:
                    parsed = decode_frame(self._incoming)
                    if parsed is None:
                        break
                    frame, self._incoming = parsed
                    if self.on_message:
                        self.on_message(str(frame["channel"]), dict(frame["payload"]))
            elif isinstance(data, str):
                try:
                    obj = json.loads(data)
                except ValueError:
                    return
                if isinstance(obj, dict) and self.on_message:
                    self.on_message(label, obj)

        channel.on("open", lambda: None)
        channel.on("message", _message)
        self._channels[label] = channel

    def _on_datachannel(self, channel: Any) -> None:
        self._bind_channel(channel)

    async def _wait_ice(self, pc: Any) -> None:
        deadline = time.monotonic() + ICE_WAIT_SECONDS
        while getattr(pc, "iceGatheringState", "complete") != "complete":
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.05)

    def _sdp(self) -> str:
        if self._pc is None or getattr(self._pc, "localDescription", None) is None:
            raise P2PError("no_session", "No local session description")
        return str(self._pc.localDescription.sdp)

    async def create_offer(self) -> str:
        aiortc = _import_aiortc()
        pc = self._new_pc(aiortc)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await self._wait_ice(pc)
        sid = _b64u_encode(secrets.token_bytes(12))
        self._expected_sid = sid
        return _session_payload(OFFER_KIND, self._sdp(), self.identity.fingerprint, sid)

    async def accept_offer(self, offer_text: str) -> str:
        aiortc = _import_aiortc()
        offer = _decode_session(offer_text, OFFER_KIND)
        if offer["fp"] and offer["fp"] != self.identity.fingerprint:
            # Fingerprint mismatch is allowed here: it is the *peer's* fingerprint.
            # The invite/QR layer performs peer identity verification; do not
            # reject a legitimate offer merely because our fp differs.
            pass
        pc = self._new_pc(aiortc)
        await pc.setRemoteDescription(aiortc.RTCSessionDescription(sdp=offer["sdp"], type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await self._wait_ice(pc)
        return _session_payload(ANSWER_KIND, self._sdp(), self.identity.fingerprint, offer["sid"])

    async def accept_answer(self, answer_text: str) -> None:
        aiortc = _import_aiortc()
        answer = _decode_session(answer_text, ANSWER_KIND)
        if self._pc is None:
            raise P2PError("no_session", "No offer was created")
        if self._expected_sid is not None and answer["sid"] != self._expected_sid:
            raise P2PError("sid_mismatch", "Answer session id does not match the offer")
        await self._pc.setRemoteDescription(
            aiortc.RTCSessionDescription(sdp=answer["sdp"], type="answer")
        )
        self._state = "connected"

    def send(self, channel: str, payload: dict[str, Any]) -> None:
        if channel not in CHANNELS:
            raise P2PError("bad_channel", f"Unknown channel: {channel}")
        target = self._channels.get(channel)
        if target is None or str(getattr(target, "readyState", "closed")) != "open":
            raise P2PError("channel_closed", f"Channel {channel} is not open")
        target.send(encode_frame(channel, payload))

    async def close(self) -> None:
        if self._pc is not None:
            await self._pc.close()
        self._pc = None
        self._channels.clear()
        self._incoming = b""
        self._expected_sid = None
        self._state = "closed"


__all__ = [
    "P2PError",
    "Identity",
    "IdentityStore",
    "Invite",
    "P2PSession",
    "VERSION",
    "CHANNELS",
    "encode_payload",
    "decode_payload",
    "encode_invite",
    "decode_invite",
    "fingerprint",
    "encode_frame",
    "decode_frame",
    "chunk_file",
    "reassemble_chunks",
]

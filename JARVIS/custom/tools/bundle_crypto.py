"""AES-GCM encryption + anti-replay for Maya device bundles.

Bundles are HMAC-signed by ``custom.tools.devices``. This module adds an
optional encryption layer: the signed JSON bundle is wrapped in an
authenticated envelope (AES-256-GCM) so the payload is confidential in
transit. A per-device sequence counter is embedded in the envelope and
checked on import to reject replays.

The envelope format (version 1)::

    {
      "format": "maya-device-bundle-encrypted",
      "version": 1,
      "enc": {
        "algo": "aes-256-gcm",
        "salt": "<hex>",
        "iterations": 600000,
        "nonce": "<base64 12 bytes>",
        "seq": 42
      },
      "payload": "<base64 ciphertext+tag>"
    }

The inner signed bundle stays untouched, so an unencrypted import path still
works (backwards compatible).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

FORMAT = "maya-device-bundle-encrypted"
VERSION = 1
KDF_ALGO = "pbkdf2_sha256"
KDF_ITERATIONS = 600_000
NONCE_BYTES = 12
KEY_BYTES = 32


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise RuntimeError("cryptography is required for encrypted bundles") from exc
    return AESGCM


def derive_key(code: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    """Derive a 32-byte AES key from the pairing code."""
    return hashlib.pbkdf2_hmac(
        "sha256", str(code or "").strip().encode("utf-8"), salt, int(iterations), dklen=KEY_BYTES
    )


def encrypt_envelope(plaintext: bytes, code: str, seq: int) -> dict[str, Any]:
    """Wrap ``plaintext`` in an authenticated, replay-numbered envelope."""
    if not isinstance(plaintext, bytes) or not plaintext:
        raise ValueError("plaintext must be non-empty bytes")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = derive_key(code, salt)
    ciphertext = _aesgcm()(key).encrypt(nonce, plaintext, None)
    return {
        "format": FORMAT,
        "version": VERSION,
        "enc": {
            "algo": "aes-256-gcm",
            "salt": salt.hex(),
            "iterations": KDF_ITERATIONS,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "seq": int(seq),
        },
        "payload": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_envelope(envelope: dict[str, Any], code: str, *, allow_replay: bool = False) -> bytes:
    """Verify + decrypt an envelope. Raises ``ValueError`` on any tamper."""
    if envelope.get("format") != FORMAT or envelope.get("version") != VERSION:
        raise ValueError("not an encrypted bundle envelope")
    enc = envelope.get("enc")
    if not isinstance(enc, dict):
        raise ValueError("envelope has no enc block")
    if enc.get("algo") != "aes-256-gcm":
        raise ValueError("unsupported encryption algorithm")
    try:
        salt = bytes.fromhex(str(enc.get("salt", "")))
        iterations = int(enc.get("iterations", 0))
        nonce = base64.b64decode(str(enc.get("nonce", "")), validate=True)
        ciphertext = base64.b64decode(str(envelope.get("payload", "")), validate=True)
        seq = int(enc.get("seq", -1))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("envelope fields are invalid") from exc
    if iterations != KDF_ITERATIONS or len(nonce) != NONCE_BYTES or seq < 0:
        raise ValueError("envelope parameters are not allowed")
    key = derive_key(code, salt, iterations)
    try:
        plaintext = _aesgcm()(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001 - cryptography raises several types
        raise ValueError("envelope authentication failed") from exc
    if not allow_replay and not _check_sequence(seq):
        raise ValueError("replay detected (sequence number already used)")
    return plaintext


def is_envelope(data: bytes) -> bool:
    """True when ``data`` looks like an encrypted envelope."""
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(obj, dict) and obj.get("format") == FORMAT


def _check_sequence(seq: int) -> bool:
    """Return True when ``seq`` is newer than the stored high-water mark."""
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    last = raw.get("last_seq", 0)
    try:
        last = int(last)
    except (TypeError, ValueError):
        last = 0
    return seq > last


def commit_sequence(seq: int) -> None:
    """Record ``seq`` as the new high-water mark (best effort)."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump({"version": 1, "last_seq": int(seq)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _state_path() -> Path:
    override = os.environ.get("MAYA_BUNDLE_SEQ", "").strip()
    if override:
        return Path(override).expanduser()
    from custom.config import PROJECT_ROOT

    return PROJECT_ROOT / "MAYA AI" / "memory" / "offline" / "bundle_seq.json"


def envelope_fingerprint(envelope: dict[str, Any]) -> str:
    """Stable fingerprint for logging/auditing (never the payload)."""
    enc = envelope.get("enc", {}) if isinstance(envelope, dict) else {}
    return hmac.new(b"maya-bundle-fp", json.dumps(enc, sort_keys=True).encode(), hashlib.sha256).hexdigest()[:16]


__all__ = [
    "commit_sequence",
    "decrypt_envelope",
    "derive_key",
    "encrypt_envelope",
    "envelope_fingerprint",
    "is_envelope",
]

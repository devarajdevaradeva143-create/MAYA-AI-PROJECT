"""Tests for the local-first P2P core (identity, framing, manual signaling)."""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from custom.tools import p2p


def test_identity_persists_locally(tmp_path: Path) -> None:
    store = p2p.IdentityStore(tmp_path / "p2p_identity.json")
    first = store.load_or_create()
    second = store.load_or_create()

    assert first.device_id == second.device_id
    assert first.public_key_b64 == second.public_key_b64
    assert first.private_key_b64 == second.private_key_b64
    assert first.fingerprint == p2p.fingerprint(first.public_key_b64)
    assert len(first.fingerprint) == 32
    assert "private_key" in store.path.read_text(encoding="utf-8")


def test_invite_roundtrip_and_validation(tmp_path: Path) -> None:
    identity = p2p.IdentityStore(tmp_path / "id.json").load_or_create()
    store = p2p.IdentityStore(tmp_path / "id.json")
    invite = store.create_invite(host="10.0.0.5", port=8420, identity=identity)

    decoded = p2p.decode_invite(invite.to_text())
    assert decoded.device_id == identity.device_id
    assert decoded.code == invite.code
    assert decoded.host == "10.0.0.5"
    assert decoded.port == 8420

    tampered = replace(invite, fingerprint="0" * 32)
    with pytest.raises(p2p.P2PError) as exc:
        p2p.decode_invite(tampered.to_text())
    assert exc.value.code == "bad_fingerprint"

    expired = replace(invite, expires_at=int(time.time()) - 1)
    with pytest.raises(p2p.P2PError) as exc:
        p2p.decode_invite(expired.to_text())
    assert exc.value.code == "expired"


def test_frame_partial_and_remainder() -> None:
    first = p2p.encode_frame("chat", {"text": "one"})
    second = p2p.encode_frame("control", {"action": "ping"})
    stream = first + second

    assert p2p.decode_frame(stream[:3]) is None
    frame, remainder = p2p.decode_frame(stream)  # type: ignore[misc]
    assert frame["channel"] == "chat"
    assert frame["payload"] == {"text": "one"}
    next_frame, rest = p2p.decode_frame(remainder)  # type: ignore[misc]
    assert next_frame["channel"] == "control"
    assert rest == b""


def test_frame_rejects_bad_length() -> None:
    with pytest.raises(p2p.P2PError) as exc:
        p2p.decode_frame((0).to_bytes(4, "big"))
    assert exc.value.code == "bad_frame"


def test_file_chunk_roundtrip_and_missing_chunk(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    payload = b"maya p2p local file test" * 500
    path.write_bytes(payload)

    frames = list(p2p.chunk_file(path, "cid-1", chunk_size=512))
    assert len(frames) > 1
    assert p2p.reassemble_chunks(frames) == payload

    with pytest.raises(p2p.P2PError) as exc:
        p2p.reassemble_chunks(frames[:-1])
    assert exc.value.code == "bad_chunk"


def test_missing_aiortc_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "aiortc", None)
    identity = p2p.IdentityStore(tmp_path / "id.json").load_or_create()
    session = p2p.P2PSession(identity=identity, settings={"p2p": {"stun": [], "turn": {}}})

    with pytest.raises(p2p.P2PError) as exc:
        asyncio.run(session.create_offer())
    assert exc.value.code == "aiortc_missing"


class _FakeChannel:
    def __init__(self, label: str) -> None:
        self.label = label
        self.readyState = "open"
        self.handlers: dict[str, object] = {}
        self.sent: list[bytes] = []

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def send(self, data: bytes) -> None:
        self.sent.append(data)


class _FakeDescription:
    def __init__(self, sdp: str, type: str) -> None:
        self.sdp = sdp
        self.type = type


class _FakePeerConnection:
    def __init__(self, iceServers: object = None) -> None:
        self.iceServers = iceServers
        self.iceGatheringState = "complete"
        self.connectionState = "new"
        self.localDescription: _FakeDescription | None = None
        self.remoteDescription: _FakeDescription | None = None
        self.handlers: dict[str, object] = {}
        self.channels: dict[str, _FakeChannel] = {}

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def createDataChannel(self, label: str) -> _FakeChannel:
        channel = _FakeChannel(label)
        self.channels[label] = channel
        return channel

    async def createOffer(self) -> _FakeDescription:
        return _FakeDescription("v=0\r\noffer", "offer")

    async def createAnswer(self) -> _FakeDescription:
        return _FakeDescription("v=0\r\nanswer", "answer")

    async def setLocalDescription(self, description: _FakeDescription) -> None:
        self.localDescription = description

    async def setRemoteDescription(self, description: _FakeDescription) -> None:
        self.remoteDescription = description

    async def close(self) -> None:
        self.connectionState = "closed"


def _fake_aiortc() -> ModuleType:
    module = ModuleType("aiortc")
    module.RTCPeerConnection = _FakePeerConnection  # type: ignore[attr-defined]
    module.RTCSessionDescription = _FakeDescription  # type: ignore[attr-defined]
    return module


def test_manual_offer_answer_and_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "aiortc", _fake_aiortc())
    identity = p2p.IdentityStore(tmp_path / "id.json").load_or_create()
    settings = {"p2p": {"stun": ["stun:example.test:3478"], "turn": {}}}
    caller = p2p.P2PSession(identity=identity, settings=settings)
    callee = p2p.P2PSession(identity=identity, settings=settings)

    offer = asyncio.run(caller.create_offer())
    answer = asyncio.run(callee.accept_offer(offer))
    asyncio.run(caller.accept_answer(answer))

    assert p2p.decode_payload(offer)["kind"] == p2p.OFFER_KIND
    assert p2p.decode_payload(answer)["kind"] == p2p.ANSWER_KIND
    assert caller.state == "connected"

    caller.send("chat", {"text": "hi"})
    assert caller._channels["chat"].sent  # type: ignore[attr-defined]
    asyncio.run(caller.close())
    assert caller.state == "closed"


def test_answer_sid_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "aiortc", _fake_aiortc())
    identity = p2p.IdentityStore(tmp_path / "id.json").load_or_create()
    session = p2p.P2PSession(
        identity=identity, settings={"p2p": {"stun": [], "turn": {}}}
    )

    asyncio.run(session.create_offer())
    bad_answer = p2p.encode_payload(
        {
            "v": p2p.VERSION,
            "kind": p2p.ANSWER_KIND,
            "sdp": "v=0\r\nanswer",
            "type": "answer",
            "fp": identity.fingerprint,
            "sid": "different-session",
            "exp": int(time.time()) + 60,
        }
    )
    with pytest.raises(p2p.P2PError) as exc:
        asyncio.run(session.accept_answer(bad_answer))
    assert exc.value.code == "sid_mismatch"


def test_turn_requires_env_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAYA_TURN_USERNAME", raising=False)
    monkeypatch.delenv("MAYA_TURN_CREDENTIAL", raising=False)
    settings = {
        "p2p": {
            "stun": [],
            "turn": {"enabled": True, "host": "turn.example.test:3478"},
        }
    }
    with pytest.raises(p2p.P2PError) as exc:
        p2p._ice_servers(settings)
    assert exc.value.code == "turn_credentials_missing"

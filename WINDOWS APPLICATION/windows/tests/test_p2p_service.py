"""Tests for the Windows P2P facade and settings wiring."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from app.services import p2p_service
from app.settings_repository import _as_url, writable_keys


class _FakeSession:
    def __init__(self) -> None:
        self.identity = SimpleNamespace(device_id="maya-test")
        self.state = "new"
        self.on_message = None
        self.sent: list[tuple[str, dict]] = []

    async def create_offer(self) -> str:
        return "offer-payload"

    async def accept_offer(self, text: str) -> str:
        return "answer-payload"

    async def accept_answer(self, text: str) -> None:
        self.state = "connected"

    def send(self, channel: str, payload: dict) -> None:
        self.sent.append((channel, payload))

    async def close(self) -> None:
        self.state = "closed"


def test_url_accepts_wss() -> None:
    assert _as_url("wss://relay.example.test:443") == "wss://relay.example.test:443"


def test_settings_keys_are_wired() -> None:
    keys = writable_keys()
    assert "server.wan.enabled" in keys
    assert "server.wan.relay_url" in keys
    assert "p2p.enabled" in keys
    assert "wan_remote.enabled" not in keys


def test_create_offer_blocked_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        p2p_service,
        "load_settings",
        lambda: {"p2p": {"enabled": False, "turn": {}}},
    )
    facade = p2p_service.P2PService()
    result = facade.create_offer()
    assert result["ok"] is False
    assert result["code"] == "disabled"


def test_offer_answer_and_permission_gate(monkeypatch) -> None:
    settings = {
        "p2p": {
            "enabled": True,
            "turn": {"enabled": False, "host": ""},
        }
    }
    monkeypatch.setattr(p2p_service, "load_settings", lambda: settings)
    session = _FakeSession()
    facade = p2p_service.P2PService(session=session)

    offer = facade.create_offer()
    assert offer == {"ok": True, "payload": "offer-payload"}

    answer = facade.accept_offer("offer-payload")
    assert answer == {"ok": True, "payload": "answer-payload"}

    assert facade.accept_answer("answer-payload")["ok"] is True
    assert facade.status()["connected"] is True
    assert facade.status()["relay"] is False

    denied = facade.send_chat("hello", confirm=lambda _a, _d: False)
    assert denied["code"] == "denied"
    assert session.sent == []

    allowed = facade.send_chat("hello", confirm=lambda _a, _d: True)
    assert allowed["ok"] is True
    assert session.sent == [("chat", {"text": "hello"})]

    facade.close()


def test_remote_control_waits_for_explicit_approval(monkeypatch) -> None:
    settings = {"p2p": {"enabled": True, "turn": {"enabled": False, "host": ""}}}
    monkeypatch.setattr(p2p_service, "load_settings", lambda: settings)
    applied: list[list[dict]] = []
    fake_module = ModuleType("app.services.remote_service")
    fake_module.InputAdapter = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        apply=lambda events: applied.append(events)
    )
    monkeypatch.setitem(sys.modules, "app.services.remote_service", fake_module)

    session = _FakeSession()
    facade = p2p_service.P2PService(session=session)
    facade._session_obj()  # wires on_message for injected sessions too

    events = [{"type": "key", "key": "a"}]
    session.on_message("control", {"action": "input", "events": events})
    assert facade.status()["pending_controls"] == 1
    assert applied == []

    denied = facade.approve_next_control(confirm=lambda _a, _d: False)
    assert denied["code"] == "denied"
    assert applied == []
    assert facade.status()["pending_controls"] == 1

    allowed = facade.approve_next_control(confirm=lambda _a, _d: True)
    assert allowed["ok"] is True
    assert applied == [events]
    assert facade.status()["pending_controls"] == 0

    facade.close()

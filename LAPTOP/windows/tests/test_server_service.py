"""Desktop service adapters + real uvicorn bootstrap tests."""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.control_service import ControlService
from app.services.engine_service import (
    EngineAdapter,
    EngineTimeoutError,
    EngineUnavailableError,
)
from app.services.server_service import ServerService, server_settings
from app.services.wake_service import WakeAdapter
from tests.fakes import DEVICE_ID, FakeEngine, auth, make_harness

# -- settings ---------------------------------------------------------


def test_server_settings_parse_and_coerce() -> None:
    raw = {
        "server": {
            "host": "127.0.0.1",
            "port": "9000",
            "lan_only": "false",
            "pin_ttl_seconds": 10,
            "max_devices": 99,
        },
        "permissions": {"allowed_roots": ["C:\\work", "", 3]},
    }

    settings = server_settings(raw)

    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.lan_only is False
    assert settings.pin_ttl_seconds == 30  # clamped
    assert settings.max_devices == 32  # clamped
    assert settings.allowed_roots == ["C:\\work"]
    assert settings.enabled is True


def test_server_settings_defaults_when_missing() -> None:
    settings = server_settings({})

    assert settings.host == "0.0.0.0"
    assert settings.port == 8420
    assert settings.lan_only is True
    assert settings.allowed_roots == []
    assert settings.wan_host == ""
    assert settings.wan_mode == "lan"


def test_server_settings_parses_wan_keys() -> None:
    raw = {
        "server": {
            "wan": {
                "enabled": True,
                "host": "100.64.0.5",
                "relay_url": "relay.example.com:9443",
                "cert_path": "/etc/maya/maya.crt",
                "key_path": "/etc/maya/maya.key",
                "mode": "wan",
            }
        }
    }
    settings = server_settings(raw)

    assert settings.wan_enabled is True
    assert settings.wan_host == "100.64.0.5"
    assert settings.wan_relay_url == "relay.example.com:9443"
    assert settings.wan_cert_path == "/etc/maya/maya.crt"
    assert settings.wan_key_path == "/etc/maya/maya.key"
    assert settings.wan_mode == "wan"


# -- engine adapter ---------------------------------------------------


def test_engine_adapter_passes_replies() -> None:
    adapter = EngineAdapter(FakeEngine(reply="hi"))

    assert adapter.chat([{"role": "user", "content": "x"}]) == "hi"
    assert adapter.model  # read from the bridge
    assert adapter.health() == {"status": "ok"}


def test_engine_adapter_maps_timeout_string() -> None:
    adapter = EngineAdapter(FakeEngine(reply="[engine error] Read timeout on request"))

    with pytest.raises(EngineTimeoutError):
        adapter.chat([])


def test_engine_adapter_maps_unavailable_string() -> None:
    adapter = EngineAdapter(FakeEngine(reply="[engine error] connection refused"))

    with pytest.raises(EngineUnavailableError):
        adapter.chat([])


def test_engine_adapter_maps_stream_error() -> None:
    adapter = EngineAdapter(FakeEngine(chunks=["[engine error] timed out"]))

    with pytest.raises(EngineTimeoutError):
        list(adapter.chat_stream([]))


def test_engine_adapter_streams_chunks() -> None:
    adapter = EngineAdapter(FakeEngine(chunks=["a", "b"]))

    assert list(adapter.chat_stream([])) == ["a", "b"]


# -- control service --------------------------------------------------


def test_control_file_write_read_and_audit(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    service = ControlService(audit_path=audit)
    target = tmp_path / "note.txt"

    written = service.execute("file.write", {"path": str(target), "content": "hello"})
    read = service.execute("file.read", {"path": str(target)})

    assert written["path"] == str(target)
    assert target.read_text(encoding="utf-8") == "hello"
    assert read["content"] == "hello"

    lines = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [line["action"] for line in lines] == ["file.write", "file.read"]
    assert all(line["ok"] for line in lines)
    assert "hello" not in audit.read_text(encoding="utf-8")


def test_control_dir_list_orders_folders_first(tmp_path) -> None:
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a_dir").mkdir()
    service = ControlService(audit_path=tmp_path / "audit.jsonl")

    result = service.execute("dir.list", {"path": str(tmp_path)})

    names = [entry["name"] for entry in result["entries"]]
    assert names[0] == "a_dir"
    assert "b.txt" in names


def test_control_unsupported_action_is_audited_as_failure(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    service = ControlService(audit_path=audit)

    with pytest.raises(RuntimeError):
        service.execute("kernel.explode", {})

    entry = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert entry == {"ts": entry["ts"], "action": "kernel.explode", "ok": False, "source": "phone"}


# -- wake adapter -----------------------------------------------------


def test_wake_status_and_events_are_honest() -> None:
    wake = WakeAdapter()

    status = wake.status()

    assert set(status) == {"listening", "clap", "name"}
    assert status["listening"] is False
    assert wake.drain_events() == []
    wake.stop()
    assert wake.status()["listening"] is False


# -- real uvicorn end to end ------------------------------------------


def test_server_service_serves_health_pair_and_chat(tmp_path) -> None:
    harness = make_harness(tmp_path)
    harness.services.host = "127.0.0.1"
    service = ServerService(
        harness.services,
        host="127.0.0.1",
        port=0,
        token_store=harness.tokens,
        limiter=harness.limiter,
        pairing=harness.pairing,
        confirm_store=harness.confirm,
    )

    service.start()
    try:
        assert service.running
        assert service.bound_port
        base = f"http://127.0.0.1:{service.bound_port}/api/v1"

        health = httpx.get(f"{base}/health", timeout=5)
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        pin, _ = service.pairing.generate_pin()
        claim = httpx.post(
            f"{base}/pair/claim",
            json={
                "device_id": DEVICE_ID,
                "device_name": "Test Phone",
                "pin": pin,
                "app_version": "0.1.0",
                "api": 1,
            },
            timeout=5,
        )
        assert claim.status_code == 200
        assert claim.json()["port"] == service.bound_port
        token = claim.json()["token"]

        chat = httpx.post(
            f"{base}/chat",
            json={
                "conversation_id": "c_e2e",
                "persona": "maya",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=auth(token),
            timeout=10,
        )
        assert chat.status_code == 200
        assert chat.json()["reply"] == "Vanakkam da!"
    finally:
        service.stop()

    assert not service.running


def test_server_service_public_client_is_blocked(tmp_path) -> None:
    """Loopback is fine; a forged public client tuple is not (middleware unit)."""
    from custom.server.lan import is_allowed_client

    assert is_allowed_client("127.0.0.1") is True
    assert is_allowed_client("192.168.1.20") is True
    assert is_allowed_client("10.0.0.5") is True
    assert is_allowed_client("172.16.4.4") is True
    assert is_allowed_client("8.8.8.8") is False
    assert is_allowed_client(None) is False

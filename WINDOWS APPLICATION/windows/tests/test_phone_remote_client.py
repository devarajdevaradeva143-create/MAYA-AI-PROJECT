"""Phone Remote client: resolve the paired phone's last known LAN IP."""

from __future__ import annotations

import time
from types import SimpleNamespace

from app.services import phone_remote_client as module


class FakeTokens:
    def __init__(self, devices: list[SimpleNamespace]) -> None:
        self._devices = devices

    def list_active(self) -> list[SimpleNamespace]:
        return self._devices


def _service(devices: list[SimpleNamespace], *, running: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        running=running,
        app=SimpleNamespace(state=SimpleNamespace(tokens=FakeTokens(devices))),
    )


def test_paired_phone_ip_uses_last_ip_of_most_recent_device(monkeypatch) -> None:
    now = time.time()
    devices = [
        SimpleNamespace(last_seen=now - 500, last_ip="10.0.0.9"),
        SimpleNamespace(last_seen=now, last_ip="10.0.0.5"),
    ]
    monkeypatch.setattr(module, "shared_server_service", lambda: _service(devices))

    client = module.PhoneRemoteClient()

    assert client._get_paired_phone_ip() == "10.0.0.5"


def test_paired_phone_ip_ignores_devices_without_an_ip(monkeypatch) -> None:
    now = time.time()
    devices = [
        SimpleNamespace(last_seen=now, last_ip=""),
        SimpleNamespace(last_seen=now - 10, last_ip="10.0.0.7"),
    ]
    monkeypatch.setattr(module, "shared_server_service", lambda: _service(devices))

    client = module.PhoneRemoteClient()

    assert client._get_paired_phone_ip() == "10.0.0.7"


def test_paired_phone_ip_is_none_when_server_is_stopped(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "shared_server_service",
        lambda: _service([], running=False),
    )

    client = module.PhoneRemoteClient()

    assert client._get_paired_phone_ip() is None


def test_paired_phone_ip_is_none_without_a_registered_ip(monkeypatch) -> None:
    now = time.time()
    devices = [SimpleNamespace(last_seen=now, last_ip="")]
    monkeypatch.setattr(module, "shared_server_service", lambda: _service(devices))

    client = module.PhoneRemoteClient()

    assert client._get_paired_phone_ip() is None

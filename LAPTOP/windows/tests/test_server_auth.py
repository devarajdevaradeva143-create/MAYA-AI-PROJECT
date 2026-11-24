"""Health, LAN guard, token auth and pairing tests."""

from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from tests.fakes import (
    DEVICE_ID,
    OTHER_DEVICE_ID,
    auth,
    error_code,
    make_harness,
    pair_device,
)


def test_health_shape_without_auth(tmp_path) -> None:
    harness = make_harness(tmp_path)

    response = harness.client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "maya-laptop"
    assert body["api"] == 1
    assert body["platform"] == "windows"
    assert body["model"] == "qwen3-3b"
    assert body["engine"] == "lemonade"
    assert "chat" in body["capabilities"]
    assert "voice_stt" in body["capabilities"]
    assert body["paired_devices"] == 0
    assert body["uptime_s"] >= 60


def test_public_client_is_rejected(tmp_path) -> None:
    harness = make_harness(tmp_path)
    public = TestClient(harness.app, client=("8.8.8.8", 12345))

    health = public.get("/api/v1/health")
    chat = public.post("/api/v1/chat", json={})

    assert health.status_code == 403
    assert error_code(health) == 4002
    assert chat.status_code == 403
    assert error_code(chat) == 4002


def test_lan_guard_can_be_disabled(tmp_path) -> None:
    harness = make_harness(tmp_path, lan_only=False)
    public = TestClient(harness.app, client=("8.8.8.8", 12345))

    assert public.get("/api/v1/health").status_code == 200


def test_protected_endpoint_requires_token(tmp_path) -> None:
    harness = make_harness(tmp_path)

    response = harness.client.get("/api/v1/pair/devices")

    assert response.status_code == 401
    assert error_code(response) == 1001


def test_valid_pin_returns_token_and_stores_only_hash(tmp_path) -> None:
    harness = make_harness(tmp_path)
    pin, pin_expires_at = harness.pairing.generate_pin()

    response = harness.client.post(
        "/api/v1/pair/claim",
        json={
            "device_id": DEVICE_ID,
            "device_name": "Devaraj Phone",
            "pin": pin,
            "app_version": "0.1.0",
            "api": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"].startswith("maya_")
    assert body["api"] == 1
    assert body["laptop_name"] == "Test-Laptop"
    assert body["host"] == "192.168.1.50"
    assert body["port"] == 8420
    # Token TTL (30 days), not the 120 s PIN expiry.
    assert body["expires_at"] > pin_expires_at

    raw = (tmp_path / "tokens.json").read_text(encoding="utf-8")
    assert body["token"] not in raw
    assert hashlib.sha256(body["token"].encode()).hexdigest() in raw
    stored = json.loads(raw)
    assert stored["devices"][DEVICE_ID]["token_hash"]


def test_wrong_pin_counts_and_locks_out(tmp_path) -> None:
    harness = make_harness(tmp_path)
    pin, _ = harness.pairing.generate_pin()
    wrong = "000000" if pin != "000000" else "111111"

    codes = []
    for _ in range(5):
        response = harness.client.post(
            "/api/v1/pair/claim",
            json={
                "device_id": DEVICE_ID,
                "device_name": "Phone",
                "pin": wrong,
                "app_version": "0.1.0",
                "api": 1,
            },
        )
        codes.append((response.status_code, error_code(response)))

    assert codes[0] == (401, 1003)
    assert codes[-1] == (429, 1005)


def test_expired_pin_returns_1004(tmp_path) -> None:
    harness = make_harness(tmp_path)
    pin, _ = harness.pairing.generate_pin()
    harness.pairing._pin.expires_at = 0  # noqa: SLF001 - TTL test

    response = harness.client.post(
        "/api/v1/pair/claim",
        json={
            "device_id": DEVICE_ID,
            "device_name": "Phone",
            "pin": pin,
            "app_version": "0.1.0",
            "api": 1,
        },
    )

    assert response.status_code == 401
    assert error_code(response) == 1004


def test_qr_claim_is_single_use(tmp_path) -> None:
    harness = make_harness(tmp_path)
    payload = harness.pairing.generate_qr("192.168.1.50", 8420, "Test-Laptop")
    body = {
        "qr_token": payload["t"],
        "device_id": DEVICE_ID,
        "device_name": "Phone",
        "app_version": "0.1.0",
        "api": 1,
    }

    first = harness.client.post("/api/v1/pair/qr/claim", json=body)
    second = harness.client.post("/api/v1/pair/qr/claim", json=body)

    assert first.status_code == 200
    assert first.json()["token"].startswith("maya_")
    assert second.status_code == 401
    assert error_code(second) == 1004


def test_refresh_rotates_the_token(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.post(
        "/api/v1/pair/refresh",
        json={"device_id": DEVICE_ID},
        headers=auth(token),
    )

    assert response.status_code == 200
    refreshed = response.json()["token"]
    assert refreshed != token
    assert harness.client.get("/api/v1/pair/devices", headers=auth(token)).status_code == 401
    assert harness.client.get("/api/v1/pair/devices", headers=auth(refreshed)).status_code == 200


def test_refresh_rejects_another_device_id(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.post(
        "/api/v1/pair/refresh",
        json={"device_id": OTHER_DEVICE_ID},
        headers=auth(token),
    )

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_device_list_marks_current(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)
    pair_device(harness, device_id=OTHER_DEVICE_ID, name="Old Phone")

    response = harness.client.get("/api/v1/pair/devices", headers=auth(token))

    assert response.status_code == 200
    devices = response.json()["devices"]
    assert len(devices) == 2
    current = [device for device in devices if device["current"]]
    assert len(current) == 1
    assert current[0]["device_id"] == DEVICE_ID


def test_revoke_invalidates_the_token(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)
    other = pair_device(harness, device_id=OTHER_DEVICE_ID, name="Old Phone")

    response = harness.client.delete(
        f"/api/v1/pair/devices/{OTHER_DEVICE_ID}",
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json() == {"revoked": True}
    revoked = harness.client.get("/api/v1/pair/devices", headers=auth(other))
    assert revoked.status_code == 401
    assert error_code(revoked) == 1007


def test_device_limit_is_enforced(tmp_path) -> None:
    harness = make_harness(tmp_path, max_devices=1)
    pair_device(harness)

    pin, _ = harness.pairing.generate_pin()
    response = harness.client.post(
        "/api/v1/pair/claim",
        json={
            "device_id": OTHER_DEVICE_ID,
            "device_name": "Second Phone",
            "pin": pin,
            "app_version": "0.1.0",
            "api": 1,
        },
    )

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_error_envelope_for_unknown_route(tmp_path) -> None:
    harness = make_harness(tmp_path)

    response = harness.client.get("/api/v1/nope")

    assert response.status_code == 404
    assert error_code(response) == 2004

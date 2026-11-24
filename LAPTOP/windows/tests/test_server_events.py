"""WS /ws/events: status snapshots, wake events, socket limit."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.fakes import auth, make_harness, pair_device

EVENTS = "/api/v1/ws/events"


def test_events_requires_auth(tmp_path) -> None:
    harness = make_harness(tmp_path)

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with harness.client.websocket_connect(EVENTS):
            pass

    assert excinfo.value.code == 4401


def test_events_sends_monitor_status_first(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    with harness.client.websocket_connect(f"{EVENTS}?token={token}") as socket:
        frame = socket.receive_json()

    assert frame["type"] == "status"
    assert frame["data"]["cpu"]["percent"] == 12.5
    assert frame["data"]["battery"]["plugged"] is True


def test_events_forwards_wake_event(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    with harness.client.websocket_connect(f"{EVENTS}?token={token}") as socket:
        assert socket.receive_json()["type"] == "status"
        harness.wake.events.append({"type": "wake", "source": "clap", "count": 3})
        frame = socket.receive_json()

    assert frame == {"type": "wake", "source": "clap", "count": 3}


def test_events_allows_two_sockets_and_rejects_third(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    with harness.client.websocket_connect(f"{EVENTS}?token={token}") as first:
        with harness.client.websocket_connect(f"{EVENTS}?token={token}") as second:
            assert first.receive_json()["type"] == "status"
            assert second.receive_json()["type"] == "status"

            with pytest.raises(WebSocketDisconnect) as excinfo:
                with harness.client.websocket_connect(f"{EVENTS}?token={token}"):
                    pass

    assert excinfo.value.code == 4429


def test_events_slot_is_released_after_disconnect(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    with harness.client.websocket_connect(f"{EVENTS}?token={token}") as first:
        assert first.receive_json()["type"] == "status"

    # Closing the session must free the slot for a new connection.
    with harness.client.websocket_connect(f"{EVENTS}?token={token}") as again:
        assert again.receive_json()["type"] == "status"


def test_events_accepts_header_auth_too(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    with harness.client.websocket_connect(EVENTS, headers=auth(token)) as socket:
        frame = socket.receive_json()

    assert frame["type"] == "status"


def test_wake_status_listen_stop(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    status = harness.client.get("/api/v1/wake/status", headers=auth(token))
    listen = harness.client.post(
        "/api/v1/wake/listen",
        json={"seconds": 45},
        headers=auth(token),
    )
    after = harness.client.get("/api/v1/wake/status", headers=auth(token))
    stop = harness.client.post("/api/v1/wake/stop", headers=auth(token))

    assert status.status_code == 200
    assert status.json() == {"listening": False, "clap": True, "name": True}
    assert listen.status_code == 200
    assert listen.json()["listening"] is True
    assert after.json()["listening"] is True
    assert harness.wake.listen_calls == [45]
    assert stop.status_code == 200
    assert stop.json() == {"listening": False}


def test_wake_listen_validates_seconds(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    zero = harness.client.post("/api/v1/wake/listen", json={"seconds": 0}, headers=auth(token))
    huge = harness.client.post("/api/v1/wake/listen", json={"seconds": 301}, headers=auth(token))

    assert zero.status_code == 400
    assert huge.status_code == 400
    assert harness.wake.listen_calls == []


def test_wake_rate_limit_is_5_per_minute(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    for _ in range(5):
        assert (
            harness.client.post(
                "/api/v1/wake/listen",
                json={"seconds": 10},
                headers=auth(token),
            ).status_code
            == 200
        )

    blocked = harness.client.post(
        "/api/v1/wake/listen",
        json={"seconds": 10},
        headers=auth(token),
    )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == 1005

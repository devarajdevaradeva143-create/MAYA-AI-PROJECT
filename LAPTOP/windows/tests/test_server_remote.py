"""Remote session, screen, input, file transfer and hybrid endpoint tests."""

from __future__ import annotations

import pytest
from custom.server import policy

from tests.fakes import (
    OTHER_DEVICE_ID,
    auth,
    error_code,
    make_harness,
    pair_device,
)

PC = "/api/v1/pc"
HYBRID = "/api/v1/hybrid"


@pytest.fixture
def harness(tmp_path, monkeypatch):
    system = tmp_path / "system"
    system.mkdir()
    (system / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(policy, "_system_roots", lambda: [system])
    harness = make_harness(tmp_path)
    harness.system_root = system  # type: ignore[attr-defined]
    return harness


def _start_session(harness, token: str) -> str:
    first = harness.client.post(f"{PC}/remote/start", json={}, headers=auth(token))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "needs_confirmation"
    assert body["description"] == "Allow remote screen and input from this phone?"
    second = harness.client.post(
        f"{PC}/remote/start",
        json={"confirm_token": body["confirm_token"]},
        headers=auth(token),
    )
    assert second.status_code == 200, second.text
    session = second.json()
    assert session["status"] == "done"
    return session["session_token"]


def test_remote_start_needs_confirmation_and_creates_session(harness) -> None:
    token = pair_device(harness)

    session = _start_session(harness, token)

    assert session.startswith("s_")
    assert harness.hybrid.takeovers == 1
    status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": session},
        headers=auth(token),
    )
    assert status.status_code == 200
    assert status.json()["active"] is True
    assert status.json()["expires_in"] > 0


def test_remote_start_confirm_is_single_use(harness) -> None:
    token = pair_device(harness)
    first = harness.client.post(f"{PC}/remote/start", json={}, headers=auth(token)).json()

    harness.client.post(
        f"{PC}/remote/start",
        json={"confirm_token": first["confirm_token"]},
        headers=auth(token),
    )
    replay = harness.client.post(
        f"{PC}/remote/start",
        json={"confirm_token": first["confirm_token"]},
        headers=auth(token),
    )

    assert replay.status_code == 403
    assert error_code(replay) == 4002


def test_starting_a_new_session_drops_the_old_one(harness) -> None:
    token = pair_device(harness)
    old = _start_session(harness, token)
    new = _start_session(harness, token)

    old_status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": old},
        headers=auth(token),
    )
    new_status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": new},
        headers=auth(token),
    )

    assert old_status.json()["active"] is False
    assert new_status.json()["active"] is True


def test_screen_requires_a_live_session(harness) -> None:
    token = pair_device(harness)

    missing = harness.client.get(f"{PC}/screen", headers=auth(token))
    bogus = harness.client.get(
        f"{PC}/screen",
        params={"session_token": "s_bogus123"},
        headers=auth(token),
    )

    assert missing.status_code == 400
    assert error_code(missing) == 2001
    assert bogus.status_code == 403
    assert error_code(bogus) == 4002


def test_screen_returns_jpeg_and_does_not_accept_other_devices(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    other = pair_device(harness, device_id=OTHER_DEVICE_ID, name="Other Phone")

    frame = harness.client.get(
        f"{PC}/screen",
        params={"session_token": session, "max_width": 960, "quality": 55},
        headers=auth(token),
    )
    stolen = harness.client.get(
        f"{PC}/screen",
        params={"session_token": session},
        headers=auth(other),
    )

    assert frame.status_code == 200
    assert frame.headers["content-type"] == "image/jpeg"
    assert frame.headers["x-maya-width"] == "640"
    assert frame.headers["x-maya-height"] == "360"
    assert frame.content.startswith(b"\xff\xd8")
    assert harness.screen.calls == [(960, 55)]
    assert stolen.status_code == 403
    assert error_code(stolen) == 4002


def test_screen_unavailable_maps_to_3001(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    harness.services.screen = None

    response = harness.client.get(
        f"{PC}/screen",
        params={"session_token": session},
        headers=auth(token),
    )

    assert response.status_code == 503
    assert error_code(response) == 3001


def test_remote_stop_invalidates_screen_and_releases_hybrid(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)

    stopped = harness.client.post(
        f"{PC}/remote/stop",
        json={"session_token": session},
        headers=auth(token),
    )
    frame = harness.client.get(
        f"{PC}/screen",
        params={"session_token": session},
        headers=auth(token),
    )

    assert stopped.status_code == 200
    assert stopped.json() == {"status": "done", "active": False, "expires_in": 0}
    assert harness.hybrid.releases == 1
    assert frame.status_code == 403
    assert error_code(frame) == 4002


def test_remote_stop_with_a_foreign_token_does_not_release_control(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    other = pair_device(harness, device_id=OTHER_DEVICE_ID, name="Other Phone")

    stopped = harness.client.post(
        f"{PC}/remote/stop",
        json={"session_token": session},
        headers=auth(other),
    )
    status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": session},
        headers=auth(token),
    )

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "done"
    assert harness.hybrid.releases == 0
    assert status.json()["active"] is True


def test_starting_a_session_on_another_device_drops_the_first(harness) -> None:
    token = pair_device(harness)
    first = _start_session(harness, token)
    other = pair_device(harness, device_id=OTHER_DEVICE_ID, name="Other Phone")
    second = _start_session(harness, other)

    first_status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": first},
        headers=auth(token),
    )
    second_status = harness.client.get(
        f"{PC}/remote/status",
        params={"session_token": second},
        headers=auth(other),
    )

    assert first_status.json()["active"] is False
    assert second_status.json()["active"] is True


def test_input_applies_valid_events(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    events = [
        {"type": "move", "x": 0.5, "y": 0.25},
        {"type": "click", "button": "left"},
        {"type": "scroll", "dy": -3},
        {"type": "text", "text": "vanakkam"},
        {"type": "key", "key": "enter"},
    ]

    response = harness.client.post(
        f"{PC}/input",
        json={"session_token": session, "events": events},
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "done", "applied": 5}
    assert harness.input.calls[0][0] == events[0]


def test_input_rejects_bad_shapes_and_unsupported_keys(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)

    bad_key = harness.client.post(
        f"{PC}/input",
        json={"session_token": session, "events": [{"type": "key", "key": "ctrl+shift+rm"}]},
        headers=auth(token),
    )
    bad_move = harness.client.post(
        f"{PC}/input",
        json={"session_token": session, "events": [{"type": "move", "x": 2}]},
        headers=auth(token),
    )
    too_many = harness.client.post(
        f"{PC}/input",
        json={
            "session_token": session,
            "events": [{"type": "click", "button": "left"}] * 33,
        },
        headers=auth(token),
    )

    assert bad_key.status_code == 400
    assert error_code(bad_key) == 2001
    assert bad_move.status_code == 400
    assert error_code(bad_move) == 2001
    assert too_many.status_code == 400
    assert error_code(too_many) == 2001
    assert harness.input.calls == []


def test_input_requires_session(harness) -> None:
    token = pair_device(harness)

    response = harness.client.post(
        f"{PC}/input",
        json={"session_token": "s_missing1", "events": [{"type": "click", "button": "left"}]},
        headers=auth(token),
    )

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_file_roots_and_list(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    (harness.root / "folder").mkdir()
    (harness.root / "zeta.txt").write_text("z", encoding="utf-8")
    (harness.root / "alpha.txt").write_text("a", encoding="utf-8")

    roots = harness.client.get(
        f"{PC}/files/roots",
        params={"session_token": session},
        headers=auth(token),
    )
    listing = harness.client.get(
        f"{PC}/files/list",
        params={"session_token": session, "path": str(harness.root)},
        headers=auth(token),
    )

    assert roots.status_code == 200
    assert roots.json()["roots"] == [str(harness.root)]
    assert listing.status_code == 200
    body = listing.json()
    names = [entry["name"] for entry in body["entries"]]
    assert names == ["folder", "alpha.txt", "zeta.txt"]
    assert body["entries"][0]["is_dir"] is True
    assert body["entries"][1]["size"] == 1


def test_file_list_blocks_traversal_and_system_folders(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)

    traversal = harness.client.get(
        f"{PC}/files/list",
        params={
            "session_token": session,
            "path": str(harness.root / ".." / "system"),
        },
        headers=auth(token),
    )
    system = harness.client.get(
        f"{PC}/files/list",
        params={"session_token": session, "path": str(harness.system_root)},
        headers=auth(token),
    )

    assert traversal.status_code == 403
    assert error_code(traversal) == 4002
    assert system.status_code == 403
    assert error_code(system) == 4002


def test_file_download_returns_bytes_and_blocks_large_files(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    target = harness.root / "notes.txt"
    target.write_text("hello maya", encoding="utf-8")

    response = harness.client.get(
        f"{PC}/files/download",
        params={"session_token": session, "path": str(target)},
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.content == b"hello maya"
    assert "notes.txt" in response.headers["content-disposition"]

    folder = harness.root / "folder"
    folder.mkdir()
    not_a_file = harness.client.get(
        f"{PC}/files/download",
        params={"session_token": session, "path": str(folder)},
        headers=auth(token),
    )
    assert not_a_file.status_code == 400
    assert error_code(not_a_file) == 2001


def test_file_upload_writes_inside_allowed_root(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)
    target = harness.root / "upload.bin"

    response = harness.client.put(
        f"{PC}/files/upload",
        params={"session_token": session, "path": str(target)},
        content=b"\x00\x01hello",
        headers={**auth(token), "Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["size"] == 7
    assert target.read_bytes() == b"\x00\x01hello"
    assert not list(harness.root.glob(".*.maya-*.tmp"))


def test_file_upload_blocks_outside_paths_and_missing_parent(harness) -> None:
    token = pair_device(harness)
    session = _start_session(harness, token)

    outside = harness.client.put(
        f"{PC}/files/upload",
        params={"session_token": session, "path": str(harness.root.parent / "x.txt")},
        content=b"x",
        headers=auth(token),
    )
    missing_parent = harness.client.put(
        f"{PC}/files/upload",
        params={"session_token": session, "path": str(harness.root / "nope" / "x.txt")},
        content=b"x",
        headers=auth(token),
    )

    assert outside.status_code == 403
    assert error_code(outside) == 4002
    assert missing_parent.status_code == 400
    assert error_code(missing_parent) == 2001


def test_file_routes_require_a_session(harness) -> None:
    token = pair_device(harness)

    response = harness.client.get(
        f"{PC}/files/roots",
        headers=auth(token),
    )

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_hybrid_status_and_control(harness) -> None:
    token = pair_device(harness)
    first = harness.client.get(f"{HYBRID}/status", headers=auth(token))
    takeover = harness.client.post(f"{HYBRID}/takeover", headers=auth(token))
    release = harness.client.post(f"{HYBRID}/release", headers=auth(token))

    assert first.status_code == 200
    assert first.json()["controller"] == "none"
    assert takeover.json()["controller"] == "user"
    assert takeover.json()["status"] == "done"
    assert release.json()["controller"] == "none"
    assert harness.hybrid.takeovers == 1
    assert harness.hybrid.releases == 1


def test_hybrid_tasks_are_listed(harness) -> None:
    from tests.fakes import FakeHybridTask

    token = pair_device(harness)
    harness.hybrid.tasks = [FakeHybridTask("t_1", "Summarise notes")]

    response = harness.client.get(f"{HYBRID}/status", headers=auth(token))

    assert response.status_code == 200
    assert response.json()["tasks"] == [
        {"id": "t_1", "description": "Summarise notes", "status": "queued"}
    ]


def test_health_advertises_new_capabilities(harness) -> None:
    response = harness.client.get("/api/v1/health")

    caps = response.json()["capabilities"]
    assert "file_transfer" in caps
    assert "screen" in caps
    assert "remote_input" in caps
    assert "hybrid" in caps


def test_remote_routes_require_auth(harness) -> None:
    response = harness.client.post(f"{PC}/remote/start", json={})

    assert response.status_code == 401
    assert error_code(response) == 1001

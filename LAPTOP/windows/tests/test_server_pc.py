"""Laptop-control policy, confirmation and rate-limit tests."""

from __future__ import annotations

import pytest
from custom.server import policy
from custom.server.errors import ApiError

from tests.fakes import (
    OTHER_DEVICE_ID,
    auth,
    error_code,
    make_harness,
    pair_device,
)

PC = "/api/v1/pc"


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Harness with a fake system root so temp paths stay usable."""
    system = tmp_path / "system"
    system.mkdir()
    (system / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(policy, "_system_roots", lambda: [system])
    harness = make_harness(tmp_path)
    harness.system_root = system  # type: ignore[attr-defined]
    return harness


def _command(harness, token: str, action: str, params: dict | None = None, **extra):
    body = {"action": action, "params": params or {}}
    body.update(extra)
    return harness.client.post(f"{PC}/command", json=body, headers=auth(token))


def test_status_returns_monitor_snapshot(harness) -> None:
    token = pair_device(harness)

    response = harness.client.get(f"{PC}/status", headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["cpu"]["cores"] == 8
    assert body["ram"]["percent"] == 46.4
    assert body["battery"]["percent"] == 82
    assert body["uptime_s"] == 12345


def test_allow_action_runs_without_confirmation(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "app.list")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["result"] == {"message": "done app.list"}
    assert harness.pc.calls == [("app.list", {})]


def test_ask_action_returns_single_use_token(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "app.open", {"name": "notepad"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_confirmation"
    assert body["confirm_token"].startswith("cf_")
    assert body["description"] == "Open application: notepad"
    assert body["expires_in"] == 60
    assert harness.pc.calls == []


def test_confirm_executes_exactly_once(harness) -> None:
    token = pair_device(harness)
    created = _command(harness, token, "app.open", {"name": "notepad"}).json()

    first = harness.client.post(
        f"{PC}/confirm",
        json={"confirm_token": created["confirm_token"]},
        headers=auth(token),
    )
    replay = harness.client.post(
        f"{PC}/confirm",
        json={"confirm_token": created["confirm_token"]},
        headers=auth(token),
    )

    assert first.status_code == 200
    assert first.json()["status"] == "done"
    assert harness.pc.calls == [("app.open", {"name": "notepad"})]
    assert replay.status_code == 403
    assert error_code(replay) == 4002


def test_command_with_confirm_token_executes(harness) -> None:
    token = pair_device(harness)
    created = _command(harness, token, "app.open", {"name": "notepad"}).json()

    response = harness.client.post(
        f"{PC}/command",
        json={
            "action": "app.open",
            "params": {"name": "notepad"},
            "confirm_token": created["confirm_token"],
        },
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert harness.pc.calls == [("app.open", {"name": "notepad"})]


def test_confirm_token_is_bound_to_params(harness) -> None:
    token = pair_device(harness)
    created = _command(harness, token, "app.open", {"name": "notepad"}).json()

    response = harness.client.post(
        f"{PC}/command",
        json={
            "action": "app.open",
            "params": {"name": "calc"},
            "confirm_token": created["confirm_token"],
        },
        headers=auth(token),
    )

    assert response.status_code == 403
    assert error_code(response) == 4002
    assert harness.pc.calls == []


def test_confirm_token_belongs_to_one_device(harness) -> None:
    token = pair_device(harness)
    other = pair_device(harness, device_id=OTHER_DEVICE_ID, name="Other Phone")
    created = _command(harness, token, "app.open", {"name": "notepad"}).json()

    response = harness.client.post(
        f"{PC}/confirm",
        json={"confirm_token": created["confirm_token"]},
        headers=auth(other),
    )

    assert response.status_code == 403
    assert error_code(response) == 4002
    assert harness.pc.calls == []


def test_cancel_drops_the_token(harness) -> None:
    token = pair_device(harness)
    created = _command(harness, token, "file.delete", {"path": str(harness.root / "x.txt")}).json()

    cancelled = harness.client.post(
        f"{PC}/cancel",
        json={"confirm_token": created["confirm_token"]},
        headers=auth(token),
    )
    confirmed = harness.client.post(
        f"{PC}/confirm",
        json={"confirm_token": created["confirm_token"]},
        headers=auth(token),
    )

    assert cancelled.status_code == 200
    assert cancelled.json() == {"status": "cancelled"}
    assert confirmed.status_code == 403
    assert error_code(confirmed) == 4002
    assert harness.pc.calls == []


def test_path_traversal_is_blocked(harness) -> None:
    token = pair_device(harness)
    path = str(harness.root / ".." / "system" / "secret.txt")

    response = _command(harness, token, "file.read", {"path": path})

    assert response.status_code == 403
    assert error_code(response) == 4002
    assert harness.pc.calls == []


def test_outside_allowed_root_is_blocked(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "file.read", {"path": str(harness.root.parent / "outside.txt")})

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_system_folder_is_blocked(harness) -> None:
    token = pair_device(harness)
    target = harness.system_root / "secret.txt"

    response = _command(harness, token, "file.read", {"path": str(target)})

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_relative_path_is_blocked(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "file.read", {"path": "notes.txt"})

    assert response.status_code == 403
    assert error_code(response) == 4002


def test_read_inside_root_is_allowed(harness) -> None:
    token = pair_device(harness)
    target = harness.root / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    response = _command(harness, token, "file.read", {"path": str(target)})

    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_write_over_256kb_is_rejected(harness) -> None:
    token = pair_device(harness)
    target = harness.root / "big.txt"

    response = _command(
        harness,
        token,
        "file.write",
        {"path": str(target), "content": "x" * (256 * 1024 + 1)},
    )

    assert response.status_code == 413
    assert error_code(response) == 2003


def test_write_to_folder_is_rejected(harness) -> None:
    token = pair_device(harness)
    folder = harness.root / "folder"
    folder.mkdir()

    response = _command(harness, token, "file.write", {"path": str(folder), "content": "x"})

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_denied_command_is_blocked(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "cmd.run", {"command": "format C: /q"})

    assert response.status_code == 403
    assert error_code(response) == 4003
    assert harness.pc.calls == []


def test_unknown_action_is_rejected(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "kernel.explode")

    assert response.status_code == 400
    assert error_code(response) == 2002


def test_missing_parameter_is_rejected(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "app.open")

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_shutdown_delay_bounds(harness) -> None:
    token = pair_device(harness)

    too_fast = _command(harness, token, "system.shutdown", {"delay_s": 5})
    too_slow = _command(harness, token, "system.shutdown", {"delay_s": 500})

    assert too_fast.status_code == 400
    assert error_code(too_fast) == 2001
    assert too_slow.status_code == 400
    assert error_code(too_slow) == 2001


def test_volume_bounds(harness) -> None:
    token = pair_device(harness)

    response = _command(harness, token, "system.volume", {"level": 101})

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_pc_rate_limit_is_30_per_minute(harness) -> None:
    token = pair_device(harness)

    for _ in range(30):
        assert _command(harness, token, "app.list").status_code == 200

    blocked = _command(harness, token, "app.list")

    assert blocked.status_code == 429
    assert error_code(blocked) == 1005


def test_pc_requires_auth(harness) -> None:
    response = harness.client.post(f"{PC}/confirm", json={"confirm_token": "cf_12345678"})

    assert response.status_code == 401
    assert error_code(response) == 1001


def test_execute_failure_maps_to_5000(harness) -> None:
    harness.pc.error = RuntimeError("boom")
    token = pair_device(harness)

    response = _command(harness, token, "app.list")

    assert response.status_code == 500
    assert error_code(response) == 5000


def test_confirm_token_too_short_is_2001(harness) -> None:
    token = pair_device(harness)

    response = harness.client.post(
        f"{PC}/confirm",
        json={"confirm_token": "short"},
        headers=auth(token),
    )

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_device_id_not_applicable_but_token_still_checked(harness) -> None:
    response = harness.client.get(f"{PC}/status", headers=auth("maya_nope"))

    assert response.status_code == 401
    assert error_code(response) == 1001


def test_policy_units_for_paths(tmp_path, monkeypatch) -> None:
    system = tmp_path / "system"
    system.mkdir()
    (system / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setattr(policy, "_system_roots", lambda: [system])
    root = tmp_path / "root"
    root.mkdir()

    assert policy.resolve_path(str(root / "a.txt"), [str(root)]) == root / "a.txt"

    with pytest.raises(ApiError) as no_roots:
        policy.resolve_path(str(root / "a.txt"), [])
    assert no_roots.value.code == 4002

    # System folder is refused even when listed as an allowed root.
    with pytest.raises(ApiError) as system_block:
        policy.resolve_path(str(system / "secret.txt"), [str(system)])
    assert system_block.value.code == 4002
    assert "System folders" in system_block.value.message


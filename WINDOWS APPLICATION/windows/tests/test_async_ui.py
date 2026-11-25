"""Async UI paths: monitor snapshots and phone-server start never block the UI."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QTimer

from app.settings_repository import SettingsRepository
from app.ui.pages.monitor_page import MonitorPage
from app.ui.pages.settings_page import SettingsPage


class _FakeMonitor:
    """Snapshot source whose calls can be made slow or failing on demand."""

    def __init__(self) -> None:
        self.delay = 0.0
        self.calls = 0
        self.cpu = 42.0
        self.error: Exception | None = None

    def snapshot(self) -> dict[str, Any]:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return {
            "cpu": {"percent": self.cpu, "cores": 8, "freq_mhz": 3000},
            "ram": {"total_gb": 16.0, "used_gb": 8.0, "percent": 50.0},
            "gpu": {"name": "Test GPU", "percent": 7.0},
            "npu": {"name": "Test NPU", "tops": 10.0, "percent": None},
            "battery": {"percent": 80.0, "plugged": True, "seconds_left": 3600},
            "temps": {"cpu_c": 55.0},
            "disks": [{"mount": "C:", "used_gb": 100.0, "total_gb": 500.0, "percent": 20.0}],
            "uptime_s": 1234,
        }


class _FakeServer:
    """Stand-in for `ServerService`: `start()` takes real time, no sockets."""

    host = "127.0.0.1"
    port = 8420

    def __init__(self, *, delay: float = 0.3, error: str | None = None) -> None:
        self.delay = delay
        self.error = error
        self.running = False
        self.bound_port: int | None = None
        self.starts = 0
        self.stops = 0
        self.stopped = False

    def start(self, timeout: float = 15.0) -> None:
        del timeout
        self.starts += 1
        time.sleep(self.delay)
        if self.error is not None:
            raise RuntimeError(self.error)
        self.running = True
        self.bound_port = 8421

    def stop(self, timeout: float = 5.0) -> None:
        del timeout
        self.stops += 1
        self.stopped = True
        self.running = False
        self.bound_port = None


# -- monitor page -----------------------------------------------------


@pytest.fixture
def monitor() -> _FakeMonitor:
    return _FakeMonitor()


@pytest.fixture
def monitor_page(qtbot, monitor: _FakeMonitor) -> MonitorPage:
    page = MonitorPage(monitor=monitor)
    qtbot.addWidget(page)
    page.show()
    return page


def _spin_timer(interval: int = 20) -> tuple[QTimer, list[float]]:
    """A UI-thread timer that records ticks; proves the loop keeps running."""
    ticks: list[float] = []
    timer = QTimer()
    timer.setInterval(interval)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()
    return timer, ticks


def test_first_paint_is_synchronous(monitor_page: MonitorPage, monitor: _FakeMonitor) -> None:
    assert monitor.calls == 1, "the page must paint once before the event loop runs"
    assert "42.0%" in monitor_page._cards["CPU"]._value.text()
    assert "C:" in monitor_page._disk_view.toPlainText()


def test_public_refresh_stays_synchronous(monitor_page: MonitorPage, monitor: _FakeMonitor) -> None:
    monitor.cpu = 11.0

    monitor_page.refresh()

    assert "11.0%" in monitor_page._cards["CPU"]._value.text()


def test_tick_does_not_block_the_ui_thread(
    qtbot, monitor_page: MonitorPage, monitor: _FakeMonitor
) -> None:
    monitor.delay = 0.3
    monitor.cpu = 90.0
    timer, ticks = _spin_timer()

    started = time.perf_counter()
    monitor_page._on_tick()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.1, f"timer tick blocked the UI thread for {elapsed:.3f}s"
    assert monitor_page._snapshot_busy is True
    assert "42.0%" in monitor_page._cards["CPU"]._value.text(), "old values stay until the signal"

    qtbot.wait(120)
    timer.stop()
    assert ticks, "the UI event loop must keep running while a snapshot is taken"

    qtbot.waitUntil(
        lambda: "90.0%" in monitor_page._cards["CPU"]._value.text(), timeout=3000
    )
    assert monitor_page._snapshot_busy is False


def test_overlapping_ticks_are_skipped(
    qtbot, monitor_page: MonitorPage, monitor: _FakeMonitor
) -> None:
    monitor.delay = 0.2

    assert monitor_page._request_snapshot() is True
    assert monitor_page._request_snapshot() is False
    monitor_page._on_tick()  # a timer tick during a run must be ignored

    qtbot.waitUntil(lambda: monitor_page._snapshot_busy is False, timeout=3000)
    assert monitor.calls == 2, "one snapshot from the first paint + exactly one tick"


def test_hide_stops_polling_and_show_restarts_it(
    qtbot, monitor_page: MonitorPage, monitor: _FakeMonitor
) -> None:
    monitor_page.hide()
    assert not monitor_page._timer.isActive()
    calls = monitor.calls
    qtbot.wait(160)
    assert monitor.calls == calls, "no polling while hidden"

    monitor_page.show()
    monitor_page._timer.setInterval(50)  # keep the test quick
    assert monitor_page._timer.isActive()
    qtbot.waitUntil(lambda: monitor.calls > calls, timeout=3000)


def test_snapshot_failure_keeps_previous_values(
    qtbot, monitor_page: MonitorPage, monitor: _FakeMonitor
) -> None:
    monitor.error = RuntimeError("WMI exploded")

    monitor_page._on_tick()
    qtbot.waitUntil(lambda: monitor_page._snapshot_busy is False, timeout=3000)

    assert "42.0%" in monitor_page._cards["CPU"]._value.text()
    assert monitor_page._timer.isActive(), "polling continues after a failed snapshot"

    monitor.error = None
    monitor.cpu = 55.0
    monitor_page._on_tick()
    qtbot.waitUntil(
        lambda: "55.0%" in monitor_page._cards["CPU"]._value.text(), timeout=3000
    )


# -- settings page: phone server -------------------------------------


@pytest.fixture
def fake_server() -> _FakeServer:
    return _FakeServer()


@pytest.fixture
def settings_page(qtbot, tmp_path: Path, fake_server: _FakeServer):
    path = tmp_path / "settings.yaml"
    path.write_text("ui:\n  theme: dark\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, server_factory=lambda: fake_server)
    qtbot.addWidget(page)
    page.show()
    yield page
    page.shutdown()  # never destroy the page with a live QThread


def test_start_returns_immediately_and_shows_starting(
    qtbot, settings_page: SettingsPage, fake_server: _FakeServer
) -> None:
    started = time.perf_counter()
    settings_page._server_start_btn.click()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.1, f"clicking Start blocked the UI for {elapsed:.3f}s"
    # The worker thread may not have entered start() yet; wait without blocking the UI.
    qtbot.waitUntil(lambda: fake_server.starts == 1, timeout=2000)
    assert settings_page._server_status.text() == "Status: Starting..."
    assert not settings_page._server_start_btn.isEnabled()
    assert not settings_page._server_stop_btn.isEnabled()
    assert not settings_page._server_pin_btn.isEnabled()


def test_start_keeps_ui_responsive(qtbot, settings_page: SettingsPage, fake_server: _FakeServer) -> None:
    fake_server.delay = 0.3
    timer, ticks = _spin_timer()

    settings_page._server_start_btn.click()
    qtbot.wait(120)
    timer.stop()

    assert ticks, "the UI event loop must keep running while the server starts"
    assert settings_page._server_status.text() == "Status: Starting..."


def test_start_finishes_running(qtbot, settings_page: SettingsPage, fake_server: _FakeServer) -> None:
    settings_page._server_start_btn.click()

    qtbot.waitUntil(
        lambda: "Running" in settings_page._server_status.text(), timeout=3000
    )

    assert settings_page._server_status.text() == "Status: Running on 127.0.0.1:8421"
    assert not settings_page._server_start_btn.isEnabled()
    assert settings_page._server_stop_btn.isEnabled()
    assert settings_page._server_pin_btn.isEnabled()
    qtbot.waitUntil(
        lambda: settings_page._server_start_worker is None, timeout=3000
    )


def test_start_failure_shows_error_and_allows_retry(
    qtbot, settings_page: SettingsPage, fake_server: _FakeServer
) -> None:
    fake_server.error = "port 8420 already in use"
    settings_page._server_start_btn.click()

    qtbot.waitUntil(lambda: "Error" in settings_page._server_status.text(), timeout=3000)

    assert "port 8420 already in use" in settings_page._server_status.text()
    assert settings_page._server_start_btn.isEnabled()
    assert not settings_page._server_stop_btn.isEnabled()
    assert not settings_page._server_pin_btn.isEnabled()
    qtbot.waitUntil(
        lambda: settings_page._server_start_worker is None, timeout=3000
    )

    # Retry after the failure: the same page must work again.
    fake_server.error = None
    settings_page._server_start_btn.click()
    qtbot.waitUntil(
        lambda: "Running" in settings_page._server_status.text(), timeout=3000
    )
    assert fake_server.starts == 2


def test_double_click_starts_once(
    qtbot, settings_page: SettingsPage, fake_server: _FakeServer
) -> None:
    settings_page._server_start_btn.click()
    settings_page._on_server_start()  # second click while the worker runs

    qtbot.waitUntil(
        lambda: "Running" in settings_page._server_status.text(), timeout=3000
    )
    assert fake_server.starts == 1


def test_refresh_does_not_clobber_starting(
    settings_page: SettingsPage, fake_server: _FakeServer
) -> None:
    fake_server.delay = 0.3
    settings_page._server_start_btn.click()

    settings_page._refresh_server_state()  # e.g. showEvent while the worker runs
    assert settings_page._server_status.text() == "Status: Starting..."


def test_stop_after_async_start(
    qtbot, settings_page: SettingsPage, fake_server: _FakeServer
) -> None:
    settings_page._server_start_btn.click()
    qtbot.waitUntil(
        lambda: "Running" in settings_page._server_status.text(), timeout=3000
    )

    settings_page._on_server_stop()

    assert fake_server.stopped is True
    assert settings_page._server_status.text() == "Status: Stopped"
    assert settings_page._server_start_btn.isEnabled()
    assert not settings_page._server_stop_btn.isEnabled()
    assert not settings_page._server_pin_btn.isEnabled()

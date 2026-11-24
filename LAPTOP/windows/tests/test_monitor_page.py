"""W2: monitor page cards update from snapshot; timer pauses when hidden."""

from __future__ import annotations

import pytest

from app.ui.pages.monitor_page import MonitorPage


class _FakeAdapter:
    def snapshot(self):
        return {
            "cpu": {"percent": 42.0, "cores": 8, "freq_mhz": 3000},
            "ram": {"total_gb": 16.0, "used_gb": 8.0, "percent": 50.0},
            "gpu": {"name": "Test GPU", "percent": 7.0},
            "npu": {"name": "Test NPU", "tops": 10.0, "percent": None},
            "battery": {"percent": 80.0, "plugged": True, "seconds_left": 3600},
            "temps": {"cpu_c": 55.0},
            "disks": [{"mount": "C:", "used_gb": 100.0, "total_gb": 500.0, "percent": 20.0}],
            "uptime_s": 1234,
        }


@pytest.fixture
def page(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.pages.monitor_page.MonitorAdapter", _FakeAdapter)
    p = MonitorPage()
    qtbot.addWidget(p)
    p.show()
    return p


def test_cards_populated(page: MonitorPage) -> None:
    assert "42.0%" in page._cards["CPU"]._value.text()
    assert "8.0/16.0 GB" in page._cards["RAM"]._value.text()
    assert "Test GPU" in page._cards["GPU"]._value.text()
    assert "Test NPU" in page._cards["NPU"]._value.text()
    assert "80.0%" in page._cards["Battery"]._value.text()
    assert "1234 s" in page._cards["Uptime"]._value.text()
    assert "C:" in page._disk_view.toPlainText()


def test_timer_stops_on_hide(page: MonitorPage) -> None:
    assert page._timer.isActive()
    page.hide()
    assert not page._timer.isActive()


def test_timer_starts_on_show(page: MonitorPage) -> None:
    page.hide()
    assert not page._timer.isActive()
    page.show()
    assert page._timer.isActive()

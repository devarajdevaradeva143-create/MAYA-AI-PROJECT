"""Monitoring page — CPU / RAM / GPU / NPU / battery cards + sparklines + disk usage (Phase 6)."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.monitor_service import MonitorAdapter
from app.ui.workers import MonitorSnapshotWorker

logger = logging.getLogger("maya.ui.monitor")


class MonitorCard(QFrame):
    """A single stats card: label + value + small sparkline spark."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border-radius: 8px; background-color: #14141c; margin: 4px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setObjectName("cardLabel")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._value = QLabel(subtitle)
        self._value.setObjectName("cardValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

        self._spark = QLabel("—")
        self._spark.setObjectName("cardSpark")
        self._spark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spark)

    def update_values(self, title: str, value: str, spark: str) -> None:
        self._title.setText(title)
        self._value.setText(value)
        self._spark.setText(spark)


class MonitorPage(QWidget):
    """Maya monitoring page: live system stats cards + disk list + uptime.

    The 2 s timer runs on the UI thread but only *schedules* a snapshot; the
    WMI/psutil work happens in `MonitorSnapshotWorker`, so ticking never
    freezes the window. Snapshots are always applied on the UI thread.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        monitor: MonitorAdapter | None = None,
    ) -> None:
        super().__init__(parent)
        self._monitor = monitor if monitor is not None else MonitorAdapter()
        self._snapshot_busy = False
        self._snapshot_worker: MonitorSnapshotWorker | None = None

        # History for tiny sparklines (last 30 readings)
        self._history: dict[str, deque[float]] = {
            "cpu": deque(maxlen=30),
            "ram": deque(maxlen=30),
        }
        self._phone_cards: dict[str, dict] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        # timer started in showEvent; stopped in hideEvent (no polling when hidden)

        self._build_ui()

    # -- ui -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(12)

        # --- Laptop Stats grid ---
        laptop_label = QLabel("Laptop")
        laptop_label.setObjectName("sectionTitle")
        layout.addWidget(laptop_label)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        self._cards: dict[str, MonitorCard] = {}
        card_defs = [
            ("CPU", "0%", "0%"),
            ("RAM", "0/0 GB", "0%"),
            ("GPU", "Unknown GPU", "—"),
            ("NPU", "Unknown NPU", "—"),
            ("Battery", "0%", "—"),
            ("Uptime", "0 s", "—"),
        ]
        for i, (title, value, _) in enumerate(card_defs):
            row, col = divmod(i, 3)
            card = MonitorCard(title, value)
            grid.addWidget(card, row, col)
            self._cards[title] = card

        layout.addLayout(grid, 1)

        # --- Phone devices section ---
        self._phone_section = QVBoxLayout()
        self._phone_section.setContentsMargins(0, 8, 0, 0)
        self._phone_section.setSpacing(8)

        self._phone_label = QLabel("Paired Phones")
        self._phone_label.setObjectName("sectionTitle")
        self._phone_label.setVisible(False)
        self._phone_section.addWidget(self._phone_label)

        self._phone_cards_layout = QGridLayout()
        self._phone_cards_layout.setContentsMargins(0, 0, 0, 0)
        self._phone_cards_layout.setSpacing(12)
        self._phone_section.addLayout(self._phone_cards_layout)

        layout.addLayout(self._phone_section)

        # --- Disk usage list ---
        left = QVBoxLayout()
        left.setContentsMargins(24, 0, 12, 0)
        left.setSpacing(6)

        self._disk_label = QLabel("Disk usage")
        self._disk_label.setObjectName("emptyHint")
        left.addWidget(self._disk_label)

        self._disk_view = QPlainTextEdit()
        self._disk_view.setReadOnly(True)
        self._disk_view.setMaximumHeight(120)
        self._disk_view.setPlainText("")
        left.addWidget(self._disk_view)

        left.addStretch(1)
        layout.addLayout(left, 0)

        # Connect signal
        self._update_cards_from_snapshot()

    # -- lifecycle ----------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        if not self._timer.isActive():
            self._timer.start(2000)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._timer.stop()
        super().hideEvent(event)

    # -- refresh ------------------------------------------------------

    def refresh(self) -> None:
        """Synchronous first/forced refresh (tests and existing callers).

        Blocks briefly while the snapshot is taken; periodic updates go
        through `_request_snapshot` instead.
        """
        self._refresh()

    def _refresh(self) -> None:
        """Take one snapshot on the calling thread and render it."""
        try:
            snapshot = self._monitor.snapshot()
        except Exception as exc:  # noqa: BLE001 - keep the last good values
            logger.debug("Monitor snapshot failed: %s", exc)
            return

        if not isinstance(snapshot, dict):
            logger.debug("Monitor returned an unexpected snapshot")
            return
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snap: dict[str, Any]) -> None:
        """Render a snapshot dict (UI thread only)."""
        # --- Cards ---
        cpu = snap.get("cpu") or {}
        ram = snap.get("ram") or {}
        gpu = snap.get("gpu") or {}
        npu = snap.get("npu") or {}
        battery = snap.get("battery") or {}

        cpu_pct = cpu.get("percent")
        cpu_str = f"{cpu_pct}%" if cpu_pct is not None else "—"
        if cpu_pct is not None:
            self._cards["CPU"].update_values("CPU", cpu_str, "█" * int(float(cpu_pct) / 5))
            self._history["cpu"].append(float(cpu_pct))

        ram_pct = ram.get("percent")
        ram_total = ram.get("total_gb")
        ram_used = ram.get("used_gb")
        ram_str = f"{ram_used}/{ram_total} GB" if ram_total is not None else "—"
        if ram_pct is not None:
            self._cards["RAM"].update_values("RAM", ram_str, "█" * int(float(ram_pct) / 5))
            self._history["ram"].append(float(ram_pct))

        # --- GPU ---
        gpu_name = gpu.get("name") or "Unknown GPU"
        gpu_util = gpu.get("percent")
        gpu_str = gpu_name if gpu_util is None else f"{gpu_name} ({gpu_util}%)"

        # --- NPU ---
        npu_name = npu.get("name") or "Unknown NPU"
        npu_util = npu.get("percent")
        npu_str = npu_name if npu_util is None else f"{npu_name} ({npu_util}%)"

        # --- Battery ---
        bat_pct = battery.get("percent")
        bat_str = f"{bat_pct}%" if bat_pct is not None else "—"
        bat_plugged = battery.get("plugged")
        if bat_plugged is not None:
            bat_str += " ⚡" if bat_plugged else " 🔋"

        # --- Uptime ---
        uptime_s = snap.get("uptime_s", 0)
        try:
            uptime_str = f"{int(uptime_s)} s"
        except (TypeError, ValueError):
            uptime_str = "—"

        # --- Disks ---
        disks = snap.get("disks") or []
        disk_lines = []
        for d in disks:
            disk_lines.append(
                f"{d.get('mount', '?')}: {d.get('used_gb', '?')}/{d.get('total_gb', '?')} GB ({d.get('percent', '?')}%)"
            )
        disk_text = "\n".join(disk_lines) if disk_lines else "No disk info"

        # Update cards
        cpu_bar = "█" * int(float(cpu_pct or 0) / 5) if cpu_pct is not None else "—"
        ram_bar = "█" * int(float(ram_pct or 0) / 5) if ram_pct is not None else "—"
        self._cards["CPU"].update_values("CPU", cpu_str, cpu_bar)
        self._cards["RAM"].update_values("RAM", ram_str, ram_bar)
        self._cards["GPU"].update_values("GPU", gpu_str, "—")
        self._cards["NPU"].update_values("NPU", npu_str, "—")
        self._cards["Battery"].update_values("Battery", bat_str, "—")
        self._cards["Uptime"].update_values("Uptime", uptime_str, "—")

        # Disk list
        self._disk_view.setPlainText(disk_text)

        # --- Phone devices ---
        phone_devices = snap.get("phone_devices") or []
        self._update_phone_cards(phone_devices)

    def _update_phone_cards(self, phone_devices: list[dict]) -> None:
        """Update or create cards for paired phone devices."""
        # Hide/show phone section
        has_phones = len(phone_devices) > 0
        self._phone_label.setVisible(has_phones)

        # Track existing phone cards
        existing_devices = set(self._phone_cards.keys()) if hasattr(self, '_phone_cards') else set()
        current_devices = set()

        # Initialize phone cards dict if not exists
        if not hasattr(self, '_phone_cards'):
            self._phone_cards = {}

        for i, device in enumerate(phone_devices):
            device_id = device.get("device_id", f"unknown_{i}")
            current_devices.add(device_id)

            name = device.get("name", "Phone")
            battery = device.get("battery_percent")
            storage = device.get("storage_used_percent")
            ram = device.get("ram_used_percent")
            uptime_hours = device.get("uptime_hours")

            if device_id not in self._phone_cards:
                # Create new card group for this device
                device_widget = QWidget()
                device_layout = QVBoxLayout(device_widget)
                device_layout.setContentsMargins(0, 0, 0, 0)
                device_layout.setSpacing(6)

                # Device name header
                name_label = QLabel(name)
                name_label.setObjectName("cardLabel")
                name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                device_layout.addWidget(name_label)

                # Stats grid for this device
                stats_grid = QGridLayout()
                stats_grid.setContentsMargins(0, 0, 0, 0)
                stats_grid.setSpacing(8)

                card_data = [
                    ("Battery", f"{battery}%" if battery is not None else "—"),
                    ("Storage", f"{storage}%" if storage is not None else "—"),
                    ("RAM", f"{ram}%" if ram is not None else "—"),
                    ("Uptime", f"{uptime_hours}h" if uptime_hours is not None else "—"),
                ]

                device_cards = {}
                for j, (title, value) in enumerate(card_data):
                    row, col = divmod(j, 2)
                    card = MonitorCard(title, value)
                    stats_grid.addWidget(card, row, col)
                    device_cards[title] = card

                device_layout.addLayout(stats_grid)
                self._phone_cards_layout.addWidget(device_widget, i // 2, i % 2)
                self._phone_cards[device_id] = {
                    "widget": device_widget,
                    "cards": device_cards,
                    "name_label": name_label,
                }
            else:
                # Update existing cards
                device_info = self._phone_cards[device_id]
                device_info["name_label"].setText(name)
                cards = device_info["cards"]
                if "Battery" in cards:
                    cards["Battery"].update_values("Battery", f"{battery}%" if battery is not None else "—", "—")
                if "Storage" in cards:
                    cards["Storage"].update_values("Storage", f"{storage}%" if storage is not None else "—", "—")
                if "RAM" in cards:
                    cards["RAM"].update_values("RAM", f"{ram}%" if ram is not None else "—", "—")
                if "Uptime" in cards:
                    cards["Uptime"].update_values("Uptime", f"{uptime_hours}h" if uptime_hours is not None else "—", "—")

        # Remove cards for devices no longer present
        for device_id in existing_devices - current_devices:
            device_info = self._phone_cards.pop(device_id)
            widget = device_info["widget"]
            self._phone_cards_layout.removeWidget(widget)
            widget.deleteLater()

    # -- async snapshot path ------------------------------------------

    def _on_tick(self) -> None:
        """Timer tick (UI thread): ask for a snapshot without blocking."""
        self._request_snapshot()

    def _request_snapshot(self) -> bool:
        """Queue one snapshot on the thread pool; False when one is running."""
        if self._snapshot_busy:
            return False

        self._snapshot_busy = True
        worker = MonitorSnapshotWorker(self._monitor)
        worker.signals.result.connect(self._on_snapshot)
        worker.signals.failed.connect(self._on_snapshot_failed)
        try:
            QThreadPool.globalInstance().start(worker)
        except Exception as exc:  # noqa: BLE001 - a busy pool must not freeze the UI
            self._snapshot_busy = False
            logger.debug("Could not queue monitor snapshot: %s", exc)
            return False

        self._snapshot_worker = worker
        return True

    def _on_snapshot(self, snapshot: object) -> None:
        """A worker finished (UI thread): render the snapshot, keep the old on error."""
        self._snapshot_busy = False
        self._snapshot_worker = None
        if not isinstance(snapshot, dict):
            return
        try:
            self._apply_snapshot(snapshot)
        except Exception:  # noqa: BLE001 - a bad snapshot must not crash the page
            logger.warning("Could not render monitor snapshot", exc_info=True)

    def _on_snapshot_failed(self, message: str) -> None:
        """A worker failed (UI thread): previous values stay on screen."""
        self._snapshot_busy = False
        self._snapshot_worker = None
        logger.debug("Monitor snapshot failed: %s", message)

    def _update_cards_from_snapshot(self) -> None:
        """Initial populating from a first snapshot."""
        try:
            self.refresh()
        except Exception:
            pass

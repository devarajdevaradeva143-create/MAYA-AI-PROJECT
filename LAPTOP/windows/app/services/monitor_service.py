"""Monitor adapter: existing `custom.tools.monitor` + psutil extras.

Output matches `GET /pc/status` in docs/API-CONTRACT.md. Unknown values are
None so the phone can render an em dash.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

import psutil
from custom.tools import monitor

_TEMP_CACHE: tuple[float, float | None] | None = None
_TEMP_CACHE_TTL_S = 10.0

# Optional callback to fetch phone stats from the server's token store.
# Set by the Windows app when the phone server is running.
_phone_stats_provider: Callable[[], list[dict[str, Any]]] | None = None


def set_phone_stats_provider(provider: Callable[[], list[dict[str, Any]]] | None) -> None:
    """Register a callback to fetch paired phone stats (battery, storage, RAM, uptime).
    Called from the Windows app when the phone server is running.
    """
    global _phone_stats_provider
    _phone_stats_provider = provider


def get_phone_stats() -> list[dict[str, Any]]:
    """Fetch phone stats from the registered provider, if any."""
    if _phone_stats_provider is not None:
        try:
            return _phone_stats_provider()
        except Exception:  # noqa: BLE001 - best effort
            return []
    return []


def _windows_cpu_temp() -> float | None:
    """Read CPU temperature from Windows WMI thermal-zone counters.

    psutil has no sensor support on Windows, so use the performance counter
    provider (no admin rights required). Values are tenths of Kelvin; the
    warmest zone is taken as the CPU reading. Cached because each WMI query
    costs noticeably more than the rest of the snapshot.
    """
    global _TEMP_CACHE

    if sys.platform != "win32":
        return None

    now = time.time()
    if _TEMP_CACHE is not None and now - _TEMP_CACHE[0] < _TEMP_CACHE_TTL_S:
        return _TEMP_CACHE[1]

    value: float | None = None
    try:
        import gc

        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        locator = service = rows = item = None
        try:
            locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            service = locator.ConnectServer(".", r"root\cimv2")
            rows = service.ExecQuery(
                "SELECT Name, HighPrecisionTemperature "
                "FROM Win32_PerfFormattedData_Counters_ThermalZoneInformation"
            )
            readings: list[float] = []
            for item in rows:
                raw = getattr(item, "HighPrecisionTemperature", None)
                if isinstance(raw, int) and raw > 0:
                    readings.append(raw / 10.0 - 273.15)
            if readings:
                value = round(max(readings), 1)
        finally:
            # Drop COM proxies before uninitializing so pywin32 does not warn
            # about outstanding IUnknown references.
            locator = service = rows = item = None
            gc.collect()
            pythoncom.CoUninitialize()
    except Exception:  # noqa: BLE001 - telemetry is best effort
        value = None

    if value is not None and not 0.0 < value < 120.0:
        value = None

    _TEMP_CACHE = (now, value)
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return round(float(value), 1)
    return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


class MonitorAdapter:
    """Builds the contract snapshot from existing local readings."""

    def snapshot(self) -> dict[str, Any]:
        cpu = monitor.get_cpu_usage()
        ram = monitor.get_ram_usage()
        gpu = monitor.get_gpu_info()
        npu = monitor.get_npu_info()
        battery = monitor.get_battery()
        temperature = monitor.get_temperature()

        snapshot = {
            "ts": int(time.time()),
            "cpu": {
                "percent": _number(cpu.get("usage_percent")),
                "cores": int(cpu.get("count") or (psutil.cpu_count() or 1)),
                "freq_mhz": self._cpu_freq(),
            },
            "ram": {
                "total_gb": _number(ram.get("total_gb")),
                "used_gb": _number(ram.get("used_gb")),
                "percent": _number(ram.get("percent")),
            },
            "gpu": {
                "name": _text(gpu.get("name")) or "Unknown GPU",
                "percent": None,
            },
            "npu": {
                "name": _text(npu.get("model")) or "Unknown NPU",
                "tops": _number(npu.get("tops")),
                "percent": None,
            },
            "battery": {
                "percent": _number(battery.get("percentage")),
                "plugged": battery.get("charging")
                if isinstance(battery.get("charging"), bool)
                else None,
                # psutil reports 4294967295 (unsigned -1) when the estimate is
                # unknown; the API contract only allows a sane Int32.
                "seconds_left": battery.get("secs_left")
                if isinstance(battery.get("secs_left"), int)
                and 0 < battery["secs_left"] < 2**31 - 1
                else None,
            },
            "temps": {"cpu_c": self._cpu_temp_c(temperature)},
            "disks": self._disks(),
            "uptime_s": self._uptime(),
        }

        # Include paired phone stats if available
        phone_stats = get_phone_stats()
        if phone_stats:
            snapshot["phone_devices"] = phone_stats

        return snapshot

    @staticmethod
    def _cpu_temp_c(fallback: dict[str, Any]) -> float | None:
        wmi = _windows_cpu_temp()
        if wmi is not None:
            return wmi
        return _number(fallback.get("current"))

    @staticmethod
    def _cpu_freq() -> int | None:
        try:
            freq = psutil.cpu_freq()
            return int(freq.current) if freq and freq.current else None
        except Exception:  # noqa: BLE001 - telemetry is best effort
            return None

    @staticmethod
    def _disks() -> list[dict[str, Any]]:
        disks: list[dict[str, Any]] = []
        try:
            partitions = psutil.disk_partitions(all=False)
        except Exception:  # noqa: BLE001
            return disks

        for partition in partitions:
            if "cdrom" in partition.opts.lower():
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except OSError:
                continue
            disks.append(
                {
                    "mount": partition.mountpoint,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "percent": round(usage.percent, 1),
                }
            )
        return disks

    @staticmethod
    def _uptime() -> int:
        try:
            return max(0, int(time.time() - psutil.boot_time()))
        except Exception:  # noqa: BLE001
            return 0

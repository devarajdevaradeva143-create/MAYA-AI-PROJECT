"""Maya AI system monitoring tools.

Reports CPU/GPU/NPU usage, RAM, temperature, battery, and SSD health.
All data is read locally — nothing leaves the laptop.

Per AGENTS.md: biometrics local only, personal details safe.
"""

import os
import shutil
import sys
import threading
import time
from typing import Dict, Any, Optional, Callable, List

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ── CPU ────────────────────────────────────────────────────────────────────

def get_cpu_usage() -> Dict[str, Any]:
    """Return CPU usage percentage."""
    if not HAS_PSUTIL:
        return {"error": "psutil not available"}
    try:
        percent = psutil.cpu_percent(interval=1)
        return {"usage_percent": percent, "count": psutil.cpu_count() or 1}
    except Exception:
        return {"error": "could not read CPU"}


# ── RAM ────────────────────────────────────────────────────────────────────

def get_ram_usage() -> Dict[str, Any]:
    """Return RAM usage: total, used, free, percent."""
    if not HAS_PSUTIL:
        return {"error": "psutil not available"}
    try:
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024 ** 3), 1),
            "used_gb": round(mem.used / (1024 ** 3), 1),
            "free_gb": round(mem.available / (1024 ** 3), 1),
            "percent": mem.percent,
        }
    except Exception:
        return {"error": "could not read RAM"}


# ── GPU (AMD) ─────────────────────────────────────────────────────────────

_VIDEO_NAME_CACHE: Optional[tuple[float, str]] = None
_VIDEO_NAME_TTL_S = 60.0


def _windows_video_controller_names() -> str:
    """Return video controller names, cached: WMI queries are expensive.

    Windows 11 removed ``wmic``; use the PowerShell CIM cmdlet when absent.
    """
    global _VIDEO_NAME_CACHE

    now = time.time()
    if _VIDEO_NAME_CACHE is not None and now - _VIDEO_NAME_CACHE[0] < _VIDEO_NAME_TTL_S:
        return _VIDEO_NAME_CACHE[1]

    text = ""
    try:
        if shutil.which("wmic"):
            text = os.popen("wmic path win32_VideoController get name,driver_version").read()
        else:
            text = os.popen(
                'powershell -NoProfile -Command "'
                "Get-CimInstance Win32_VideoController | "
                "ForEach-Object { $_.Name }"
                '"'
            ).read()
    except Exception:
        text = ""

    _VIDEO_NAME_CACHE = (now, text)
    return text


def get_gpu_info() -> Dict[str, Any]:
    """Return AMD GPU info (Radeon 840M etc.). Try amdsmi first, then psutil."""
    if not HAS_PSUTIL:
        return {"error": "psutil not available"}

    # Try amdsmi first (AMD GPU metrics)
    try:
        import amdsmi

        gpu_count = amdsmi.get_gpu_count()
        if gpu_count > 0:
            for i in range(gpu_count):
                try:
                    gpu = amdsmi.gpu_handle_to_device_handle(i)
                    info = amdsmi.get_gpu_info(gpu)
                    return {
                        "vendor": "amd",
                        "name": info.get("gpu_name", "AMD GPU"),
                        "vram_gb": round(info.get("vram", 0) / (1024 ** 3), 1)
                        if info.get("vram")
                        else 0.0,
                        "driver": info.get("gpu_drive_version", "unknown"),
                    }
                except Exception:
                    continue
    except ImportError:
        pass

    # Fallback: try psutil (may not have GPU info)
    try:
        # psutil doesn't directly give GPU, but we can check
        if sys.platform == "win32":
            # On Windows, check if Radeon software is present
            result = _windows_video_controller_names()
            if "Radeon" in result or "AMD" in result:
                name = next(
                    (line.strip() for line in result.splitlines() if line.strip()),
                    "AMD Radeon GPU",
                )
                return {
                    "vendor": "amd",
                    "name": name[:80],
                    "note": "Radeon GPU detected via WMI",
                    "detail": result.strip()[:200],
                }
    except Exception:
        pass

    # Final fallback for your laptop's Radeon 840M
    return {
        "vendor": "amd",
        "name": "Radeon 840M (integrated)",
        "vram_gb": 0.0,
        "note": "VRAM shared with system RAM; full info via amdsmi or AMD Adrenalin",
    }


# ── NPU (Ryzen AI) ───────────────────────────────────────────────────────

def get_npu_info() -> Dict[str, Any]:
    """Return NPU info for Ryzen AI hardware.

    Your laptop: Ryzen AI 5 340 → 50 TOPS.
    """
    # Check for Ryzen AI / NPU via cpupower or sysfs or just report known specs
    npu_details = {
        "vendor": "amd",
        "model": "Ryzen AI 5 340",
        "tops": 50,
        "mode": "NPU acceleration available",
    }

    # Try to detect if NPU is accessible
    if HAS_PSUTIL:
        try:
            # Check for amdsmi NPU support
            import amdsmi
            gpu_count = amdsmi.get_gpu_count()
            npu_details["accessible"] = gpu_count > 0
        except Exception:
            npu_details["accessible"] = False
    else:
        npu_details["accessible"] = False

    # Also check environment variable or common paths
    npu_paths = [
        "/sys/bus/i2c/devices",
        "/sys/class/asic",
    ]
    for p in npu_paths:
        if os.path.exists(p):
            npu_details["sysfs_exists"] = True
            break

    return npu_details


# ── Temperature ────────────────────────────────────────────────────────────

def get_temperature() -> Dict[str, Any]:
    """Return CPU/GPU temperature if available."""
    if not HAS_PSUTIL:
        return {"note": "install psutil with: uv pip install psutil", "value": "N/A"}

    try:
        # Try to get temperature sensors
        temps = psutil.sensors_temperatures()
        if temps:
            # Return first available temp sensor
            for name, entries in temps.items():
                if entries:
                    entry = entries[0]
                    return {
                        "sensor": name,
                        "label": entry.label or name,
                        "current": entry.current,
                        "high": entry.high,
                        "critical": entry.critical,
                    }
        # If no temperature sensors, check if we're on Windows without sensors
        return {"note": "no temperature sensors found", "value": "N/A", "platform": sys.platform}
    except Exception as e:
        return {"note": f"could not read temperature: {e}", "value": "N/A"}


# ── Battery ────────────────────────────────────────────────────────────────

def get_battery() -> Dict[str, Any]:
    """Return battery percentage and charging status."""
    if not HAS_PSUTIL:
        return {"note": "install psutil", "percentage": "N/A", "charging": "N/A"}

    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percentage": battery.percent,
                "charging": battery.power_plugged,
                "secs_left": battery.secsleft if battery.secsleft != -1 else None,
            }
        return {"percentage": "N/A (desktop)", "charging": "N/A", "note": "no battery found"}
    except Exception as e:
        return {"note": f"could not read battery: {e}", "percentage": "N/A", "charging": "N/A"}


# ── SSD Health ─────────────────────────────────────────────────────────────

def get_ssd_health() -> Dict[str, Any]:
    """Return SSD health status.

    Note: Full SMART read requires root/admin or specific tools.
    """
    if not HAS_PSUTIL:
        return {
            "note": "install psutil: uv pip install psutil",
            "health": "unknown",
            "detail": "Use OS disk management tools for full SSD health",
        }

    try:
        # psutil doesn't directly give SSD SMART data
        # Try common approaches
        import subprocess

        # Try smartctl (Linux)
        result = subprocess.run(
            ["smartctl", "-H", "/dev/sda"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            line = [entry for entry in result.stdout.splitlines() if "SMART" in entry.upper()]
            if "PASSED" in line[0].upper() if line else False:
                return {"health": "good", "tool": "smartctl", "detail": result.stdout[:200]}

        # Try wmic on Windows
        if sys.platform == "win32":
            wmic_result = subprocess.run(
                ["wmic", "diskdrive", "get", "status"], capture_output=True, text=True, timeout=5
            )
            status_line = wmic_result.stdout.strip()
            if "OK" in status_line.upper():
                return {"health": "good", "tool": "wmic", "detail": status_line}

        # Fallback
        return {
            "health": "check",
            "note": "Run 'smartctl -a /dev/sda' or check Windows Disk Management",
            "detail": "SMART data not auto-available",
        }
    except Exception as e:
        return {"note": f"could not check SSD: {e}", "health": "unknown"}


# ── Full report ────────────────────────────────────────────────────────────

def get_full_report() -> str:
    """Return a formatted full system report string."""
    lines = []
    lines.append("=" * 50)
    lines.append("MAYA AI — System Monitor Report")
    lines.append("=" * 50)
    lines.append("")

    # CPU
    cpu = get_cpu_usage()
    lines.append("CPU:")
    if "error" in cpu:
        lines.append(f"  {cpu['error']}")
    else:
        lines.append(f"  Usage: {cpu['usage_percent']}%")
        lines.append(f"  Cores: {cpu['count']}")
    lines.append("")

    # RAM
    ram = get_ram_usage()
    lines.append("RAM:")
    if "error" in ram:
        lines.append(f"  {ram['error']}")
    else:
        lines.append(f"  Used: {ram['used_gb']} GB / {ram['total_gb']} GB")
        lines.append(f"  Free: {ram['free_gb']} GB")
        lines.append(f"  Percent: {ram['percent']}%")
    lines.append("")

    # GPU
    lines.append("GPU:")
    gpu = get_gpu_info()
    if "error" in gpu:
        lines.append(f"  {gpu['error']}")
    else:
        lines.append(f"  Vendor: {gpu.get('vendor', 'unknown')}")
        lines.append(f"  Name: {gpu.get('name', 'unknown')}")
        lines.append(f"  VRAM: {gpu.get('vram_gb', 0)} GB")
        if "note" in gpu:
            lines.append(f"  Note: {gpu['note']}")
    lines.append("")

    # NPU
    lines.append("NPU:")
    npu = get_npu_info()
    lines.append(f"  Model: {npu.get('model', 'unknown')}")
    lines.append(f"  TOPS: {npu.get('tops', 'unknown')}")
    lines.append(f"  Vendor: {npu.get('vendor', 'unknown')}")
    lines.append(f"  Accessible: {npu.get('accessible', 'unknown')}")
    if "note" in npu:
        lines.append(f"  Note: {npu['note']}")
    lines.append("")

    # Temperature
    lines.append("Temperature:")
    temp = get_temperature()
    if "value" in temp and temp["value"] != "N/A" and "note" not in temp:
        lines.append(f"  Current: {temp['current']}°C")
    else:
        lines.append(f"  {temp.get('note', 'N/A')}")
    lines.append("")

    # Battery
    lines.append("Battery:")
    batt = get_battery()
    if "note" in batt:
        lines.append(f"  {batt['note']}")
    else:
        lines.append(f"  Percentage: {batt['percentage']}%")
        lines.append(f"  Charging: {batt['charging']}")
    lines.append("")

    # SSD
    lines.append("SSD Health:")
    ssd = get_ssd_health()
    lines.append(f"  {ssd.get('note', ssd.get('health', 'unknown'))}")
    lines.append("")

    lines.append("=" * 50)
    lines.append("End of report")
    lines.append("=" * 50)

    return "\n".join(lines)


# ── Threshold alerts ─────────────────────────────────────────────────────────

class MonitorAlert:
    """A single threshold alert raised by the monitor loop."""

    def __init__(
        self,
        metric: str,
        value: Any,
        threshold: Any,
        message: str,
    ) -> None:
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.message = message
        self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def __str__(self) -> str:
        return (
            f"[ALERT] {self.timestamp} — {self.metric}: {self.value} "
            f"(threshold: {self.threshold}) — {self.message}"
        )


# Default thresholds (overridden by settings.yaml ``monitor`` section).
DEFAULT_THRESHOLDS = {
    "cpu_percent": 80,
    "ram_percent": 85,
    "temp_celsius": 85,
    "battery_low_percent": 20,
    "disk_percent": 90,
}


def load_thresholds() -> Dict[str, Any]:
    """Read monitor thresholds from settings.yaml ``monitor`` section."""
    from ..config import load_settings

    settings = load_settings()
    monitor_cfg = settings.get("monitor", {}) if isinstance(settings, dict) else {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    if isinstance(monitor_cfg, dict):
        thresholds.update(monitor_cfg)
    return thresholds


def check_thresholds(thresholds: Dict[str, Any] | None = None) -> List[MonitorAlert]:
    """Check current system values against thresholds and return alerts.

    Args:
        thresholds: Dict of metric -> threshold value. If None, loads from
            settings.yaml.

    Returns:
        List of MonitorAlert objects for any threshold breaches.
    """
    if thresholds is None:
        thresholds = load_thresholds()

    alerts: List[MonitorAlert] = []

    # CPU
    cpu = get_cpu_usage()
    if "error" not in cpu:
        cpu_pct = cpu.get("usage_percent", 0)
        if cpu_pct >= thresholds.get("cpu_percent", 80):
            alerts.append(
                MonitorAlert(
                    "CPU",
                    f"{cpu_pct}%",
                    f">= {thresholds['cpu_percent']}%",
                    "CPU usage is high — close unused apps or processes",
                )
            )

    # RAM
    ram = get_ram_usage()
    if "error" not in ram:
        ram_pct = ram.get("percent", 0)
        if ram_pct >= thresholds.get("ram_percent", 85):
            alerts.append(
                MonitorAlert(
                    "RAM",
                    f"{ram_pct}%",
                    f">= {thresholds['ram_percent']}%",
                    "RAM usage is high — close unused apps",
                )
            )

    # Temperature
    temp = get_temperature()
    if temp.get("value") not in (None, "N/A") and "note" not in temp:
        temp_val = temp.get("current")
        if temp_val is not None and temp_val >= thresholds.get("temp_celsius", 85):
            alerts.append(
                MonitorAlert(
                    "Temperature",
                    f"{temp_val}°C",
                    f">= {thresholds['temp_celsius']}°C",
                    "System is running hot — give it a rest",
                )
            )

    # Battery
    batt = get_battery()
    if batt.get("percentage") not in (None, "N/A") and "note" not in batt:
        batt_pct = batt.get("percentage", 100)
        charging = batt.get("charging", False)
        if (
            not charging
            and batt_pct <= thresholds.get("battery_low_percent", 20)
        ):
            alerts.append(
                MonitorAlert(
                    "Battery",
                    f"{batt_pct}%",
                    f"<= {thresholds['battery_low_percent']}%",
                    "Battery is low — plug in charger",
                )
            )

    # Disk (SSD health check — use usage via psutil)
    if HAS_PSUTIL:
        try:
            disk = psutil.disk_usage("/")
            disk_pct = disk.percent
            if disk_pct >= thresholds.get("disk_percent", 90):
                alerts.append(
                    MonitorAlert(
                        "Disk",
                        f"{disk_pct}%",
                        f">= {thresholds['disk_percent']}%",
                        "Disk space is low — free up some space",
                    )
                )
        except Exception:
            pass

    return alerts


# ── Background monitor loop ─────────────────────────────────────────────────

class MonitorLoop:
    """Background monitor loop that checks thresholds on an interval.

    Runs in a daemon thread. Calls ``on_alert`` whenever a threshold is breached.
    Use ``start()`` / ``stop()`` to control it. Silent by design — the CLI
    layer is responsible for printing.
    """

    def __init__(
        self,
        interval: float = 30.0,
        on_alert: Optional[Callable[[MonitorAlert], None]] = None,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.interval = interval
        self.on_alert = on_alert
        self.thresholds = thresholds or load_thresholds()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False

    @property
    def running(self) -> bool:
        """Return True if the loop is currently running."""
        return self._running

    def start(self) -> None:
        """Start the background monitoring loop (daemon thread)."""
        if self._running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._stop.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        """Internal loop: check thresholds every ``interval`` seconds."""
        while not self._stop.is_set():
            try:
                alerts = check_thresholds(self.thresholds)
                for alert in alerts:
                    if self.on_alert:
                        self.on_alert(alert)
            except Exception:
                # Never crash the monitor loop — log internally only.
                pass
            self._stop.wait(self.interval)


# Module-level default monitor loop (can be imported and started by the CLI).
monitor_loop = MonitorLoop()

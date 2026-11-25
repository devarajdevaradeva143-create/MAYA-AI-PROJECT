"""Maya AI Connection Manager.

Manages four connection types used by Maya AI (spec: docs/REQUIREMENTS.md §11):

    1. Wi-Fi
    2. Mobile Hotspot
    3. Bluetooth
    4. Internet

Responsibilities (laptop side, Windows):
    - Discover available connections.
    - Check connection status (connected, ssid/name, ip, signal, latency).
    - Connect / disconnect securely.
    - Retry on drop with exponential backoff.
    - Switch connection type on demand (conflict-free).
    - Notify listeners on status change.

This module is LOCAL only — it inspects the laptop's own network state.
It never sends personal data anywhere. It never auto-connects to a new
device without an explicit user action (pairing handled by devices.py).

Design:
    - Backends are injectable (see `Backend` protocol) so the same code runs
      on Windows, and in tests (MockBackend).
    - `SystemBackend` is the default and uses psutil + OS commands.
    - All blocking OS calls go through the backend; the manager itself is
      pure logic + retry + events.
"""

from __future__ import annotations

import platform
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol


class ConnectionType(str, Enum):
    WIFI = "wifi"
    HOTSPOT = "hotspot"
    BLUETOOTH = "bluetooth"
    INTERNET = "internet"
    NONE = "none"


class ConnectionStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class ConnectionInfo:
    """Snapshot of a single connection type."""
    type: ConnectionType
    status: ConnectionStatus = ConnectionStatus.UNKNOWN
    name: str = ""          # SSID / device name / interface
    ip: str = ""
    signal: Optional[int] = None   # 0..100 where applicable
    latency_ms: Optional[int] = None
    error: str = ""
    last_checked: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

    def is_connected(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED


@dataclass
class SwitchResult:
    ok: bool
    from_type: ConnectionType
    to_type: ConnectionType
    message: str = ""


# ── Backend protocol ────────────────────────────────────────────────────────


class Backend(Protocol):
    """OS-specific network probing. Inject a mock in tests."""

    def list_interfaces(self) -> List[Dict[str, Any]]:
        """Return list of {name, type, ip, up} dicts."""
        ...

    def wifi_status(self) -> ConnectionInfo:
        ...

    def wifi_scan(self) -> List[str]:
        """Return list of SSID strings visible."""
        ...

    def hotspot_status(self) -> ConnectionInfo:
        ...

    def bluetooth_status(self) -> ConnectionInfo:
        ...

    def bluetooth_scan(self) -> List[str]:
        """Return list of nearby device names/addresses."""
        ...

    def internet_status(self) -> ConnectionInfo:
        ...


# ── System backend (default) ────────────────────────────────────────────────


class SystemBackend:
    """Real OS backend using psutil + platform commands."""

    def __init__(self) -> None:
        try:
            import psutil
            self._psutil = psutil
            self._has_psutil = True
        except ImportError:
            self._psutil = None
            self._has_psutil = False
        self._system = platform.system().lower()

    # -- helpers --

    def _run(self, cmd: List[str], timeout: int = 8) -> Optional[str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return (r.stdout or "").strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _first_ipv4(self) -> str:
        if not self._has_psutil:
            return ""
        for _name, addrs in self._psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    return a.address
        return ""

    def list_interfaces(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self._has_psutil:
            return out
        stats = self._psutil.net_if_stats()
        addrs = self._psutil.net_if_addrs()
        for name, st in stats.items():
            ip = ""
            for a in addrs.get(name, []):
                if a.family == socket.AF_INET:
                    ip = a.address
                    break
            out.append({"name": name, "up": bool(st.isup), "ip": ip})
        return out

    # -- wifi --

    def wifi_status(self) -> ConnectionInfo:
        info = ConnectionInfo(type=ConnectionType.WIFI)
        # Try platform-specific.
        if self._system == "windows":
            out = self._run(["netsh", "wlan", "show", "interfaces"])
            if out:
                ssid = ""
                signal = None
                for line in out.splitlines():
                    line = line.strip()
                    if line.lower().startswith("ssid") and ":" in line and "bssid" not in line.lower():
                        ssid = line.split(":", 1)[1].strip()
                    if line.lower().startswith("signal"):
                        try:
                            signal = int(line.split(":", 1)[1].strip().rstrip("%"))
                        except ValueError:
                            pass
                if ssid:
                    info.status = ConnectionStatus.CONNECTED
                    info.name = ssid
                    info.signal = signal
                    info.ip = self._first_ipv4()
            else:
                info.status = ConnectionStatus.DISCONNECTED
        elif self._system == "linux":
            # nmcli
            out = self._run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"])
            connected_ssid = ""
            signal = None
            if out:
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 3 and parts[0] == "yes":
                        connected_ssid = parts[1]
                        try:
                            signal = int(parts[2])
                        except ValueError:
                            pass
                        break
            if connected_ssid:
                info.status = ConnectionStatus.CONNECTED
                info.name = connected_ssid
                info.signal = signal
                info.ip = self._first_ipv4()
            else:
                info.status = ConnectionStatus.DISCONNECTED
        else:
            # Unknown OS — fall back to "any non-loopback interface up"
            if self._first_ipv4():
                info.status = ConnectionStatus.CONNECTED
                info.ip = self._first_ipv4()
            else:
                info.status = ConnectionStatus.DISCONNECTED
        info.last_checked = time.time()
        return info

    def wifi_scan(self) -> List[str]:
        if self._system == "windows":
            out = self._run(["netsh", "wlan", "show", "networks"])
            ssids: List[str] = []
            if out:
                for line in out.splitlines():
                    line = line.strip()
                    if line.lower().startswith("ssid") and ":" in line:
                        name = line.split(":", 1)[1].strip()
                        if name and name not in ssids:
                            ssids.append(name)
            return ssids
        if self._system == "linux":
            out = self._run(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"])
            if not out:
                return []
            return [s for s in (x.strip() for x in out.splitlines()) if s]
        return []

    # -- hotspot --

    def hotspot_status(self) -> ConnectionInfo:
        info = ConnectionInfo(type=ConnectionType.HOTSPOT)
        # Hotspot = this machine is sharing its connection. Detect via interface name hints.
        names = [i["name"].lower() for i in self.list_interfaces()]
        hotspot_hints = ("hotspot", "ap", "shared", "microsoft wifi direct")
        active = any(any(h in n for h in hotspot_hints) for n in names)
        if active:
            info.status = ConnectionStatus.CONNECTED
            info.name = "hotspot"
            info.ip = self._first_ipv4()
        else:
            info.status = ConnectionStatus.DISCONNECTED
        info.last_checked = time.time()
        return info

    # -- bluetooth --

    def bluetooth_status(self) -> ConnectionInfo:
        info = ConnectionInfo(type=ConnectionType.BLUETOOTH)
        # Best-effort: check if a bluetooth adapter exists & is up.
        if self._system == "linux":
            out = self._run(["bluetoothctl", "show"])
            if out and "Powered: yes" in out:
                info.status = ConnectionStatus.CONNECTED
                info.name = "bluetooth-adapter"
            else:
                info.status = ConnectionStatus.DISCONNECTED
        elif self._system == "windows":
            # PowerShell query
            out = self._run(["powershell", "-NoProfile", "-Command",
                            "Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -eq 'OK'} | Select-Object -First 1 -ExpandProperty FriendlyName"])
            if out:
                info.status = ConnectionStatus.CONNECTED
                info.name = out.splitlines()[0].strip() if out.splitlines() else "bluetooth"
            else:
                info.status = ConnectionStatus.DISCONNECTED
        else:
            info.status = ConnectionStatus.UNKNOWN
        info.last_checked = time.time()
        return info

    def bluetooth_scan(self) -> List[str]:
        if self._system == "linux":
            out = self._run(["bluetoothctl", "devices"], timeout=10)
            if not out:
                return []
            devs: List[str] = []
            for line in out.splitlines():
                # "Device XX:XX:XX:XX:XX:XX Name"
                parts = line.split(" ", 2)
                if len(parts) == 3 and parts[0] == "Device":
                    devs.append(parts[2])
            return devs
        if self._system == "windows":
            out = self._run(["powershell", "-NoProfile", "-Command",
                            "Get-PnpDevice -Class Bluetooth | Where-Object {$_.Status -eq 'OK'} | Select-Object -ExpandProperty FriendlyName"])
            if not out:
                return []
            return [x.strip() for x in out.splitlines() if x.strip()]
        return []

    # -- internet --

    def internet_status(self) -> ConnectionInfo:
        info = ConnectionInfo(type=ConnectionType.INTERNET)
        # Check reachability of a well-known endpoint (timeout short, no personal data).
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            info.status = ConnectionStatus.CONNECTED
            info.name = "internet"
            info.latency_ms = None
        except OSError:
            info.status = ConnectionStatus.DISCONNECTED
        info.ip = self._first_ipv4() if info.status == ConnectionStatus.CONNECTED else ""
        info.last_checked = time.time()
        return info


# ── Connection Manager ──────────────────────────────────────────────────────


class ConnectionManager:
    """High-level manager with retry, switching, and events.

    Usage:
        cm = ConnectionManager()                       # uses SystemBackend
        cm = ConnectionManager(backend=MockBackend())   # tests
        cm.on_status_change(lambda info: print(info))
        cm.detect_available()
        cm.connect(ConnectionType.WIFI)
        cm.switch(ConnectionType.BLUETOOTH)
    """

    def __init__(
        self,
        backend: Optional[Backend] = None,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend: Backend = backend if backend is not None else SystemBackend()
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self._sleep = sleep_fn
        self._listeners: List[Callable[[ConnectionInfo], None]] = []
        self._lock = threading.RLock()
        self._active: ConnectionType = ConnectionType.NONE
        self._statuses: Dict[ConnectionType, ConnectionInfo] = {}
        self._last_error: str = ""

    # -- events --

    def on_status_change(self, fn: Callable[[ConnectionInfo], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def _emit(self, info: ConnectionInfo) -> None:
        for fn in list(self._listeners):
            try:
                fn(info)
            except Exception:
                pass

    # -- discovery --

    def detect_available(self) -> List[ConnectionType]:
        """Return connection types that appear usable right now."""
        available: List[ConnectionType] = []
        try:
            if self.backend.wifi_status().status in (ConnectionStatus.CONNECTED, ConnectionStatus.DISCONNECTED):
                available.append(ConnectionType.WIFI)
        except Exception:
            pass
        try:
            # hotspot "available" means the feature exists; treat as available always
            available.append(ConnectionType.HOTSPOT)
        except Exception:
            pass
        try:
            bt = self.backend.bluetooth_status()
            if bt.status != ConnectionStatus.UNKNOWN:
                available.append(ConnectionType.BLUETOOTH)
        except Exception:
            pass
        try:
            available.append(ConnectionType.INTERNET)
        except Exception:
            pass
        return available

    def scan(self, ctype: ConnectionType) -> List[str]:
        """Scan for nearby targets for a connection type."""
        if ctype == ConnectionType.WIFI:
            return self.backend.wifi_scan()
        if ctype == ConnectionType.BLUETOOTH:
            return self.backend.bluetooth_scan()
        return []

    # -- status --

    def status(self, ctype: Optional[ConnectionType] = None) -> Any:
        if ctype is None:
            return {t.value: self._status_one(t).to_dict() for t in ConnectionType if t != ConnectionType.NONE}
        return self._status_one(ctype)

    def _status_one(self, ctype: ConnectionType) -> ConnectionInfo:
        with self._lock:
            if ctype == ConnectionType.WIFI:
                info = self.backend.wifi_status()
            elif ctype == ConnectionType.HOTSPOT:
                info = self.backend.hotspot_status()
            elif ctype == ConnectionType.BLUETOOTH:
                info = self.backend.bluetooth_status()
            elif ctype == ConnectionType.INTERNET:
                info = self.backend.internet_status()
            else:
                info = ConnectionInfo(type=ctype, status=ConnectionStatus.UNKNOWN)
            self._statuses[ctype] = info
            self._emit(info)
            return info

    def refresh_all(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for t in (ConnectionType.WIFI, ConnectionType.HOTSPOT, ConnectionType.BLUETOOTH, ConnectionType.INTERNET):
            info = self._status_one(t)
            out[t.value] = info.to_dict()
        return out

    # -- connect / disconnect --

    def connect(self, ctype: ConnectionType, target: Optional[str] = None) -> ConnectionInfo:
        """Attempt to connect (with retry). Returns final status.

        Note: Actual OS-level connect commands (nmcli connect, netsh) are
        backend-dependent; this manager records intent + verifies via status.
        For Wi-Fi with a target SSID, the backend is expected to handle it;
        here we verify reachability after attempts.
        """
        with self._lock:
            self._active = ctype
        info = ConnectionInfo(type=ctype, status=ConnectionStatus.CONNECTING)
        self._emit(info)

        last: ConnectionInfo = info
        for attempt in range(1, self.max_retries + 1):
            try:
                last = self._status_one(ctype)
                if last.is_connected():
                    with self._lock:
                        self._active = ctype
                    return last
            except Exception as e:
                last = ConnectionInfo(type=ctype, status=ConnectionStatus.FAILED, error=str(e))
            if attempt < self.max_retries:
                self._sleep(self.base_backoff * (2 ** (attempt - 1)))
        # failed
        failed = ConnectionInfo(type=ctype, status=ConnectionStatus.FAILED,
                                error=last.error or "connection failed")
        with self._lock:
            self._statuses[ctype] = failed
        self._emit(failed)
        return failed

    def disconnect(self, ctype: Optional[ConnectionType] = None) -> ConnectionInfo:
        ctype = ctype or self._active
        if ctype == ConnectionType.NONE:
            return ConnectionInfo(type=ConnectionType.NONE, status=ConnectionStatus.DISCONNECTED)
        with self._lock:
            if self._active == ctype:
                self._active = ConnectionType.NONE
        info = ConnectionInfo(type=ctype, status=ConnectionStatus.DISCONNECTED)
        self._statuses[ctype] = info
        self._emit(info)
        return info

    # -- switch --

    def switch(self, to_type: ConnectionType) -> SwitchResult:
        """Switch active connection type. Disconnects current first."""
        with self._lock:
            from_type = self._active
        if from_type == to_type:
            info = self._status_one(to_type)
            return SwitchResult(ok=info.is_connected(), from_type=from_type,
                               to_type=to_type, message="already active")
        # disconnect current
        if from_type != ConnectionType.NONE:
            self.disconnect(from_type)
        # connect new
        result_info = self.connect(to_type)
        ok = result_info.is_connected()
        return SwitchResult(ok=ok, from_type=from_type, to_type=to_type,
                           message="ok" if ok else (result_info.error or "failed"))

    # -- convenience --

    @property
    def active(self) -> ConnectionType:
        with self._lock:
            return self._active

    def summary(self) -> Dict[str, Any]:
        return {
            "active": self.active.value,
            "statuses": {t.value: self._statuses.get(t, ConnectionInfo(type=t)).to_dict()
                         for t in (ConnectionType.WIFI, ConnectionType.HOTSPOT,
                                   ConnectionType.BLUETOOTH, ConnectionType.INTERNET)},
        }


# ── Mock backend (tests / dev) ──────────────────────────────────────────────


class MockBackend:
    """In-memory backend for tests. Configure return values per method."""

    def __init__(self) -> None:
        self.interfaces: List[Dict[str, Any]] = []
        self.wifi: ConnectionInfo = ConnectionInfo(type=ConnectionType.WIFI,
                                                   status=ConnectionStatus.DISCONNECTED)
        self.hotspot: ConnectionInfo = ConnectionInfo(type=ConnectionType.HOTSPOT,
                                                      status=ConnectionStatus.DISCONNECTED)
        self.bluetooth: ConnectionInfo = ConnectionInfo(type=ConnectionType.BLUETOOTH,
                                                       status=ConnectionStatus.DISCONNECTED)
        self.internet: ConnectionInfo = ConnectionInfo(type=ConnectionType.INTERNET,
                                                      status=ConnectionStatus.DISCONNECTED)
        self.wifi_ssids: List[str] = []
        self.bt_devices: List[str] = []
        self.raise_on: Optional[str] = None

    def _maybe_raise(self, name: str) -> None:
        if self.raise_on == name:
            raise RuntimeError(f"mock failure: {name}")

    def list_interfaces(self) -> List[Dict[str, Any]]:
        self._maybe_raise("list_interfaces")
        return list(self.interfaces)

    def wifi_status(self) -> ConnectionInfo:
        self._maybe_raise("wifi_status")
        return self.wifi

    def wifi_scan(self) -> List[str]:
        self._maybe_raise("wifi_scan")
        return list(self.wifi_ssids)

    def hotspot_status(self) -> ConnectionInfo:
        self._maybe_raise("hotspot_status")
        return self.hotspot

    def bluetooth_status(self) -> ConnectionInfo:
        self._maybe_raise("bluetooth_status")
        return self.bluetooth

    def bluetooth_scan(self) -> List[str]:
        self._maybe_raise("bluetooth_scan")
        return list(self.bt_devices)

    def internet_status(self) -> ConnectionInfo:
        self._maybe_raise("internet_status")
        return self.internet

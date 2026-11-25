"""Bluetooth PAN Remote Client for laptop (Windows)."""

from __future__ import annotations

import logging
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("maya.bluetooth_remote")


@dataclass
class BluetoothDevice:
    name: str
    address: str
    paired: bool
    rssi: int


class BluetoothRemoteClient:
    """Client for connecting to phone via Bluetooth PAN on Windows."""

    def __init__(
        self,
        on_device_found: Callable[[BluetoothDevice], None] | None = None,
        on_connected: Callable[[str], None] | None = None,
        on_disconnected: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._on_device_found = on_device_found
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._connected = False
        self._phone_ip: str | None = None
        self._phone_port = 8421
        self._socket: socket.socket | None = None
        self._listen_thread: threading.Thread | None = None
        self._stop_listen = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def phone_ip(self) -> str | None:
        return self._phone_ip

    def scan_devices(self) -> list[BluetoothDevice]:
        """Scan for nearby Bluetooth devices (Windows)."""
        devices = []
        try:
            # This is a placeholder - actual implementation needs
            # Windows.Devices.Bluetooth APIs or pybluez
            logger.warning("Bluetooth scanning not fully implemented on Windows")
        except ImportError:
            logger.warning("pywin32 not available for Bluetooth scanning")
        return devices

    def connect_pan(self, device_address: str) -> bool:
        """Connect to phone's Bluetooth PAN (phone as PANU, laptop as NAP)."""
        try:
            # On Windows, Bluetooth PAN is managed by OS
            # We need to:
            # 1. Pair device via Windows Bluetooth settings
            # 2. Connect to PAN profile
            # 3. Get assigned IP (DHCP or link-local)
            
            # For now, use socket connection to phone's PAN gateway
            # Phone PAN typically uses 192.168.44.1 or link-local
            
            self._phone_ip = "192.168.44.1"  # Common PAN gateway
            self._phone_port = 8421
            
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(10)
            self._socket.connect((self._phone_ip, self._phone_port))
            
            self._connected = True
            self._on_connected and self._on_connected(self._phone_ip)
            
            # Start listening for data
            self._stop_listen.clear()
            self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listen_thread.start()
            
            return True
        except Exception as e:
            logger.error("Bluetooth PAN connect failed: %s", e)
            self._on_error and self._on_error(str(e))
            return False

    def connect_rfcomm(self, device_address: str, channel: int = 1) -> bool:
        """Connect via RFCOMM (Serial Port Profile) fallback."""
        try:
            # Windows RFCOMM uses virtual COM ports
            # Requires device pairing first
            logger.warning("RFCOMM not fully implemented")
            return False
        except Exception as e:
            logger.error("RFCOMM connect failed: %s", e)
            return False

    def _listen_loop(self) -> None:
        """Listen for incoming data from phone."""
        while not self._stop_listen.is_set() and self._socket:
            try:
                self._socket.settimeout(1.0)
                data = self._socket.recv(4096)
                if not data:
                    break
                # Handle incoming data
            except TimeoutError:
                continue
            except Exception as e:
                logger.error("Bluetooth listen error: %s", e)
                break

    def send(self, data: bytes) -> bool:
        """Send data to phone."""
        if not self._socket or not self._connected:
            return False
        try:
            self._socket.send(data)
            return True
        except Exception as e:
            logger.error("Bluetooth send failed: %s", e)
            return False

    def disconnect(self) -> None:
        """Disconnect from phone."""
        self._stop_listen.set()
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._connected = False
        self._phone_ip = None
        self._on_disconnected and self._on_disconnected()


# Singleton
_bluetooth_client: BluetoothRemoteClient | None = None
_client_lock = threading.Lock()


def get_bluetooth_client(
    on_device_found: Callable[[BluetoothDevice], None] | None = None,
    on_connected: Callable[[str], None] | None = None,
    on_disconnected: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> BluetoothRemoteClient:
    global _bluetooth_client
    with _client_lock:
        if _bluetooth_client is None:
            _bluetooth_client = BluetoothRemoteClient(
                on_device_found, on_connected, on_disconnected, on_error
            )
        return _bluetooth_client


def reset_bluetooth_client() -> None:
    global _bluetooth_client
    with _client_lock:
        if _bluetooth_client:
            _bluetooth_client.disconnect()
        _bluetooth_client = None
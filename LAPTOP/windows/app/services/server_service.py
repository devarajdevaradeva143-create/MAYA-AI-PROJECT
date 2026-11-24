"""Phone server bootstrap: settings -> adapters -> uvicorn (headless).

Runs the FastAPI app in a background thread with its own asyncio loop, so the
Qt event loop (GUI mode) and the server never block each other.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import signal
import socket
import sys
import threading
import time
from types import FrameType
from typing import Any

import psutil
from custom.server import ServerServices, ServerSettings, create_app

from app import __version__
from app.logging_setup import setup_server_logging
from app.services.control_service import ControlService
from app.services.engine_service import EngineAdapter
from app.services.monitor_service import MonitorAdapter, set_phone_stats_provider
from app.services.remote_service import HybridAdapter, InputAdapter, ScreenAdapter
from app.services.voice_service import VoiceAdapter
from app.services.wake_service import WakeAdapter

logger = logging.getLogger("maya.server")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8420
START_TIMEOUT_S = 15.0


def load_raw_settings() -> dict[str, Any]:
    from custom.config import load_settings

    try:
        data = load_settings()
    except Exception as exc:  # noqa: BLE001 - startup must explain the failure
        logger.error("Could not read settings.yaml: %s", type(exc).__name__)
        return {}
    return data if isinstance(data, dict) else {}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_int(value: Any, default: int, low: int | None = None, high: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def server_settings(raw: dict[str, Any] | None = None) -> ServerSettings:
    """Read the `server:` + `permissions.allowed_roots` config keys."""
    data = load_raw_settings() if raw is None else raw
    server_cfg = data.get("server") or {}
    permissions = data.get("permissions") or {}

    roots: list[str] = []
    for root in permissions.get("allowed_roots") or []:
        if isinstance(root, str) and root.strip():
            roots.append(root.strip())

    wan_cfg = server_cfg.get("wan") or {}
    if not isinstance(wan_cfg, dict):
        wan_cfg = {}

    return ServerSettings(
        host=str(server_cfg.get("host", DEFAULT_HOST)),
        port=_as_int(server_cfg.get("port", DEFAULT_PORT), DEFAULT_PORT, 1, 65535),
        lan_only=_as_bool(server_cfg.get("lan_only", True), True),
        token_ttl_hours=_as_int(server_cfg.get("token_ttl_hours", 720), 720, 1),
        pin_ttl_seconds=_as_int(server_cfg.get("pin_ttl_seconds", 120), 120, 30, 600),
        qr_ttl_seconds=_as_int(server_cfg.get("qr_ttl_seconds", 120), 120, 30, 600),
        max_pair_attempts=_as_int(server_cfg.get("max_pair_attempts", 5), 5, 1, 20),
        lockout_minutes=_as_int(server_cfg.get("lockout_minutes", 10), 10, 1),
        max_devices=_as_int(server_cfg.get("max_devices", 8), 8, 1, 32),
        allowed_roots=roots,
        enabled=_as_bool(server_cfg.get("enabled", True), True),
        wan_enabled=_as_bool(wan_cfg.get("enabled", False), False),
        wan_relay_url=str(wan_cfg.get("relay_url", "") or ""),
        wan_cert_path=str(wan_cfg.get("cert_path", "") or ""),
        wan_key_path=str(wan_cfg.get("key_path", "") or ""),
        wan_mode=str(wan_cfg.get("mode", "lan") or "lan"),
        wan_host=str(wan_cfg.get("host", "") or ""),
    )


def lan_ip() -> str:
    """Best private IPv4 for the pairing response (no packets are sent)."""
    try:
        interfaces = psutil.net_if_addrs()
    except Exception:  # noqa: BLE001 - network listing is best effort
        return ""

    for name, addresses in interfaces.items():
        lowered = name.lower()
        if lowered.startswith(("loopback", "lo", "docker", "veth", "br-", "vmnet", "vbox")):
            continue
        for address in addresses:
            if address.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or not ip.is_private:
                continue
            return str(ip)
    return ""


def build_services(
    raw_settings: dict[str, Any] | None = None,
    *,
    engine: Any | None = None,
    voice: Any | None = None,
    pc: Any | None = None,
    monitor: Any | None = None,
    wake: Any | None = None,
    screen: Any | None = None,
    input_adapter: Any | None = None,
    hybrid: Any | None = None,
) -> ServerServices:
    """Wire real adapters (tests can inject fakes)."""
    data = load_raw_settings() if raw_settings is None else raw_settings
    settings = server_settings(data)

    engine = engine or EngineAdapter()
    voice = voice or VoiceAdapter()
    pc = pc or ControlService()
    monitor = monitor or MonitorAdapter()
    wake = wake or WakeAdapter()
    screen = screen or ScreenAdapter()
    input_adapter = input_adapter or InputAdapter()
    hybrid = hybrid or HybridAdapter()

    from custom.persona.loader import load_persona

    laptop_name = str(data.get("laptop_name") or socket.gethostname() or "Maya-Laptop")

    return ServerServices(
        engine=engine,
        voice=voice,
        pc=pc,
        monitor=monitor,
        wake=wake,
        settings=settings,
        laptop_name=laptop_name,
        host=lan_ip(),
        version=__version__,
        platform=sys.platform,
        model=str(getattr(engine, "model", "") or data.get("model", "qwen3-3b")),
        engine_name=str(getattr(engine, "engine_name", "lemonade")),
        screen=screen,
        input=input_adapter,
        hybrid=hybrid,
        persona_prompts={
            "maya": load_persona("girlfriend"),
            "teacher": load_persona("english_teacher"),
        },
        started_at=time.time(),
    )


class ServerService:
    """Owns the uvicorn thread and exposes the app for tests and the UI."""

    def __init__(
        self,
        services: ServerServices | None = None,
        *,
        host: str | None = None,
        port: int | None = None,
        token_store: Any | None = None,
        limiter: Any | None = None,
        pairing: Any | None = None,
        confirm_store: Any | None = None,
    ) -> None:
        self.services = services or build_services()
        self.host = host or self.services.settings.host or DEFAULT_HOST
        self.port = int(port if port is not None else self.services.settings.port)
        self.bound_port: int | None = None
        self.last_error: str | None = None

        self._token_store = token_store
        self._limiter = limiter
        self._pairing = pairing
        self._confirm_store = confirm_store
        self._app = None
        self._server = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._zeroconf = None
        self._nsd_info = None

    # -- lifecycle ----------------------------------------------------

    @property
    def app(self):
        if self._app is None:
            self._app = create_app(
                self.services,
                token_store=self._token_store,
                limiter=self._limiter,
                pairing=self._pairing,
                confirm_store=self._confirm_store,
            )
        return self._app

    @property
    def pairing(self):
        return self.app.state.pairing

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server is not None)

    def start(self, timeout: float = START_TIMEOUT_S) -> None:
        if self.running:
            return
        self.last_error = None
        self.bound_port = None
        self._started.clear()
        self._thread = threading.Thread(target=self._serve, name="maya-server", daemon=True)
        self._thread.start()

        if not self._started.wait(timeout):
            raise RuntimeError("Phone server did not start in time")
        if self.last_error:
            raise RuntimeError(self.last_error)

        # Register phone stats provider for the Windows app monitor page
        def _phone_stats_provider() -> list[dict[str, Any]]:
            try:
                tokens = self.app.state.tokens
                devices = tokens.list_active()
                phone_stats = []
                for d in devices:
                    if d.phone_battery_percent is not None or d.phone_storage_used_percent is not None \
                       or d.phone_ram_used_percent is not None or d.phone_uptime_hours is not None:
                        phone_stats.append({
                            "device_id": d.device_id,
                            "name": d.name,
                            "battery_percent": d.phone_battery_percent,
                            "storage_used_percent": d.phone_storage_used_percent,
                            "ram_used_percent": d.phone_ram_used_percent,
                            "uptime_hours": d.phone_uptime_hours,
                            "updated": d.phone_stats_updated,
                        })
                return phone_stats
            except Exception:  # noqa: BLE001
                return []

        set_phone_stats_provider(_phone_stats_provider)

    def stop(self, timeout: float = 5.0) -> None:
        self._unregister_nsd()
        try:
            self.services.wake.stop()
        except Exception:  # noqa: BLE001 - shutdown must continue
            logger.debug("Wake stop failed", exc_info=True)

        server = self._server
        if server is not None:
            server.should_exit = True
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._server = None
        self._thread = None
        self.bound_port = None

        # Unregister phone stats provider
        set_phone_stats_provider(None)

    # -- internals ----------------------------------------------------

    def _serve(self) -> None:
        import uvicorn

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_config=None,
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        self._server = server

        async def _run() -> None:
            task = asyncio.create_task(server.serve())
            while not server.started and not task.done():
                await asyncio.sleep(0.05)
            if server.started:
                self.bound_port = self._bound_port(server)
                if self.bound_port:
                    self.services.settings.port = self.bound_port
                if self.host not in {"0.0.0.0", "::", ""}:
                    self.services.host = self.host
                logger.info("Phone server listening on %s:%s", self.host, self.bound_port)
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._register_nsd, (self.bound_port or self.port)
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("NSD registration scheduling failed", exc_info=True)
            self._started.set()
            await task

        try:
            loop.run_until_complete(_run())
        except Exception as exc:  # noqa: BLE001 - surfaced through last_error
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.error("Phone server stopped: %s", self.last_error)
        finally:
            self._started.set()
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            loop.close()

    @staticmethod
    def _bound_port(server: Any) -> int | None:
        try:
            sockets = server.servers[0].sockets
            if sockets:
                return int(sockets[0].getsockname()[1])
        except (AttributeError, IndexError, OSError):
            pass
        return None

    def _register_nsd(self, port: int) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except Exception:  # noqa: BLE001 - optional dependency
            logger.info("zeroconf not installed; skipping NSD advertise")
            return
        try:
            ip = self.services.host or lan_ip()
            if not ip:
                logger.info("No LAN IP; skipping NSD advertise")
                return
            name_host = (self.services.laptop_name or socket.gethostname() or "Maya-Laptop").replace(" ", "-")
            service_name = f"{name_host}._maya._tcp.local."
            info = ServiceInfo(
                "_maya._tcp.local.",
                service_name,
                port=int(port),
                parsed_addresses=[ip],
                server=f"{socket.gethostname()}.local.",
                properties={"version": "1"},
            )
            zc = Zeroconf()
            zc.register_service(info, allow_name_change=True)
            self._zeroconf = zc
            self._nsd_info = info
            logger.info("NSD advertising %s on port %s", service_name, port)
        except Exception as exc:  # noqa: BLE001 - advertise is best effort
            logger.warning("NSD advertise failed: %r", exc, exc_info=True)
            self._zeroconf = None
            self._nsd_info = None

    def _unregister_nsd(self) -> None:
        zc = self._zeroconf
        info = self._nsd_info
        self._zeroconf = None
        self._nsd_info = None
        if zc is None:
            return
        try:
            if info is not None:
                zc.unregister_service(info)
        except Exception:  # noqa: BLE001
            logger.debug("NSD unregister failed", exc_info=True)
        try:
            zc.close()
        except Exception:  # noqa: BLE001
            logger.debug("Zeroconf close failed", exc_info=True)


def _print_pairing(service: ServerService) -> None:
    """Headless mode has no window: print a fresh PIN once to the console."""
    try:
        pin, expires_at = service.pairing.generate_pin()
    except Exception as exc:  # noqa: BLE001
        print(f"Pairing PIN unavailable: {exc}")
        return
    minutes = max(1, int((expires_at - time.time()) / 60))
    print("=" * 52)
    print(" Maya AI phone server (LAN only)")
    print(f" Host : {service.services.host or 'this laptop'}:{service.bound_port or service.port}")
    print(f" PIN  : {pin}  (valid ~{minutes} min)")
    print(" Phone: Maya app -> Pair with PIN")
    print(" Ctrl+C to stop")
    print("=" * 52)


_SHARED_SERVICE: ServerService | None = None
_SHARED_LOCK = threading.Lock()


def shared_server_service() -> ServerService:
    """One ServerService for the whole app (Settings page + auto-start)."""
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        if _SHARED_SERVICE is None:
            _SHARED_SERVICE = ServerService()
        return _SHARED_SERVICE


def stop_shared_server(timeout: float = 5.0) -> None:
    """Stop the shared server on exit. Safe when it never started."""
    global _SHARED_SERVICE
    with _SHARED_LOCK:
        service = _SHARED_SERVICE
        _SHARED_SERVICE = None
    if service is not None:
        try:
            service.stop(timeout=timeout)
        except Exception:  # noqa: BLE001 - shutdown must never raise
            logger.debug("Shared server stop failed", exc_info=True)


def run_headless_server() -> int:
    """Entry point for `python -m app --headless`."""
    setup_server_logging(console=True)
    raw = load_raw_settings()
    settings = server_settings(raw)

    if not settings.enabled:
        logger.info("Phone server is disabled in settings.yaml (server.enabled=false)")
        return 0

    service = ServerService(build_services(raw))
    try:
        service.start()
    except Exception as exc:  # noqa: BLE001 - clear exit code + log
        logger.error("Could not start the phone server: %s", exc)
        return 1

    logger.info("Headless server ready on %s:%s", service.host, service.bound_port or service.port)
    _print_pairing(service)

    stop = threading.Event()

    def _handle_signal(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        stop.set()

    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), _handle_signal)
            except (OSError, ValueError):
                pass

    try:
        while not stop.is_set():
            stop.wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Stopping phone server")
        service.stop()
    return 0

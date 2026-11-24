"""Fake ports + app harness for the phone server tests."""

from __future__ import annotations

import time
import wave
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from custom.server.app import create_app
from custom.server.auth import RateLimiter, TokenStore
from custom.server.confirm import ConfirmStore
from custom.server.contracts import ScreenFrame, ServerServices, ServerSettings
from custom.server.pair import PairingManager
from fastapi.testclient import TestClient

DEVICE_ID = "a" * 32
OTHER_DEVICE_ID = "b" * 32


class FakeEngine:
    def __init__(
        self,
        reply: str = "Vanakkam da!",
        chunks: list[str] | None = None,
        error: Exception | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.reply = reply
        self.chunks = chunks if chunks is not None else ["Van", "akkam"]
        self.error = error
        self.stream_error = stream_error
        self.last_messages: list[dict[str, str]] = []

    def health(self) -> dict[str, Any]:
        return {"status": "ok"}

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.last_messages = messages
        if self.error:
            raise self.error
        return self.reply

    def chat_stream(self, messages: list[dict[str, str]]):
        self.last_messages = messages
        if self.stream_error:
            raise self.stream_error
        yield from self.chunks


class FakeVoice:
    def __init__(self, tmp_dir: Path, available: bool = True) -> None:
        self.tmp_dir = tmp_dir
        self.available = available
        self.last_extras: dict[str, Any] = {}
        self.last_wav_path: Path | None = None

    def status(self) -> dict[str, Any]:
        return {
            "stt": {"engine": "vosk", "available": self.available, "languages": ["en", "en-in"]},
            "tts": {
                "engine": "sapi",
                "available": self.available,
                "voices": ["heera"],
                "piper": {"available": False, "voices": []},
            },
        }

    def transcribe(self, wav_path: Path, lang: str) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("stt down")
        if not wav_path.is_file():
            raise AssertionError("server must pass an existing temp wav")
        self.last_wav_path = wav_path
        return {"text": "enna time", "lang": lang, "engine": "vosk"}

    def synthesize_wav(
        self,
        text: str,
        *,
        engine: str = "auto",
        voice: str | None = None,
        lang: str = "en",
        speed: float = 1.0,
    ) -> Path:
        if not self.available:
            raise RuntimeError("tts down")
        self.last_extras = {
            "text": text,
            "engine": engine,
            "voice": voice,
            "lang": lang,
            "speed": speed,
        }
        path = self.tmp_dir / "tts-out.wav"
        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 100)
        path.write_bytes(buffer.getvalue())
        return path


class FakePc:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((action, params))
        if self.error:
            raise self.error
        return {"message": f"done {action}"}


class FakeScreen:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, int]] = []

    def capture(self, *, max_width: int = 1280, quality: int = 60) -> ScreenFrame:
        self.calls.append((max_width, quality))
        if self.error:
            raise self.error
        return ScreenFrame(b"\xff\xd8fake-jpeg\xff\xd9", "image/jpeg", 640, 360)


class FakeInput:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[list[dict[str, Any]]] = []

    def apply(self, events: list[dict[str, Any]]) -> int:
        self.calls.append(events)
        if self.error:
            raise self.error
        return len(events)


class FakeHybridTask:
    def __init__(self, task_id: str, description: str, status: str = "queued") -> None:
        self.id = task_id
        self.description = description
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "status": self.status}


class FakeHybrid:
    def __init__(self) -> None:
        self.controller = "none"
        self.takeovers = 0
        self.releases = 0
        self.tasks: list[FakeHybridTask] = []

    def status(self) -> dict[str, Any]:
        return {
            "controller": self.controller,
            "ai_busy": False,
            "queued_tasks": len(self.tasks),
            "running_task": None,
            "conflicts": 0,
            "last_takeover": None,
            "uptime_s": 60,
        }

    def takeover(self) -> bool:
        self.takeovers += 1
        self.controller = "user"
        return True

    def release(self) -> bool:
        self.releases += 1
        self.controller = "none"
        return True

    def list_tasks(self) -> list[FakeHybridTask]:
        return list(self.tasks)


class FakeMonitor:
    def snapshot(self) -> dict[str, Any]:
        return {
            "ts": 1760100000,
            "cpu": {"percent": 12.5, "cores": 8, "freq_mhz": 3200},
            "ram": {"total_gb": 15.3, "used_gb": 7.1, "percent": 46.4},
            "gpu": {"name": "AMD Radeon 840M", "percent": None},
            "npu": {"name": "AMD XDNA", "tops": 50, "percent": None},
            "battery": {"percent": 82, "plugged": True, "seconds_left": None},
            "temps": {"cpu_c": 48.0},
            "disks": [
                {"mount": "C:\\", "total_gb": 476.0, "used_gb": 210.0, "percent": 44.1},
            ],
            "uptime_s": 12345,
        }


class FakeWake:
    def __init__(self) -> None:
        self.listening = False
        self.expires_at = 0.0
        self.events: list[dict[str, Any]] = []
        self.listen_calls: list[int] = []

    def status(self) -> dict[str, Any]:
        return {"listening": self.listening, "clap": True, "name": True}

    def listen(self, seconds: int) -> float:
        self.listen_calls.append(seconds)
        self.listening = True
        self.expires_at = time.time() + seconds
        return self.expires_at

    def stop(self) -> None:
        self.listening = False

    def drain_events(self) -> list[dict[str, Any]]:
        events = self.events
        self.events = []
        return events


@dataclass
class Harness:
    app: Any
    client: TestClient
    services: ServerServices
    tokens: TokenStore
    limiter: RateLimiter
    pairing: PairingManager
    confirm: ConfirmStore
    engine: FakeEngine = field(default_factory=FakeEngine)
    voice: FakeVoice | None = None
    pc: FakePc = field(default_factory=FakePc)
    monitor: FakeMonitor = field(default_factory=FakeMonitor)
    wake: FakeWake = field(default_factory=FakeWake)
    screen: FakeScreen = field(default_factory=FakeScreen)
    input: FakeInput = field(default_factory=FakeInput)
    hybrid: FakeHybrid = field(default_factory=FakeHybrid)
    root: Path = Path()


def make_harness(
    tmp_path: Path,
    *,
    lan_only: bool = True,
    engine: FakeEngine | None = None,
    voice_available: bool = True,
    pc: FakePc | None = None,
    screen: FakeScreen | None = None,
    input_adapter: FakeInput | None = None,
    hybrid: FakeHybrid | None = None,
    **settings_kwargs: Any,
) -> Harness:
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    settings = ServerSettings(
        port=8420,
        lan_only=lan_only,
        allowed_roots=[str(root)],
        **settings_kwargs,
    )
    engine = engine or FakeEngine()
    voice = FakeVoice(tmp_path, available=voice_available)
    pc = pc or FakePc()
    monitor = FakeMonitor()
    wake = FakeWake()
    screen = screen or FakeScreen()
    input_adapter = input_adapter or FakeInput()
    hybrid = hybrid or FakeHybrid()
    services = ServerServices(
        engine=engine,
        voice=voice,
        pc=pc,
        monitor=monitor,
        wake=wake,
        screen=screen,
        input=input_adapter,
        hybrid=hybrid,
        settings=settings,
        laptop_name="Test-Laptop",
        host="192.168.1.50",
        platform="windows",
        model="qwen3-3b",
        engine_name="lemonade",
        persona_prompts={"maya": "MAYA PROMPT", "teacher": "TEACHER PROMPT"},
        started_at=time.time() - 60,
    )

    tokens = TokenStore(tmp_path / "tokens.json")
    limiter = RateLimiter()
    pairing = PairingManager(settings, tokens)
    confirm = ConfirmStore()
    app = create_app(
        services,
        token_store=tokens,
        limiter=limiter,
        pairing=pairing,
        confirm_store=confirm,
    )
    client = TestClient(app, client=("127.0.0.1", 50000))
    return Harness(
        app=app,
        client=client,
        services=services,
        tokens=tokens,
        limiter=limiter,
        pairing=pairing,
        confirm=confirm,
        engine=engine,
        voice=voice,
        pc=pc,
        monitor=monitor,
        wake=wake,
        screen=screen,
        input=input_adapter,
        hybrid=hybrid,
        root=root,
    )


def pair_device(
    harness: Harness,
    device_id: str = DEVICE_ID,
    name: str = "Test Phone",
    app_version: str = "0.1.0",
) -> str:
    pin, _ = harness.pairing.generate_pin()
    response = harness.client.post(
        "/api/v1/pair/claim",
        json={
            "device_id": device_id,
            "device_name": name,
            "pin": pin,
            "app_version": app_version,
            "api": 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def error_code(response: Any) -> int:
    return int(response.json()["error"]["code"])

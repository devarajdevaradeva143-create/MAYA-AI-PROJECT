"""Model download process fallback and timeout behavior."""

from __future__ import annotations

import io
import threading

import httpx

from app.services import model_service
from app.services.model_service import ModelService


class FakeProcess:
    def __init__(self, stdout, returncode: int | None = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -1
        release = getattr(self.stdout, "release", None)
        if release is not None:
            release.set()

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = -1
        return self.returncode

    def kill(self) -> None:
        self.terminate()


class BlockingOutput:
    def __init__(self) -> None:
        self.release = threading.Event()

    def __iter__(self):
        self.release.wait(timeout=2)
        return iter(())

    def close(self) -> None:
        self.release.set()


def test_pull_falls_back_to_cli_when_engine_is_unreachable(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "lemonade.exe"
    executable.touch()
    monkeypatch.setattr(model_service, "LEMONADE_EXE", executable)
    process = FakeProcess(io.StringIO("download started\n"))
    monkeypatch.setattr(model_service.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(unreachable))
    service = ModelService(client=client)
    try:
        chunks = list(service.pull("model-id"))
    finally:
        service.close()

    assert process.terminated is False
    assert chunks[-1] == {"status": "completed", "model": "model-id"}


def test_cli_download_times_out_without_output(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "lemonade.exe"
    executable.touch()
    monkeypatch.setattr(model_service, "LEMONADE_EXE", executable)
    monkeypatch.setattr(model_service, "PULL_TIMEOUT", 0.05)
    process = FakeProcess(BlockingOutput(), returncode=None)
    monkeypatch.setattr(model_service.subprocess, "Popen", lambda *_args, **_kwargs: process)

    chunks = list(ModelService()._pull_cli("model-id"))

    assert process.terminated is True
    assert chunks == [{"status": "error", "message": "Download timed out"}]


def test_cli_download_can_cancel_while_waiting_for_output(tmp_path, monkeypatch) -> None:
    executable = tmp_path / "lemonade.exe"
    executable.touch()
    monkeypatch.setattr(model_service, "LEMONADE_EXE", executable)
    process = FakeProcess(BlockingOutput(), returncode=None)
    monkeypatch.setattr(model_service.subprocess, "Popen", lambda *_args, **_kwargs: process)
    service = ModelService()
    service.cancel()

    try:
        chunks = list(service._pull_cli("model-id"))
    finally:
        service.close()

    assert process.terminated is True
    assert chunks == [{"status": "cancelled"}]

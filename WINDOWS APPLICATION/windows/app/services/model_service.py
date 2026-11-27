"""Model management service for the Lemonade engine.

High-level operations for listing, downloading, deleting and loading models.
Qt-free: the UI drives it from worker threads.

Endpoints used (verified against Lemonade 2026.43.3):

- ``GET  /api/v1/models?show_all=true`` — full catalog (213 entries here)
- ``GET  /api/v1/models``               — downloaded models only
- ``GET  /api/v1/health``               — engine + loaded model status
- ``POST /v1/pull``                     — download (returns JSON, not SSE)
- ``POST /v1/delete``                   — remove a model
- ``POST /api/v1/load``                 — load into memory
- ``lemonade.exe backends``             — CLI only; there is no REST endpoint
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from app.services.engine_service import EngineUnavailableError

logger = logging.getLogger("maya.model.service")

DEFAULT_HOST = "http://localhost:13305"
LEMONADE_EXE = (
    Path.home() / "AppData" / "Local" / "lemonade_server" / "bin" / "lemonade.exe"
)
PULL_TIMEOUT = 3600.0


class ModelService:
    """Service for managing models in Lemonade."""

    def __init__(
        self, host: str = DEFAULT_HOST, client: httpx.Client | None = None
    ) -> None:
        self._host = host.rstrip("/")
        self._client = client or httpx.Client(timeout=30.0)
        self._cancel_event = threading.Event()

    @property
    def host(self) -> str:
        return self._host

    def cancel(self) -> None:
        """Cancel any ongoing operation (e.g., a model download)."""
        self._cancel_event.set()

    def _reset_cancel(self) -> None:
        self._cancel_event.clear()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = self._client.get(f"{self._host}{path}", params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as exc:
            raise EngineUnavailableError(f"Cannot connect to engine at {self._host}") from exc
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(f"Request to {path} failed: {exc}") from exc
        except ValueError as exc:
            raise EngineUnavailableError(f"Invalid JSON from {path}") from exc

    def health(self) -> dict[str, Any]:
        """Get engine health status."""
        data = self._get("/api/v1/health")
        return data if isinstance(data, dict) else {}

    def catalog(self) -> list[dict[str, Any]]:
        """Full model catalog, including models that are not downloaded."""
        data = self._get("/api/v1/models", params={"show_all": "true"})
        items = data.get("data", []) if isinstance(data, dict) else []
        return [m for m in items if isinstance(m, dict)]

    def installed(self) -> list[dict[str, Any]]:
        """Only the models that are downloaded and ready to load."""
        data = self._get("/api/v1/models")
        items = data.get("data", []) if isinstance(data, dict) else []
        return [m for m in items if isinstance(m, dict) and m.get("downloaded")]

    def is_downloaded(self, model_id: str) -> bool:
        """True when the model is installed. False when the engine is unreachable."""
        try:
            return any(m.get("id") == model_id for m in self.installed())
        except EngineUnavailableError:
            return False

    # -- download ------------------------------------------------------

    def pull(self, model_id: str) -> Iterator[dict[str, Any]]:
        """Download a model, yielding progress chunks as they arrive.

        Tries the REST endpoint first; falls back to ``lemonade.exe pull`` when
        the server rejects the request or cannot be reached.
        """
        self._reset_cancel()
        yield {"status": "downloading", "message": f"Preparing {model_id}..."}

        try:
            yield from self._pull_rest(model_id)
            return
        except _PullFallback:
            logger.info("REST pull unavailable for %s; using lemonade.exe", model_id)
        except EngineUnavailableError:
            raise

        yield from self._pull_cli(model_id)

    def _pull_rest(self, model_id: str) -> Iterator[dict[str, Any]]:
        """POST /v1/pull. The server answers with a single JSON document."""
        try:
            with self._client.stream(
                "POST",
                f"{self._host}/v1/pull",
                json={"model_name": model_id},
                timeout=PULL_TIMEOUT,
            ) as r:
                if r.status_code >= 400:
                    raise _PullFallback()
                body = "".join(r.iter_text())
        except httpx.ConnectError as exc:
            raise _PullFallback() from exc
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(f"Pull failed: {exc}") from exc

        if self._cancel_event.is_set():
            yield {"status": "cancelled"}
            return

        payload: dict[str, Any] = {}
        for line in body.splitlines():
            text = line.strip()
            if text.startswith("data: "):
                text = text[6:].strip()
            if not text or text == "[DONE]":
                continue
            try:
                chunk = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(chunk, dict):
                payload.update(chunk)

        status = str(payload.get("status", "")).lower()
        if status in {"success", "ok", "completed", "already_downloaded"}:
            yield {"status": "completed", "model": model_id}
        elif status in {"error", "failed"}:
            yield {
                "status": "error",
                "message": str(payload.get("message") or payload.get("error") or "Pull failed"),
            }
        elif payload:
            yield {"status": "completed", "model": model_id}
        else:
            # Empty or unrecognised body: let the CLI produce a real result.
            raise _PullFallback()

    def _pull_cli(self, model_id: str) -> Iterator[dict[str, Any]]:
        """Download through ``lemonade.exe pull`` and stream its output."""
        if not LEMONADE_EXE.is_file():
            yield {"status": "error", "message": f"lemonade.exe not found at {LEMONADE_EXE}"}
            return

        try:
            proc = subprocess.Popen(
                [str(LEMONADE_EXE), "pull", model_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            yield {"status": "error", "message": f"Could not start lemonade.exe: {exc}"}
            return

        assert proc.stdout is not None
        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                for raw in proc.stdout:
                    output.put(raw)
            except (OSError, ValueError):
                pass
            finally:
                output.put(None)

        reader = threading.Thread(target=read_output, name="maya-model-output", daemon=True)
        reader.start()
        deadline = time.monotonic() + PULL_TIMEOUT

        def stop_process() -> None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        try:
            while True:
                if self._cancel_event.is_set():
                    stop_process()
                    yield {"status": "cancelled"}
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop_process()
                    yield {"status": "error", "message": "Download timed out"}
                    return
                try:
                    raw = output.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue
                if raw is None:
                    break
                line = raw.strip()
                if line:
                    yield {"status": "downloading", "message": line}

            while proc.poll() is None:
                if self._cancel_event.is_set():
                    stop_process()
                    yield {"status": "cancelled"}
                    return
                if time.monotonic() >= deadline:
                    stop_process()
                    yield {"status": "error", "message": "Download timed out"}
                    return
                time.sleep(0.1)
        finally:
            proc.stdout.close()

        if proc.returncode == 0:
            yield {"status": "completed", "model": model_id}
        else:
            yield {"status": "error", "message": f"lemonade.exe exited {proc.returncode}"}

    # -- lifecycle -----------------------------------------------------

    def delete(self, model_id: str) -> dict[str, Any]:
        """Delete a downloaded model."""
        return self._post("/v1/delete", {"model_name": model_id}, timeout=60)

    def load(self, model_id: str) -> dict[str, Any]:
        """Load a model into memory."""
        return self._post("/api/v1/load", {"model_name": model_id}, timeout=120)

    def _post(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        try:
            r = self._client.post(f"{self._host}{path}", json=body, timeout=timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.ConnectError as exc:
            raise EngineUnavailableError(f"Cannot connect to engine at {self._host}") from exc
        except httpx.HTTPError as exc:
            raise EngineUnavailableError(f"Request to {path} failed: {exc}") from exc
        except ValueError as exc:
            raise EngineUnavailableError(f"Invalid JSON from {path}") from exc
        return data if isinstance(data, dict) else {}

    # -- backends ------------------------------------------------------

    def backends(self) -> list[dict[str, Any]]:
        """Installed backends, parsed from ``lemonade.exe backends``.

        There is no REST endpoint for this (``/api/v1/backends`` returns 404).
        """
        if not LEMONADE_EXE.is_file():
            raise EngineUnavailableError(f"lemonade.exe not found at {LEMONADE_EXE}")

        try:
            result = subprocess.run(
                [str(LEMONADE_EXE), "backends"],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise EngineUnavailableError("Backends command timed out") from exc
        except OSError as exc:
            raise EngineUnavailableError(f"Backends command failed: {exc}") from exc

        if result.returncode != 0:
            raise EngineUnavailableError(
                f"Backends command failed: {result.stderr.strip() or result.stdout.strip()}"
            )

        entries: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            # Rows look like:  llamacpp   vulkan   core   native   installed   b11393
            if len(parts) < 5 or parts[0] == "Recipe":
                continue
            if parts[4] not in {"installed", "installable", "missing", "error"}:
                continue
            entries.append(
                {
                    "recipe": parts[0],
                    "backend": parts[1],
                    "tier": parts[2],
                    "format": parts[3],
                    "status": parts[4],
                    "version": parts[5] if len(parts) > 5 else "",
                }
            )
        return entries

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()


class _PullFallback(Exception):
    """Internal signal: use the CLI instead of the REST endpoint."""

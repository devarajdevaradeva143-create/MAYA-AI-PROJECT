r"""Maya AI engine bridge.

Connects to the local inference engine (Lemonade via OpenAI-compatible HTTP,
or OpenJarvis CLI subprocess). All settings come from
MAYA AI/config/settings.yaml (``engine`` section) — never hardcoded.

Modes:
  - ``direct`` (default): HTTP straight to Lemonade at http://localhost:13305/v1
  - ``openjarvis``: subprocess call to .venv-engine/Scripts/jarvis.exe ask ...

Graceful failure: if the engine is down, returns a clear error message,
never crashes.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Iterator

import httpx

from ..config import load_settings, PROJECT_ROOT


#: Default Lemonade host (overridden by settings.yaml).
DEFAULT_HOST = "http://localhost:13305"
#: Default model (overridden by settings.yaml).
DEFAULT_MODEL = "qwen3.5-2b-FLM"
#: Fallback model if the primary is unavailable.
DEFAULT_FALLBACK_MODEL = "qwen3-it-4b-FLM"


class EngineError(RuntimeError):
    """Raised when the engine cannot be reached or returns an error."""


def _strip_thinking(text: str) -> str:
    """Remove ``<think...>...</think...>`` blocks some models emit."""
    cleaned = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.S | re.I)
    return re.sub(r"</?think\b[^>]*>", "", cleaned, flags=re.I).strip()


class EngineBridge:
    """Thin client over the local inference engine.

    Reads host/model/timeouts from settings.yaml. Two modes:
    ``direct`` (HTTP to Lemonade) and ``openjarvis`` (jarvis.exe subprocess).
    """

    def __init__(self, mode: str | None = None) -> None:
        settings = load_settings()
        engine_cfg = settings.get("engine", {}) if isinstance(settings, dict) else {}

        self.mode = mode or str(engine_cfg.get("mode", "direct"))
        self.engine_type = str(engine_cfg.get("type", "lemonade"))
        self.host = str(engine_cfg.get("host", DEFAULT_HOST)).rstrip("/")
        # engine.model is the single source of truth.
        self.model = str(engine_cfg.get("model", DEFAULT_MODEL))
        self.fallback_model = str(
            engine_cfg.get("fallback_model", DEFAULT_FALLBACK_MODEL)
        )
        self.timeout = float(engine_cfg.get("timeout", 30))
        self.temperature = float(engine_cfg.get("temperature", 0.7))
        self.max_tokens = int(engine_cfg.get("max_tokens", 512))
        # Reasoning models (Qwen3 / Qwen3.5) can spend the whole max_tokens budget
        # on hidden reasoning and return empty content. ``engine.disable_thinking``
        # switches that off so the answer text is always produced.
        self.disable_thinking = bool(engine_cfg.get("disable_thinking", False))

        # venv lives at JARVIS/.venv-engine (PROJECT_ROOT is the top-level folder).
        self._jarvis = PROJECT_ROOT / "JARVIS" / ".venv-engine" / "Scripts" / "jarvis.exe"
        self._client = httpx.Client(timeout=self.timeout)

    # ── Health / discovery ──────────────────────────────────────────
    def health(self) -> dict[str, Any]:
        """Return engine health status.

        Returns ``{"ok": True, ...}`` when reachable, or
        ``{"ok": False, "error": ...}`` when unreachable. Never raises.
        """
        try:
            if self.mode == "openjarvis":
                return self._health_openjarvis()
            return self._health_direct()
        except Exception as exc:  # pragma: no cover - defensive
            return {"ok": False, "error": f"{exc}"}

    def list_models(self) -> list[str]:
        """List available model ids. Falls back to configured models on error.

        Never raises.
        """
        try:
            if self.mode == "openjarvis":
                return self._list_models_openjarvis()
            return self._list_models_direct()
        except Exception:  # pragma: no cover - defensive
            return [self.model, self.fallback_model]

    # ── Chat ────────────────────────────────────────────────────────
    def chat(self, messages: list[dict[str, str]], stream: bool = False) -> str:
        """Send a chat completion and return the reply text.

        If ``stream`` is True, the full streamed text is collected and returned
        (use :meth:`chat_stream` for incremental chunking).

        Never raises — returns an ``[engine error]`` string on failure.
        """
        try:
            if self.mode == "openjarvis":
                return self._chat_openjarvis(messages)
            return self._chat_direct(messages, stream=stream)
        except EngineError as exc:
            return f"[engine error] {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            return f"[engine error] {exc}"

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield reply text chunks incrementally.

        Never raises — yields an ``[engine error]`` string on failure.
        """
        try:
            if self.mode == "openjarvis":
                # jarvis.exe ask is non-streaming; yield the whole reply once.
                reply = self._chat_openjarvis(messages)
                if reply:
                    yield reply
                return
            yield from self._chat_stream_direct(messages)
        except EngineError as exc:
            yield f"[engine error] {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            yield f"[engine error] {exc}"

    # ── Direct (HTTP) mode ─────────────────────────────────────────
    def _extra_payload(self) -> dict[str, Any]:
        """Settings-driven request options (currently just thinking mode)."""
        if not self.disable_thinking:
            return {}
        return {"chat_template_kwargs": {"enable_thinking": False}}

    def _health_direct(self) -> dict[str, Any]:
        r = self._client.get(f"{self.host}/v1/models", timeout=10)
        r.raise_for_status()
        data = r.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return {
            "ok": True,
            "mode": "direct",
            "host": self.host,
            "models": ids,
        }

    def _list_models_direct(self) -> list[str]:
        r = self._client.get(f"{self.host}/v1/models", timeout=10)
        r.raise_for_status()
        data = r.json()
        return [
            m.get("id", "")
            for m in data.get("data", [])
            if m.get("id")
        ]

    def _chat_direct(self, messages: list[dict[str, str]], stream: bool = False) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
            **self._extra_payload(),
        }
        r = self._client.post(
            f"{self.host}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise EngineError("no choices returned by engine")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise EngineError("empty content returned by engine")
        return _strip_thinking(content)

    def _chat_stream_direct(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
            **self._extra_payload(),
        }
        with self._client.stream(
            "POST",
            f"{self.host}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

    # ── OpenJarvis CLI mode ────────────────────────────────────────
    def _jarvis_available(self) -> bool:
        return self._jarvis.is_file()

    def _health_openjarvis(self) -> dict[str, Any]:
        if not self._jarvis_available():
            return {
                "ok": False,
                "error": f"jarvis.exe not found at {self._jarvis}",
            }
        return {"ok": True, "mode": "openjarvis", "jarvis": str(self._jarvis)}

    def _list_models_openjarvis(self) -> list[str]:
        # jarvis.exe has no simple model-list subcommand we rely on;
        # return configured models instead.
        return [self.model, self.fallback_model]

    def _chat_openjarvis(self, messages: list[dict[str, str]]) -> str:
        if not self._jarvis_available():
            raise EngineError(f"jarvis.exe not found at {self._jarvis}")
        prompt = self._messages_to_prompt(messages)
        cmd = [
            str(self._jarvis),
            "ask",
            prompt,
            "-e",
            "lemonade",
            "-m",
            self.model,
            "--no-stream",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            raise EngineError(f"jarvis.exe not found at {self._jarvis}")
        except subprocess.TimeoutExpired:
            raise EngineError("engine request timed out")
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            raise EngineError(f"jarvis exited {result.returncode}: {err}")
        output = result.stdout.strip()
        if not output:
            raise EngineError("empty reply from engine")
        return _strip_thinking(output)

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
        """Flatten chat messages into a single prompt for jarvis.exe ask."""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Maya: {content}")
            else:
                parts.append(f"User: {content}")
        return "\n".join(parts)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()


# Module-level default bridge (direct mode, reads settings.yaml).
bridge = EngineBridge()

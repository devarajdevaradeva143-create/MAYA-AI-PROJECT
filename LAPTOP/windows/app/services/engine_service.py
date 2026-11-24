"""Engine adapter: existing EngineBridge, but contract-shaped.

`custom.engine.bridge.EngineBridge` never raises; it returns an
`[engine error] ...` string. The phone API must answer with error codes
3001/3002 instead, so this adapter converts those strings to exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

ENGINE_ERROR_PREFIX = "[engine error]"

TIMEOUT_MARKERS = (
    "timeout",
    "timed out",
    "read timeout",
    "connect timeout",
)


class EngineUnavailableError(RuntimeError):
    """Engine unreachable or returned no content."""


class EngineTimeoutError(TimeoutError):
    """Engine did not answer within the configured timeout."""


def _raise_for_error(text: str) -> None:
    message = text[len(ENGINE_ERROR_PREFIX) :].strip()
    lowered = message.lower()
    if any(marker in lowered for marker in TIMEOUT_MARKERS):
        raise EngineTimeoutError(message or "Engine timeout")
    raise EngineUnavailableError(message or "Engine unavailable")


class EngineAdapter:
    """Thin wrapper around the shared EngineBridge/singleton."""

    def __init__(self, bridge: Any | None = None) -> None:
        if bridge is None:
            from custom.engine.bridge import bridge as engine_bridge

            bridge = engine_bridge
        self._bridge = bridge

    @property
    def model(self) -> str:
        return str(getattr(self._bridge, "model", "qwen3-3b"))

    @property
    def engine_name(self) -> str:
        return str(getattr(self._bridge, "engine_type", "lemonade"))

    def health(self) -> dict[str, Any]:
        return self._bridge.health()

    def chat(self, messages: list[dict[str, str]]) -> str:
        reply = self._bridge.chat(messages)
        if isinstance(reply, str) and reply.startswith(ENGINE_ERROR_PREFIX):
            _raise_for_error(reply)
        return reply

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        for chunk in self._bridge.chat_stream(messages):
            if isinstance(chunk, str) and chunk.startswith(ENGINE_ERROR_PREFIX):
                _raise_for_error(chunk)
            yield chunk

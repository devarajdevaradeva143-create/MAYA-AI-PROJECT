"""Engine adapter — wraps custom.engine.bridge.EngineBridge."""

from dataclasses import dataclass
from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


@dataclass
class EngineResult:
    ok: bool
    text: str
    raw: Any = None


class EngineAdapter:
    """Thin wrapper over custom.engine.bridge.EngineBridge."""

    def __init__(self, max_tokens: int = 800, temperature: float = 0.7):
        from custom.engine.bridge import EngineBridge

        self._bridge = EngineBridge()
        self._bridge.max_tokens = max_tokens
        self._bridge.temperature = temperature

    def chat(self, messages: list[dict[str, str]]) -> EngineResult:
        """Send messages to engine, return structured result."""
        text = self._bridge.chat(messages, stream=False)
        ok = not text.startswith("[engine error]")
        return EngineResult(ok=ok, text=text, raw=text)

    def chat_stream(self, messages: list[dict[str, str]]):
        """Stream deltas from engine. Yields raw deltas (may include ``` ```)."""
        for delta in self._bridge.chat_stream(messages):
            yield delta

    def health(self) -> EngineResult:
        """Quick health check."""
        return self.chat([{"role": "user", "content": "ping"}])

    def close(self):
        """Close the underlying bridge."""
        self._bridge.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
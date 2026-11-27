"""Tests for the Maya AI engine bridge (custom/engine/bridge.py).

Integration tests (health, list_models, chat, chat_stream) require the
Lemonade server at http://localhost:13305 to be running. The graceful
failure test uses a dead port and works without the server.
"""

from __future__ import annotations



from custom.engine.bridge import EngineBridge, EngineError


# ── Configuration ───────────────────────────────────────────────────

def test_bridge_reads_settings_from_yaml() -> None:
    """Bridge reads host/model/timeouts from settings.yaml — never hardcoded."""
    b = EngineBridge()
    assert b.host == "http://localhost:13305"
    assert b.model == "Qwen3.5-2B-GGUF"
    assert b.fallback_model == "qwen3-1.7b-instruct-q4_k_m"
    assert b.timeout == 60
    assert b.temperature == 0.7
    assert b.max_tokens == 512
    assert b.mode == "direct"
    assert b.disable_thinking is True


def test_engine_error_is_runtime_error() -> None:
    """EngineError is a RuntimeError subclass."""
    assert issubclass(EngineError, RuntimeError)


# ── Health / discovery ──────────────────────────────────────────────

def test_health_ok() -> None:
    """Health check returns ok=True when Lemonade server is up."""
    b = EngineBridge()
    h = b.health()
    assert h["ok"] is True
    assert h["mode"] == "direct"
    assert h["host"] == "http://localhost:13305"


def test_list_models() -> None:
    """list_models returns available model ids from the server."""
    b = EngineBridge()
    models = b.list_models()
    assert isinstance(models, list)
    # The configured model must exist in the server catalog, otherwise chat fails.
    assert b.model in models


# ── Chat ────────────────────────────────────────────────────────────

def test_chat_real_reply() -> None:
    """Exit criteria: chat() returns a real model reply through the bridge."""
    b = EngineBridge()
    b.timeout = 120  # first request may need model load time
    reply = b.chat([{"role": "user", "content": "Reply with exactly: BRIDGE REAL OK"}])
    assert "BRIDGE REAL OK" in reply
    assert not reply.startswith("[engine error]")


def test_chat_stream_yields_chunks() -> None:
    """chat_stream() yields text chunks incrementally."""
    b = EngineBridge()
    b.timeout = 120
    chunks = list(b.chat_stream([{"role": "user", "content": "Say hi in one word"}]))
    assert len(chunks) > 0
    full = "".join(chunks)
    assert len(full) > 0


# ── Graceful failure ────────────────────────────────────────────────

def test_graceful_failure_down_server() -> None:
    """Bridge never crashes when the engine is down — returns clear error."""
    b = EngineBridge(mode="direct")
    b.host = "http://localhost:99999"  # dead port
    b.timeout = 3

    h = b.health()
    assert h["ok"] is False
    assert "error" in h

    reply = b.chat([{"role": "user", "content": "hello"}])
    assert reply.startswith("[engine error]")

    # stream also yields an error instead of crashing
    chunks = list(b.chat_stream([{"role": "user", "content": "hello"}]))
    assert len(chunks) == 1
    assert chunks[0].startswith("[engine error]")


# ── OpenJarvis mode ─────────────────────────────────────────────────

def test_openjarvis_mode_jarvis_path() -> None:
    """OpenJarvis mode points at the correct jarvis.exe."""
    b = EngineBridge(mode="openjarvis")
    assert b._jarvis.name == "jarvis.exe"
    assert b._jarvis.is_file()

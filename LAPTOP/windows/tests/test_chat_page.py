"""Chat page tests: streaming UI, stop, retry, persona, health banner."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt

from app.services.chat_service import ChatService
from app.ui.pages.chat_page import ChatPage
from tests.fakes import FakeEngine


class GatedEngine(FakeEngine):
    """First chunk immediately, second only after the test opens the gate."""

    def __init__(self) -> None:
        super().__init__(chunks=[])
        self.gate = threading.Event()

    def chat_stream(self, messages):
        del messages
        yield "first"
        self.gate.wait(5)
        yield " second"


class FlakyEngine(FakeEngine):
    """Fails the first stream, then works (retry test)."""

    def __init__(self) -> None:
        super().__init__(chunks=[])
        self.calls = 0

    def chat_stream(self, messages):
        del messages
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("connection refused")
        yield "recovered"


def _page(qtbot, tmp_path: Path, engine=None, **kwargs) -> ChatPage:
    chat = ChatService(
        engine or FakeEngine(chunks=["Van", "akkam"]),
        tmp_path / "chat_history.json",
        persona_loader=lambda name: f"PROMPT:{name}",
        **kwargs,
    )
    page = ChatPage(chat, chat.engine)
    qtbot.addWidget(page)
    page.show()
    return page


def test_send_streams_reply_into_bubbles(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path)

    page.composer.setPlainText("hi")
    page.send_button.click()

    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)
    assert page.bubbles() == [("user", "hi"), ("assistant", "Vanakkam")]
    assert page.composer.toPlainText() == ""


def test_empty_input_does_nothing(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path)

    page.send()

    assert page.bubbles() == []
    assert not page.is_generating


def test_stop_cancels_and_shows_info_banner(qtbot, tmp_path) -> None:
    engine = GatedEngine()
    page = _page(qtbot, tmp_path, engine)

    page.composer.setPlainText("hi")
    page.send()
    qtbot.waitUntil(lambda: page.is_generating, timeout=2000)
    qtbot.waitUntil(lambda: "first" in page.bubbles()[-1][1], timeout=3000)

    page.stop()
    engine.gate.set()
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert "Stopped" in page.banner_text
    # The partial text stays visible; it is simply not persisted.
    assert page.bubbles() == [("user", "hi"), ("assistant", "first")]
    assert page.chat.messages() == []


def test_error_banner_and_retry(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path, FlakyEngine())

    page.composer.setPlainText("hi")
    page.send()
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert "could not reach" in page.banner_text.lower() or "chat failed" in page.banner_text.lower()
    assert page.bubbles() == [("user", "hi")]

    page.retry()
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert page.bubbles() == [("user", "hi"), ("assistant", "recovered")]
    assert page.banner_text == ""


def test_persona_switch_without_ask_clears_transcript(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path)
    page.composer.setPlainText("hi")
    page.send()
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert page.switch_persona("teacher", ask=False) is True

    assert page.bubbles() == []
    assert page.persona_combo.currentData() == "teacher"
    assert page.chat.persona == "teacher"


def test_new_chat_clears_transcript(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path)
    page.composer.setPlainText("hi")
    page.send()
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert page.new_chat(ask=False) is True

    assert page.bubbles() == []
    assert page.chat.messages() == []


def test_enter_sends_and_shift_enter_does_not(qtbot, tmp_path) -> None:
    page = _page(qtbot, tmp_path)

    page.composer.setPlainText("hi")
    qtbot.keyClick(page.composer, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert page.bubbles() == []

    qtbot.keyClick(page.composer, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not page.is_generating, timeout=5000)

    assert page.bubbles()[0] == ("user", "hi")


def test_health_failure_shows_banner(qtbot, tmp_path) -> None:
    engine = FakeEngine()
    engine.health = lambda: {"ok": False, "error": "Lemonade is not running"}
    page = _page(qtbot, tmp_path, engine)

    qtbot.waitUntil(lambda: "offline" in page.banner_text.lower(), timeout=5000)
    assert "Lemonade is not running" in page.banner_text


def test_health_success_sets_model_label(qtbot, tmp_path) -> None:
    engine = FakeEngine()
    engine.health = lambda: {"ok": True, "models": ["qwen3.5-2b-FLM"]}
    page = _page(qtbot, tmp_path, engine)

    qtbot.waitUntil(lambda: page._model_label.text() == "qwen3.5-2b-FLM", timeout=5000)
    assert page.banner_text == ""


def test_history_loads_on_open(qtbot, tmp_path) -> None:
    first = ChatService(
        FakeEngine(reply="stored reply"),
        tmp_path / "chat_history.json",
        persona_loader=lambda name: "P",
    )
    first.send("remember me")

    page = _page(qtbot, tmp_path)

    assert page.bubbles() == [
        ("user", "remember me"),
        ("assistant", "stored reply"),
    ]


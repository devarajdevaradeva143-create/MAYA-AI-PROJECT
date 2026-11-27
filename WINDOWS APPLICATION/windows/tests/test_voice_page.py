"""Voice page transcript log keeps only the last 10 lines (no Qt sender crash)."""

from __future__ import annotations

import pytest

from app.ui.pages.voice_page import VoicePage


class FakeVoice:
    listen_seconds = 1
    is_speaking = False

    def __init__(self, transcript: str = "hello Maya") -> None:
        self.transcript = transcript
        self.spoken: list[str] = []

    def listen_once(self, seconds: int, lang: str) -> str:
        return self.transcript

    def speak(self, text: str, **_kwargs) -> None:
        self.spoken.append(text)


class FakeWake:
    def listen(self, seconds: int) -> None:
        pass

    def status(self) -> dict[str, bool]:
        return {"clap": True, "name": True}


class FakeChat:
    def __init__(self, *, engine_enabled: bool = True, cloud_available: bool = False) -> None:
        self.engine_enabled = engine_enabled
        self.cloud_available = cloud_available
        self.local_messages: list[str] = []
        self.cloud_messages: list[str] = []

    def stream(self, text: str):
        self.local_messages.append(text)
        yield "Hello from local Maya"

    def stream_cloud(self, text: str):
        self.cloud_messages.append(text)
        yield "Hello from cloud Maya"

    def cancel(self) -> None:
        pass


@pytest.fixture
def page(qtbot):
    p = VoicePage()
    qtbot.addWidget(p)
    return p


def test_transcript_appends_via_signal(page: VoicePage) -> None:
    # emitted the same way the wake worker does it; must not raise
    page.transcript_added.emit("user", "hello maya")
    assert "user: hello maya" in page._transcript_view.toPlainText()


def test_transcript_keeps_last_ten(page: VoicePage) -> None:
    for i in range(14):
        page._append_transcript_local("user", f"line {i}")
    text = page._transcript_view.toPlainText()
    assert "line 13" in text
    assert "line 3" not in text
    assert len(page._transcripts) == 10
    assert page._transcripts[0] == ("user", "line 4")


def test_push_to_talk_sends_transcript_to_local_chat(qtbot) -> None:
    voice = FakeVoice()
    chat = FakeChat()
    page = VoicePage(voice=voice, wake=FakeWake(), chat=chat)
    qtbot.addWidget(page)

    page._listen_worker()

    assert chat.local_messages == ["hello Maya"]
    assert chat.cloud_messages == []
    assert voice.spoken == ["Hello from local Maya"]
    assert page._transcripts[-1] == ("assistant", "Hello from local Maya")


def test_push_to_talk_uses_cloud_when_local_engine_is_off(qtbot) -> None:
    voice = FakeVoice()
    chat = FakeChat(engine_enabled=False, cloud_available=True)
    page = VoicePage(voice=voice, wake=FakeWake(), chat=chat)
    qtbot.addWidget(page)

    page._listen_worker()

    assert chat.local_messages == []
    assert chat.cloud_messages == ["hello Maya"]
    assert voice.spoken == ["Hello from cloud Maya"]

"""Voice page transcript log keeps only the last 10 lines (no Qt sender crash)."""

from __future__ import annotations

import pytest

from app.ui.pages.voice_page import VoicePage


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

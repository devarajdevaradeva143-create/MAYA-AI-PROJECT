"""Voice page — push-to-talk, TTS, wake words, orb, and transcript log (Phase 4)."""

from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.chat_service import ChatService
from app.services.voice_service import VoiceAdapter, VoiceError
from app.services.wake_service import WakeAdapter


class VoicePage(QWidget):
    """Maya voice UI: orb, PTT, TTS toggle, wake status, last 10 transcripts, language selector."""

    transcript_added = Signal(str, str)  # role, text

    def __init__(self, voice: VoiceAdapter | None = None, wake: WakeAdapter | None = None,
                 chat: ChatService | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._voice = voice or VoiceAdapter()
        self._wake = wake or WakeAdapter()

        # Transcript log (last 10 entries, local only)
        self._transcripts: deque[tuple[str, str]] = deque(maxlen=10)

        # Wake-status polling timer
        self._wake_timer = QTimer(self)
        self._wake_timer.timeout.connect(self._poll_wake)
        self._wake_timer.start(1500)  # poll every 1.5 s

        # Connect wake events to transcript
        self._wake_events: list[dict[str, Any]] = []
        self._wake.listen(seconds=0)  # just to init

        self._build_ui()
        self._update_ui()

    # -- ui -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top control row ---
        top = QHBoxLayout()
        top.setContentsMargins(24, 16, 24, 8)
        top.setSpacing(12)

        # Language selector
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("Tamil", "ta")
        self._lang_combo.setFixedWidth(140)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_change)
        self._selected_lang = str(self._lang_combo.currentData() or "en")

        # Orb button (click-to-toggle listen/clap)
        self._orb_button = QPushButton("🎤")
        self._orb_button.setObjectName("orbButton")
        self._orb_button.setFixedSize(64, 64)
        self._orb_button.setCheckable(True)
        self._orb_button.clicked.connect(self._on_orb_toggle)

        # TTS test button
        self._tts_button = QPushButton("TTS Test")
        self._tts_button.setFixedSize(96, 32)
        self._tts_button.clicked.connect(self._on_tts_test)

        top.addWidget(QLabel("Language:"))
        top.addWidget(self._lang_combo)
        top.addStretch(1)
        top.addWidget(self._orb_button)
        top.addWidget(self._tts_button)

        layout.addLayout(top)

        # --- Live transcript ---
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("chatScroll")
        container = QWidget()
        container.setObjectName("pageBody")
        self._transcript_layout = QVBoxLayout(container)
        self._transcript_layout.setContentsMargins(24, 8, 24, 8)
        self._transcript_layout.setSpacing(6)
        self._transcript_layout.addStretch(1)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)

        # --- Last 10 transcripts ---
        left = QVBoxLayout()
        left.setContentsMargins(24, 0, 12, 0)
        left.setSpacing(6)

        self._transcript_label = QLabel("Last 10 transcripts")
        self._transcript_label.setObjectName("emptyHint")
        left.addWidget(self._transcript_label)

        self._transcript_view = QPlainTextEdit()
        self._transcript_view.setReadOnly(True)
        self._transcript_view.setMaximumHeight(120)
        self._transcript_view.setPlainText("")
        left.addWidget(self._transcript_view)

        # Wake status chip
        self._wake_label = QLabel("Wake: clap enabled, name pending")
        self._wake_label.setObjectName("statusChip")
        self._wake_label.setFixedHeight(24)
        left.addWidget(self._wake_label)

        left.addStretch(1)
        layout.addLayout(left, 0)

        # Wire up transcript signals
        self.transcript_added.connect(self._append_transcript_local)

    # -- behaviour ----------------------------------------------------

    def _on_orb_toggle(self, checked: bool) -> None:
        if checked:
            # Start listening
            self._orb_button.setText("Listening…")
            self._wake.listen(seconds=6)
            # Start the wake loop in a thread
            self._wake.start_name_wake()
        else:
            # Stop listening
            self._wake.stop_name_wake()
            self._wake.stop()
            self._orb_button.setText("🎤")

    def _on_lang_change(self, index: int) -> None:
        lang = str(self._lang_combo.currentData())
        self._selected_lang = lang
        try:
            st = self._voice.status()
            if lang == "ta":
                available = bool(st.get("stt", {}).get("tamil_stt_available")) or st.get("tts", {}).get("tamil_available")
                note = "Tamil ready" if available else "Tamil needs models"
            else:
                note = "English"
        except Exception:
            note = "English" if lang != "ta" else "Tamil"
        self._wake_label.setText(f"Wake: clap enabled, STT {note}")

    def _on_tts_test(self) -> None:
        try:
            if getattr(self, "_selected_lang", "en") == "ta":
                text = "வணக்கம், நான் மாயா. இது ஒரு தமிழ் குரல் சோதனை."
                self._voice.speak(text, lang="tamil")
            else:
                text = "Vanakkam da! Enna aachu? Konjam rest eduthukko."
                self._voice.speak(text, lang="english")
            self.transcript_added.emit("assistant", text)
        except VoiceError as e:
            self.transcript_added.emit("system", f"TTS error: {e}")

    # -- wake polling -------------------------------------------------

    def _poll_wake(self) -> None:
        """Update wake status chip from the adapter's status()."""
        try:
            st = self._wake.status()
        except Exception:
            return
        clap = "clap " + ("on" if st.get("clap") else "off")
        name = "name " + ("on" if st.get("name") else "off")
        self._wake_label.setText(f"Wake: {clap}, {name}")

    # -- transcript log -----------------------------------------------

    def _append_transcript_local(self, role: str, text: str) -> None:
        """Add a line to the last-10 transcript view.

        Qt delivers `transcript_added` on the UI thread even when it is
        emitted from the wake worker thread, so no extra guard is needed.
        """
        self._transcripts.append((role, text))
        lines = [f"{r}: {t}" for r, t in self._transcripts]
        self._transcript_view.setPlainText("\n".join(lines[-10:]))

    # -- public API ---------------------------------------------------

    def update_from_signals(self) -> None:
        """Called from outside (e.g., wake-service event → voice reply)."""
        pass

    def _update_ui(self) -> None:
        """Refresh the wake label from the current status."""
        try:
            st = self._wake.status()
            clap = "clap on" if st.get("clap") else "clap off"
            name = "name on" if st.get("name") else "name off"
            self._wake_label.setText(f"Wake: {clap}, {name}")
        except Exception:
            pass
"""Chat page — streaming replies, persona switch, local history (Phase 3)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.chat_service import MAX_INPUT_CHARS, PERSONA_LABELS, ChatService
from app.ui.widgets.message_bubble import MessageBubble
from app.ui.workers import ChatStreamWorker, HealthWorker


class ChatPage(QWidget):
    """Maya chat with streaming, stop, retry and persona switching."""

    engine_status = Signal(str, str)  # text, state (ok/warn/error)
    reply_finished = Signal(str)
    generation_changed = Signal(bool)

    def __init__(self, chat: ChatService, engine: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chat = chat
        self._engine = engine
        self._worker: ChatStreamWorker | None = None
        self._health_worker: HealthWorker | None = None
        self._reply_bubble: MessageBubble | None = None
        self._last_text = ""
        self._rows: list[QWidget] = []
        self._loading_combo = False
        self._banner_kind = ""

        self._build_ui()
        self._load_combo()
        self._load_history()
        QTimer.singleShot(0, self.refresh_health)

    # -- ui -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # top bar
        top = QHBoxLayout()
        top.setContentsMargins(24, 16, 24, 8)
        top.setSpacing(10)

        self._persona_combo = QComboBox()
        self._persona_combo.setFixedWidth(190)
        self._persona_combo.currentIndexChanged.connect(self._on_persona_index)

        self._model_label = QLabel("")
        self._model_label.setObjectName("emptyHint")

        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_chat_button.clicked.connect(lambda: self.new_chat())

        top.addWidget(self._persona_combo)
        top.addWidget(self._model_label, 1)
        top.addWidget(self._new_chat_button)
        layout.addLayout(top)

        # banner
        self._banner = QFrame()
        self._banner.setObjectName("banner")
        self._banner.setProperty("state", "error")
        banner_layout = QHBoxLayout(self._banner)
        banner_layout.setContentsMargins(16, 10, 12, 10)
        self._banner_label = QLabel("")
        self._banner_label.setObjectName("bannerText")
        self._banner_label.setWordWrap(True)
        self._banner_retry = QPushButton("Retry")
        self._banner_retry.setObjectName("iconButton")
        self._banner_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self._banner_retry.clicked.connect(self.retry)
        banner_layout.addWidget(self._banner_label, 1)
        banner_layout.addWidget(self._banner_retry)

        banner_holder = QVBoxLayout()
        banner_holder.setContentsMargins(24, 0, 24, 8)
        banner_holder.addWidget(self._banner)
        layout.addLayout(banner_holder)
        self._banner.hide()

        # transcript
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("chatScroll")
        container = QWidget()
        container.setObjectName("pageBody")
        self._messages_layout = QVBoxLayout(container)
        self._messages_layout.setContentsMargins(24, 8, 24, 8)
        self._messages_layout.setSpacing(10)
        self._messages_layout.addStretch(1)
        self._scroll.setWidget(container)
        layout.addWidget(self._scroll, 1)

        # composer
        composer = QHBoxLayout()
        composer.setContentsMargins(24, 10, 24, 6)
        composer.setSpacing(10)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Type a message…")
        self._input.setFixedHeight(84)
        self._input.installEventFilter(self)

        self._send_button = QPushButton("Send")
        self._send_button.setObjectName("primaryButton")
        self._send_button.setFixedSize(96, 40)
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button.clicked.connect(self.send)

        self._mic_button = QPushButton("🎤")
        self._mic_button.setFixedSize(44, 40)
        self._mic_button.setEnabled(False)
        self._mic_button.setToolTip("Voice input arrives in Phase 4")

        composer.addWidget(self._input, 1)
        composer.addWidget(self._mic_button)
        composer.addWidget(self._send_button)
        layout.addLayout(composer)

        hint = QLabel("Enter to send · Shift+Enter for a new line · Replies stay on this laptop")
        hint.setObjectName("emptyHint")
        hint.setContentsMargins(24, 0, 24, 12)
        layout.addWidget(hint)

    # -- badge / health ----------------------------------------------

    def refresh_health(self) -> None:
        if self._health_worker is not None and self._health_worker.isRunning():
            return
        worker = HealthWorker(self._engine, self)
        worker.result.connect(self._on_health)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._clear_health_worker)
        self._health_worker = worker
        worker.start()

    def _clear_health_worker(self) -> None:
        self._health_worker = None

    def _on_health(self, ok: bool, detail: str, model: str) -> None:
        if ok:
            if self._banner_kind in {"", "engine"}:
                self._hide_banner()
            label = model or self._chat.model
            self._model_label.setText(label)
            self.engine_status.emit("Engine ready", "ok")
        else:
            self._show_banner(f"Engine offline — {detail}", retry=False, kind="engine")
            self.engine_status.emit("Engine offline", "error")

    def shutdown(self) -> None:
        """Stop workers before the window disappears (prevents QThread crashes)."""
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
            self._worker = None
        if self._health_worker is not None:
            self._health_worker.wait(3000)
            self._health_worker = None

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt signature
        self.shutdown()
        super().closeEvent(event)

    # -- transcript ---------------------------------------------------

    def _append_bubble(self, role: str, text: str = "") -> MessageBubble:
        bubble = MessageBubble(role, text)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, row)
        self._rows.append(row)
        if self._should_scroll():
            self._scroll_to_bottom()
        return bubble

    def _clear_transcript(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self._reply_bubble = None

    def _load_history(self) -> None:
        for item in self._chat.messages():
            role = str(item.get("role", ""))
            if role in {"user", "assistant"}:
                self._append_bubble(role, str(item.get("content", "")))
        self._scroll_to_bottom()

    def _should_scroll(self) -> bool:
        bar = self._scroll.verticalScrollBar()
        return bar.value() >= bar.maximum() - 48

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, self._do_scroll)

    def _do_scroll(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- persona ------------------------------------------------------

    def _load_combo(self) -> None:
        self._loading_combo = True
        self._persona_combo.clear()
        for key, label in PERSONA_LABELS.items():
            self._persona_combo.addItem(label, key)
        index = self._persona_combo.findData(self._chat.persona)
        self._persona_combo.setCurrentIndex(max(0, index))
        self._loading_combo = False

    def _on_persona_index(self, _index: int) -> None:
        if self._loading_combo:
            return
        key = str(self._persona_combo.currentData())
        if key != self._chat.persona:
            self.switch_persona(key, ask=True)

    def switch_persona(self, key: str, ask: bool = True) -> bool:
        if key == self._chat.persona:
            return True
        if ask and self._chat.messages():
            answer = QMessageBox.question(
                self,
                "Start a new chat?",
                "Switching persona starts a new chat. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._load_combo()
                return False
        self._chat.set_persona(key)
        self._clear_transcript()
        self._load_combo()
        self._hide_banner()
        return True

    def new_chat(self, ask: bool = True) -> bool:
        if self._worker is not None:
            return False
        if ask and self._chat.messages():
            answer = QMessageBox.question(
                self,
                "New chat?",
                "Clear this conversation and start fresh?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self._chat.new_chat()
        self._clear_transcript()
        self._hide_banner()
        self._last_text = ""
        return True

    # -- generation ---------------------------------------------------

    def send(self) -> None:
        if self._worker is not None:
            self.stop()
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        if len(text) > MAX_INPUT_CHARS:
            self._show_banner(f"Message is longer than {MAX_INPUT_CHARS} characters", retry=False)
            return
        self._input.clear()
        self._append_bubble("user", text)
        self._start_stream(text)

    def _start_stream(self, text: str) -> None:
        self._last_text = text
        self._hide_banner()
        self._reply_bubble = self._append_bubble("assistant", "")
        self._scroll_to_bottom()
        self._set_generating(True)

        worker = ChatStreamWorker(self._chat, text, self)
        worker.chunk.connect(self._on_chunk)
        worker.completed.connect(self._on_completed)
        worker.cancelled.connect(self._on_cancelled)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_chunk(self, piece: str) -> None:
        if self._reply_bubble is not None:
            self._reply_bubble.append(piece)
        if self._should_scroll():
            self._scroll_to_bottom()

    def _on_completed(self, text: str) -> None:
        if self._reply_bubble is not None and not self._reply_bubble.text().strip() and text:
            self._reply_bubble.set_text(text)
        self._finish_generation()
        self.reply_finished.emit(text)

    def _on_cancelled(self) -> None:
        self._drop_empty_reply()
        self._show_banner(
            "Stopped. The partial reply was not saved.",
            state="info",
            retry=False,
            kind="info",
        )
        self._finish_generation()

    def _on_failed(self, error_type: str, message: str) -> None:
        self._drop_empty_reply()
        self._show_banner(_friendly_error(error_type, message), retry=True, kind="chat")
        self._finish_generation()

    def _finish_generation(self) -> None:
        self._worker = None
        self._reply_bubble = None
        self._set_generating(False)

    def _drop_empty_reply(self) -> None:
        bubble = self._reply_bubble
        if bubble is not None and not bubble.text().strip() and self._rows:
            row = self._rows.pop()
            row.setParent(None)
            row.deleteLater()
        self._reply_bubble = None

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()

    def retry(self) -> None:
        if self._worker is not None or not self._last_text:
            return
        self._start_stream(self._last_text)

    def _set_generating(self, generating: bool) -> None:
        self._send_button.setText("Stop" if generating else "Send")
        self._input.setEnabled(not generating)
        self._persona_combo.setEnabled(not generating)
        self._new_chat_button.setEnabled(not generating)
        self.generation_changed.emit(generating)

    # -- banner -------------------------------------------------------

    def _show_banner(
        self,
        text: str,
        state: str = "error",
        retry: bool = False,
        kind: str = "chat",
    ) -> None:
        self._banner_label.setText(text)
        self._banner_kind = kind
        self._banner.setProperty("state", state)
        self._banner.style().unpolish(self._banner)
        self._banner.style().polish(self._banner)
        self._banner_retry.setVisible(retry)
        self._banner.show()

    def _hide_banner(self) -> None:
        self._banner_kind = ""
        self._banner.hide()

    # -- input --------------------------------------------------------

    def eventFilter(self, obj: Any, event: QEvent) -> bool:
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if key_event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not (
                key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self.send()
                return True
        return super().eventFilter(obj, event)

    # -- test seams ---------------------------------------------------

    @property
    def is_generating(self) -> bool:
        return self._worker is not None

    @property
    def composer(self) -> QPlainTextEdit:
        return self._input

    @property
    def send_button(self) -> QPushButton:
        return self._send_button

    @property
    def persona_combo(self) -> QComboBox:
        return self._persona_combo

    @property
    def banner_text(self) -> str:
        return self._banner_label.text() if self._banner.isVisible() else ""

    @property
    def chat(self) -> ChatService:
        return self._chat

    def bubbles(self) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for row in self._rows:
            bubble = row.findChild(MessageBubble)
            if bubble is not None:
                found.append((bubble.role, bubble.text()))
        return found


def _friendly_error(error_type: str, message: str) -> str:
    lowered = message.lower()
    if "timeout" in error_type.lower() or "timed out" in lowered:
        return "Maya did not answer in time. Is Lemonade still running?"
    if "unavailable" in error_type.lower() or "connect" in lowered:
        return "Maya could not reach the engine. Start Lemonade and retry."
    return f"Chat failed: {message or error_type}"

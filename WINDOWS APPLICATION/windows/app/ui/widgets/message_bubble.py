"""Chat message bubble."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

BUBBLE_MAX_WIDTH = 620


class MessageBubble(QFrame):
    """Rounded bubble; `append` is used while the reply streams in."""

    def __init__(
        self,
        role: str,
        text: str = "",
        parent: QWidget | None = None,
        source: str = "",
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._source = source
        self.setObjectName("bubbleUser" if role == "user" else "bubbleAssistant")
        self.setMaximumWidth(BUBBLE_MAX_WIDTH)

        self._text = text
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setMaximumWidth(BUBBLE_MAX_WIDTH - 32)

        self._meta = QLabel(source)
        self._meta.setObjectName("bubbleMeta")
        self._meta.setVisible(bool(source))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        layout.addWidget(self._meta)
        layout.addWidget(self._label)

    @property
    def source(self) -> str:
        """Who produced this reply ("Lemonade", "Gemini"), empty when unknown."""
        return self._source

    def set_placeholder(self, text: str) -> None:
        """Show a hint until the first chunk arrives (never stored as text)."""
        if not self._text:
            self._label.setText(text)

    def append(self, chunk: str) -> None:
        self._text += chunk
        self._label.setText(self._text)

    def set_text(self, text: str) -> None:
        self._text = text
        self._label.setText(text)

    def text(self) -> str:
        return self._text

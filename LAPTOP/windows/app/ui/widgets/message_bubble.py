"""Chat message bubble."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

BUBBLE_MAX_WIDTH = 620


class MessageBubble(QFrame):
    """Rounded bubble; `append` is used while the reply streams in."""

    def __init__(self, role: str, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self.setObjectName("bubbleUser" if role == "user" else "bubbleAssistant")
        self.setMaximumWidth(BUBBLE_MAX_WIDTH)

        self._text = text
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._label.setMaximumWidth(BUBBLE_MAX_WIDTH - 32)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self._label)

    def append(self, chunk: str) -> None:
        self._text += chunk
        self._label.setText(self._text)

    def set_text(self, text: str) -> None:
        self._text = text
        self._label.setText(text)

    def text(self) -> str:
        return self._text

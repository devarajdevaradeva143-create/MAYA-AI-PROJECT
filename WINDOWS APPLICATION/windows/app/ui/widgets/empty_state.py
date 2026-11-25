"""Shared UI pieces used by several pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    """Centered icon + title + hint; replaced by the real page phase by phase."""

    def __init__(self, icon: str, title: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageBody")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setObjectName("emptyIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint_label = QLabel(hint)
        hint_label.setObjectName("emptyHint")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        hint_label.setMaximumWidth(440)

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)

"""English Teacher page — grammar, vocabulary and pronunciation coaching (Phase 7)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.engine_service import EngineAdapter
from app.services.teacher_service import LEVELS, TOPICS, TeacherService

LESSONS: dict[str, dict[str, Any]] = {
    "Vocabulary": {
        "prompt": "What does 'serendipity' mean?\nA) Sadness  B) Chance joy  C) Anger  D) Boredom",
        "answer": "b",
        "explain": "'Serendipity' = a happy accidental discovery.",
    },
    "Grammar": {
        "prompt": "Convert to Present Perfect:\n'I saw that movie last year.'",
        "answer": "i have seen that movie last year",
        "explain": "Use have/has + past participle for unspecified past time.",
    },
    "Pronunciation": {
        "prompt": "Word: serendipity  /ˌserənˈdipədɪ/\nListen, then type what you heard.",
        "answer": None,
        "explain": "Stress on the third syllable: ser-en-DIP-i-ty.",
    },
    "Idioms": {
        "prompt": "Which sentence uses 'break the ice' correctly?\nA) The ice was cold.\nB) He broke the frozen lake.\nC) He started the conversation.",
        "answer": "c",
        "explain": "'Break the ice' = initiate conversation in a social setting.",
    },
}


class _LessonWorker(QThread):
    finished = Signal(object)  # lesson dict

    def __init__(self, service: TeacherService, topic: str, level: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._service = service
        self._topic = topic
        self._level = level

    def run(self) -> None:
        try:
            lesson = self._service.generate_lesson(self._topic, self._level)
        except Exception as exc:  # noqa: BLE001
            lesson = {"error": str(exc)}
        self.finished.emit(lesson)


class TeacherPage(QWidget):
    """Maya English Teacher: vocabulary, grammar, pronunciation, idioms lessons."""

    def __init__(
        self,
        voice: Any = None,
        parent: QWidget | None = None,
        engine: Any = None,
        teacher_service: TeacherService | None = None,
        progress_path: Any = None,
    ) -> None:
        super().__init__(parent)
        self._voice = voice
        self._engine = engine
        self._teacher_service = teacher_service or TeacherService(engine=engine, progress_path=progress_path)
        self._current: str | None = None
        self._ai_lesson: dict[str, Any] | None = None
        self._ai_worker: _LessonWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(12)

        welcome = QLabel(
            "English Teacher — Maya's personal grammar & vocabulary coach\n"
            "Select a lesson type below to get started."
        )
        welcome.setObjectName("emptyHint")
        welcome.setWordWrap(True)
        layout.addWidget(welcome)

        # --- AI lesson row ---
        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        ai_row.addWidget(QLabel("AI lesson:"))
        self._topic_combo = QComboBox()
        for t in TOPICS:
            self._topic_combo.addItem(t, t)
        ai_row.addWidget(self._topic_combo)
        self._level_combo = QComboBox()
        for lvl in LEVELS:
            self._level_combo.addItem(lvl, lvl)
        ai_row.addWidget(self._level_combo)
        self._ai_button = QPushButton("New AI lesson")
        self._ai_button.setFixedHeight(32)
        self._ai_button.clicked.connect(self._request_ai_lesson)
        ai_row.addWidget(self._ai_button)
        ai_row.addStretch(1)
        self._progress_label = QLabel("")
        self._progress_label.setObjectName("emptyHint")
        ai_row.addWidget(self._progress_label)
        layout.addLayout(ai_row)

        self._ai_status = QLabel("")
        self._ai_status.setObjectName("emptyHint")
        layout.addWidget(self._ai_status)

        # --- Lesson grid ---
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 8, 0, 0)
        self._grid.setSpacing(12)

        for i, title in enumerate(LESSONS):
            row, col = divmod(i, 2)
            card = QFrame()
            card.setFrameStyle(QFrame.Shape.StyledPanel)
            card.setStyleSheet(
                "QFrame { border-radius: 8px; background-color: #14141c; margin: 4px; }"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(4)

            btn = QPushButton(title)
            btn.setObjectName("navButton")
            btn.setFixedHeight(60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=title: self._lesson_selected(t))
            cl.addWidget(btn)

            lbl = QLabel(LESSONS[title]["prompt"].split("\n")[0])
            lbl.setObjectName("emptyHint")
            lbl.setWordWrap(True)
            cl.addWidget(lbl)

            self._grid.addWidget(card, row, col)

        layout.addLayout(self._grid, 1)

        # --- Lesson area ---
        self._lesson_area = QFrame()
        self._lesson_area.setVisible(False)
        la = QVBoxLayout(self._lesson_area)
        la.setContentsMargins(0, 0, 0, 0)
        la.setSpacing(8)

        self._lesson_label = QLabel("Select a lesson above")
        self._lesson_label.setObjectName("cardLabel")
        la.addWidget(self._lesson_label)

        self._lesson_text = QPlainTextEdit()
        self._lesson_text.setReadOnly(True)
        self._lesson_text.setMaximumHeight(160)
        la.addWidget(self._lesson_text)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Your answer...")
        la.addWidget(self._input)

        btn_row = QHBoxLayout()
        self._submit = QPushButton("Submit")
        self._submit.setFixedHeight(32)
        self._submit.clicked.connect(self._submit_answer)
        btn_row.addWidget(self._submit)

        self._hear_btn = QPushButton("Hear word")
        self._hear_btn.setFixedHeight(32)
        self._hear_btn.clicked.connect(self._hear_word)
        btn_row.addWidget(self._hear_btn)

        self._back_btn = QPushButton("Back to lessons")
        self._back_btn.setFixedHeight(32)
        self._back_btn.clicked.connect(self._back_to_grid)
        btn_row.addWidget(self._back_btn)
        la.addLayout(btn_row)

        self._feedback = QLabel("")
        self._feedback.setObjectName("emptyHint")
        self._feedback.setWordWrap(True)
        la.addWidget(self._feedback)

        layout.addWidget(self._lesson_area, 1)

        self._refresh_progress()

    # -- engine -------------------------------------------------------
    def _ensure_engine(self) -> Any:
        if self._engine is None:
            try:
                self._engine = EngineAdapter()
            except Exception:
                self._engine = None
        if self._teacher_service is not None and getattr(self._teacher_service, "_engine", None) is None:
            self._teacher_service._engine = self._engine
        return self._engine

    # -- AI lesson ----------------------------------------------------
    def _request_ai_lesson(self) -> None:
        self._ensure_engine()
        topic = str(self._topic_combo.currentData() or self._topic_combo.currentText())
        level = str(self._level_combo.currentData() or self._level_combo.currentText())
        self._ai_button.setEnabled(False)
        self._ai_status.setText("Maya is preparing a lesson…")
        worker = _LessonWorker(self._teacher_service, topic, level, self)
        worker.finished.connect(self._on_ai_lesson)
        self._ai_worker = worker
        worker.start()

    def _on_ai_lesson(self, lesson: Any) -> None:
        self._ai_button.setEnabled(True)
        self._ai_worker = None
        if isinstance(lesson, dict) and lesson.get("error"):
            self._ai_status.setText(f"Error: {lesson['error']}")
            return
        if not isinstance(lesson, dict):
            self._ai_status.setText("Could not generate a lesson.")
            return
        self._ai_lesson = lesson
        self._ai_status.setText(f"AI lesson ({lesson.get('source', 'ai')})")
        self._current = None
        self._lesson_label.setText(f"Lesson: {lesson.get('topic')} ({lesson.get('level')})")
        self._lesson_text.setPlainText(str(lesson.get("prompt", "")))
        self._feedback.setText("")
        self._input.clear()
        self._input.setPlaceholderText("Your answer...")
        self._grid.setEnabled(False)
        self._lesson_area.setVisible(True)
        self._refresh_progress()

    def set_ai_lesson(self, lesson: dict[str, Any]) -> None:
        """Test seam: apply an already-generated lesson without a worker."""
        self._on_ai_lesson(lesson)

    # -- quick lessons ------------------------------------------------
    def _lesson_selected(self, lesson: str) -> None:
        self._current = lesson
        self._ai_lesson = None
        data = LESSONS[lesson]
        self._lesson_label.setText(f"Lesson: {lesson}")
        self._lesson_text.setPlainText(data["prompt"])
        self._feedback.setText("")
        self._input.clear()
        self._input.setPlaceholderText("Your answer...")
        self._grid.setEnabled(False)
        self._lesson_area.setVisible(True)

    def _submit_answer(self) -> None:
        if self._ai_lesson is not None:
            text = self._input.text().strip()
            if not text:
                self._feedback.setText("Type an answer first.")
                return
            result = self._teacher_service.check_answer(self._ai_lesson, text)
            correct = result.get("correct")
            if correct is True:
                self._feedback.setText(f"✅ Correct! {result.get('feedback', '')}")
            elif correct is False:
                self._feedback.setText(f"❌ {result.get('feedback', '')}")
            else:
                self._feedback.setText(str(result.get("feedback", "")))
            self._input.clear()
            self._refresh_progress()
            return

        if self._current is None:
            return
        data = LESSONS[self._current]
        text = self._input.text().strip()
        if not text:
            self._feedback.setText("Type an answer first.")
            return

        answer = data.get("answer")
        if answer is None:
            self._feedback.setText(f"ℹ {data['explain']}")
            self._input.clear()
            return

        normalized = " ".join(text.lower().split()).strip(" .,!?")
        if normalized == answer:
            self._feedback.setText(f"✅ Correct! {data['explain']}")
        else:
            self._feedback.setText(f"❌ Not quite. Answer: {answer}. {data['explain']}")
        self._input.clear()

    def _hear_word(self) -> None:
        if self._voice is None:
            self._feedback.setText("Voice not available.")
            return
        try:
            self._voice.speak("serendipity")
            self._feedback.setText("Speaking: serendipity")
        except Exception as exc:  # noqa: BLE001
            self._feedback.setText(f"Voice error: {exc}")

    def _back_to_grid(self) -> None:
        self._grid.setEnabled(True)
        self._lesson_area.setVisible(False)
        self._current = None
        self._ai_lesson = None
        self._input.clear()
        self._feedback.setText("")

    def _refresh_progress(self) -> None:
        try:
            prog = self._teacher_service.progress()
            totals = prog.get("totals", {})
            attempts = totals.get("attempts", 0)
            correct = totals.get("correct", 0)
            streak = prog.get("streak", 0)
            self._progress_label.setText(f"Progress: {correct}/{attempts} correct · streak {streak}")
        except Exception:
            pass

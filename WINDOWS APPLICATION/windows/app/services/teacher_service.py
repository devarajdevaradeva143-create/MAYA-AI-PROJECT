"""AI English Teacher service — adapter over the shared custom core.

Qt-free and testable. Delegates lesson generation and SQLite progress
persistence to ``custom.tools.teacher_service.TeacherService``.
"""

from __future__ import annotations

from typing import Any

from custom.tools.teacher_service import (
    LEVELS as _LEVELS,
)
from custom.tools.teacher_service import (
    TOPICS as _TOPICS,
)
from custom.tools.teacher_service import (
    TeacherService as CoreTeacherService,
)

TOPICS = _TOPICS
LEVELS = _LEVELS


class TeacherService:
    def __init__(
        self,
        engine: Any = None,
        progress_path: Any = None,
        db_path: Any = None,
        **kwargs: Any,
    ) -> None:
        self._core = CoreTeacherService(
            engine=engine, progress_path=progress_path, db_path=db_path, **kwargs
        )

    # allow UI to (re)attach an engine
    @property
    def _engine(self) -> Any:
        return self._core._engine

    @_engine.setter
    def _engine(self, value: Any) -> None:
        self._core._engine = value

    def generate_lesson(self, topic: str, level: str, lesson_type: str = "mixed") -> dict[str, Any]:
        return self._core.generate_lesson(topic, level, lesson_type)

    def check_answer(self, lesson_or_id: Any, user_answer: str) -> dict[str, Any]:
        return self._core.check_answer(lesson_or_id, user_answer)

    def progress(self) -> dict[str, Any]:
        return self._core.get_progress(None)

    def get_progress(self, lesson_id: Any = None) -> dict[str, Any]:
        return self._core.get_progress(lesson_id)

    def mark_complete(self, lesson_id: Any, score: int) -> dict[str, Any]:
        return self._core.mark_complete(lesson_id, score)

    def reset_progress(self) -> None:
        self._core.reset_progress()
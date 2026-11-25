"""AI teacher tests."""

from __future__ import annotations

from pathlib import Path

from app.services.teacher_service import TeacherService
from app.ui.pages.teacher_page import TeacherPage


def test_fallback_when_no_engine(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "p.json")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    assert lesson["source"] == "fallback"
    assert lesson["topic"] == "Vocabulary"


def test_ai_lesson_with_fake_engine(tmp_path: Path) -> None:
    class FakeEngine:
        def chat(self, messages):
            return '{"prompt": "What is 2+2?", "answer": "4", "explanation": "basic math"}'

    svc = TeacherService(engine=FakeEngine(), progress_path=tmp_path / "p.json")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    assert lesson["source"] == "ai"
    assert lesson["answer"] == "4"


def test_check_answer_and_progress(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "p.json")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    # fallback answer is "b"
    res = svc.check_answer(lesson, "b")
    assert res["correct"] is True
    prog = svc.progress()
    assert prog["totals"]["attempts"] == 1
    assert prog["totals"]["correct"] == 1
    assert prog["streak"] == 1


def test_progress_persists(tmp_path: Path) -> None:
    p = tmp_path / "p.json"
    svc = TeacherService(engine=None, progress_path=p)
    lesson = svc.generate_lesson("Grammar", "Beginner")
    svc.check_answer(lesson, "wrong")
    svc2 = TeacherService(engine=None, progress_path=p)
    assert svc2.progress()["totals"]["attempts"] == 1


def test_ui_ai_lesson_seam(qtbot) -> None:
    page = TeacherPage(teacher_service=TeacherService(engine=None))
    qtbot.addWidget(page)
    page.show()
    page.set_ai_lesson({"topic": "Vocabulary", "level": "Beginner", "prompt": "Q?", "answer": "a", "explanation": "e", "source": "ai"})
    assert page._lesson_area.isVisible()
    assert "Q?" in page._lesson_text.toPlainText()
    page._input.setText("a")
    page._submit_answer()
    assert "Correct" in page._feedback.text()
    assert "Progress:" in page._progress_label.text()

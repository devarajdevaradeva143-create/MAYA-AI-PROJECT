"""W3: teacher page lessons + answer feedback (no crashes)."""

from __future__ import annotations

import pytest

from app.ui.pages.teacher_page import LESSONS, TeacherPage


@pytest.fixture
def page(qtbot):
    p = TeacherPage()
    qtbot.addWidget(p)
    p.show()
    return p


def test_lesson_select_shows_prompt(page: TeacherPage) -> None:
    for name in LESSONS:
        page._lesson_selected(name)
        assert page._lesson_area.isVisible()
        assert name in page._lesson_label.text()
        assert LESSONS[name]["prompt"] in page._lesson_text.toPlainText()


def test_correct_answer_feedback(page: TeacherPage) -> None:
    page._lesson_selected("Vocabulary")
    page._input.setText("B")
    page._submit_answer()
    assert "Correct" in page._feedback.text()
    assert page._input.text() == ""


def test_wrong_answer_feedback(page: TeacherPage) -> None:
    page._lesson_selected("Idioms")
    page._input.setText("A")
    page._submit_answer()
    assert "Not quite" in page._feedback.text()


def test_empty_answer(page: TeacherPage) -> None:
    page._lesson_selected("Grammar")
    page._submit_answer()
    assert "Type an answer" in page._feedback.text()


def test_back_to_grid(page: TeacherPage) -> None:
    page._lesson_selected("Vocabulary")
    assert page._lesson_area.isVisible()
    page._back_to_grid()
    assert not page._lesson_area.isVisible()
    assert page._grid.isEnabled()


def test_pronunciation_no_autocheck(page: TeacherPage) -> None:
    page._lesson_selected("Pronunciation")
    page._input.setText("anything")
    page._submit_answer()
    assert "ℹ" in page._feedback.text() or page._feedback.text() != ""

"""Model manager guards against selecting or deleting unusable defaults."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from app.settings_repository import SettingsRepository
from app.ui.widgets.model_manager import ModelManager


class FakeModelService:
    def __init__(self) -> None:
        self.models = [
            {"id": "installed-model", "downloaded": True},
            {"id": "missing-model", "downloaded": False},
        ]
        self.deleted: list[str] = []

    def catalog(self) -> list[dict[str, Any]]:
        return self.models

    def installed(self) -> list[dict[str, Any]]:
        return [model for model in self.models if model["downloaded"]]

    def delete(self, model_id: str) -> dict[str, Any]:
        self.deleted.append(model_id)
        return {"status": "ok"}


def _make_manager(qtbot, tmp_path):
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("engine:\n  model: installed-model\n", encoding="utf-8")
    repository = SettingsRepository(settings_path, tmp_path / "backups")
    service = FakeModelService()
    manager = ModelManager(repository, model_service=service)
    qtbot.addWidget(manager)
    qtbot.waitUntil(lambda: manager._table.rowCount() == 2)
    return manager, repository, service


def test_uninstalled_model_cannot_be_set_as_default(qtbot, tmp_path, monkeypatch) -> None:
    manager, repository, _service = _make_manager(qtbot, tmp_path)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    manager._table.selectRow(1)
    assert not manager._set_default_btn.isEnabled()
    manager._on_set_default()

    assert repository.get("engine.model") == "installed-model"
    assert warnings


def test_active_default_model_cannot_be_deleted(qtbot, tmp_path, monkeypatch) -> None:
    manager, _repository, service = _make_manager(qtbot, tmp_path)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    manager._table.selectRow(0)
    manager._on_delete()

    assert service.deleted == []
    assert warnings

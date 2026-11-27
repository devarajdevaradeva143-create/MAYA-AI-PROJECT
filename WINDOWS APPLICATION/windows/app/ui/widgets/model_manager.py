"""Model Manager widget for Settings → AI Engine.

Displays model catalog with download/delete/set-default actions.
"""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.model_service import ModelService
from app.settings_repository import SettingsRepository


class _PopulateTableEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, catalog: list[dict[str, Any]], installed_ids: set[str]) -> None:
        super().__init__(self.EVENT_TYPE)
        self.catalog = catalog
        self.installed_ids = installed_ids


class _RefreshEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self) -> None:
        super().__init__(self.EVENT_TYPE)


class _ErrorEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, message: str) -> None:
        super().__init__(self.EVENT_TYPE)
        self.message = message


def _post(widget: QWidget, event: QEvent) -> None:
    """Post a custom event to the widget when a Qt app is running."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.postEvent(widget, event)


class ModelManager(QWidget):
    """Model management UI: list, download, delete, set as default."""

    # Emitted when the default model changes
    model_changed = Signal(str)

    def __init__(
        self,
        repository: SettingsRepository,
        model_service: ModelService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._model_service = model_service or ModelService()
        self._worker: DownloadWorker | None = None
        self._refresh_worker: threading.Thread | None = None
        self._all_models: list[dict[str, Any]] = []
        self._installed_ids: set[str] = set()
        self._deleted = False

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_label = QLabel("Search:")
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter models...")
        self._search_input.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_label)
        toolbar.addWidget(self._search_input, 1)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "Downloaded", "Not Downloaded"])
        self._filter_combo.currentTextChanged.connect(self._on_filter)
        toolbar.addWidget(self._filter_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Status", "Name", "Recipe", "Size", "Labels"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 80)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setObjectName("emptyHint")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)

        self._download_btn = QPushButton("Download")
        self._download_btn.setFixedHeight(32)
        self._download_btn.clicked.connect(self._on_download)
        actions.addWidget(self._download_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedHeight(32)
        self._delete_btn.clicked.connect(self._on_delete)
        actions.addWidget(self._delete_btn)

        self._set_default_btn = QPushButton("Set as default")
        self._set_default_btn.setFixedHeight(32)
        self._set_default_btn.clicked.connect(self._on_set_default)
        actions.addWidget(self._set_default_btn)

        layout.addLayout(actions)

        # Connect selection change
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._on_selection_changed()

    def refresh(self) -> None:
        """Reload model catalog from engine."""
        if self._deleted:
            return
        if self._refresh_worker and self._refresh_worker.is_alive():
            return

        def worker() -> None:
            try:
                catalog = self._model_service.catalog()
                installed_ids = {m.get("id") for m in self._model_service.installed()}
                if not self._deleted:
                    _post(self, _PopulateTableEvent(catalog, installed_ids))
            except Exception as exc:  # noqa: BLE001
                if not self._deleted:
                    _post(self, _ErrorEvent(str(exc)))

        self._refresh_worker = threading.Thread(target=worker, daemon=True)
        self._refresh_worker.start()

    def customEvent(self, event: QEvent) -> None:
        if self._deleted:
            return
        if isinstance(event, _PopulateTableEvent):
            self._do_populate_table(event.catalog, event.installed_ids)
        elif isinstance(event, _RefreshEvent):
            self.refresh()
        elif isinstance(event, _ErrorEvent):
            self._show_error(event.message)
        else:
            super().customEvent(event)

    def _do_populate_table(self, catalog: list[dict[str, Any]], installed_ids: set[str]) -> None:
        if self._deleted:
            return
        self._table.setRowCount(0)
        self._all_models = catalog
        self._installed_ids = installed_ids
        for model in catalog:
            self._add_model_row(model, model.get("id", "") in installed_ids)
        self._apply_filter()

    def _add_model_row(self, model: dict[str, Any], downloaded: bool) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Status
        status_item = QTableWidgetItem("✅" if downloaded else "⬇️")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 0, status_item)

        # Name
        name_item = QTableWidgetItem(model.get("id", ""))
        name_item.setData(Qt.ItemDataRole.UserRole, model.get("id", ""))
        self._table.setItem(row, 1, name_item)

        # Recipe
        recipe = model.get("recipe", "")
        recipe_item = QTableWidgetItem(recipe)
        recipe_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 2, recipe_item)

        # Size — Lemonade reports this in GB (e.g. 1.87). Older servers sent bytes,
        # so a value far above any real model size is treated as bytes.
        try:
            size_gb = float(model.get("size") or 0)
        except (TypeError, ValueError):
            size_gb = 0.0
        if size_gb > 1024:
            size_gb /= 1024**3
        size_str = f"{size_gb:.2f} GB" if size_gb else "—"
        size_item = QTableWidgetItem(size_str)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 3, size_item)

        # Labels
        labels = model.get("labels", [])
        labels_str = ", ".join(labels) if labels else "—"
        labels_item = QTableWidgetItem(labels_str)
        self._table.setItem(row, 4, labels_item)

    def _apply_filter(self) -> None:
        if self._deleted:
            return
        filter_text = self._search_input.text().lower()
        filter_mode = self._filter_combo.currentText()

        for row in range(self._table.rowCount()):
            model_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            model = next((m for m in self._all_models if m.get("id") == model_id), None)
            if not model:
                continue

            name = model.get("id", "").lower()
            downloaded = model_id in self._installed_ids

            matches_search = filter_text in name
            matches_filter = True
            if filter_mode == "Downloaded":
                matches_filter = downloaded
            elif filter_mode == "Not Downloaded":
                matches_filter = not downloaded

            show = matches_search and matches_filter
            self._table.setRowHidden(row, not show)

    def _on_search(self) -> None:
        self._apply_filter()

    def _on_filter(self) -> None:
        self._apply_filter()

    def _on_selection_changed(self) -> None:
        if self._deleted:
            return
        row = self._table.currentRow()
        has_selection = row >= 0

        if has_selection:
            model_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            downloaded = model_id in self._installed_ids
            self._download_btn.setEnabled(not downloaded)
            self._download_btn.setText("Download" if not downloaded else "Downloaded")
            self._delete_btn.setEnabled(downloaded)
            self._set_default_btn.setEnabled(downloaded)
        else:
            self._download_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            self._set_default_btn.setEnabled(False)

    def _is_chat_model(self, model_id: str) -> bool:
        """False for embeddings-only models: the engine rejects them for chat."""
        model = next((m for m in self._all_models if m.get("id") == model_id), None)
        if model is None:
            return True
        labels = [str(label).lower() for label in (model.get("labels") or [])]
        if not labels:
            return True
        return "embeddings" not in labels

    def _on_download(self) -> None:
        if self._deleted:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        model_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if model_id in self._installed_ids:
            return

        self._download_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setVisible(True)
        self._progress_label.setText(f"Downloading {model_id}...")

        self._worker = DownloadWorker(self._model_service, model_id, self)
        self._worker.progress.connect(self._on_download_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.start()

    def _on_download_progress(self, chunk: dict[str, Any]) -> None:
        if self._deleted:
            return
        status = chunk.get("status", "")
        if status == "downloading":
            msg = chunk.get("message", "")
            self._progress_label.setText(msg)
            self._progress_bar.setRange(0, 0)
        elif status == "completed":
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(100)
        elif status == "error":
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(0)
        elif status == "cancelled":
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(0)

    def _on_download_finished(self, progress: list[dict[str, Any]]) -> None:
        if self._deleted:
            return
        self._worker = None
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)
        self._download_btn.setEnabled(True)

        completed = any(c.get("status") == "completed" for c in progress)
        if completed:
            self.refresh()
        else:
            error_msg = next(
                (c.get("message", "Unknown error") for c in progress if c.get("status") == "error"),
                "Download failed",
            )
            QMessageBox.warning(self, "Download Failed", error_msg)

    def _on_delete(self) -> None:
        if self._deleted:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        model_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        active_model = str(self._repository.get("engine.model", "") or "")
        if model_id == active_model:
            QMessageBox.warning(
                self,
                "Cannot Delete Default Model",
                "Choose another default model before deleting this one.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Delete Model",
            f"Delete model '{model_id}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def worker() -> None:
            try:
                self._model_service.delete(model_id)
                if not self._deleted:
                    _post(self, _RefreshEvent())
            except Exception as exc:  # noqa: BLE001
                if not self._deleted:
                    _post(self, _ErrorEvent(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_set_default(self) -> None:
        if self._deleted:
            return
        row = self._table.currentRow()
        if row < 0:
            return
        model_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if model_id not in self._installed_ids:
            QMessageBox.warning(
                self,
                "Model Not Downloaded",
                "Download this model before setting it as the default.",
            )
            return
        if not self._is_chat_model(model_id):
            QMessageBox.warning(
                self,
                "Not a Chat Model",
                f"'{model_id}' is an embedding model, so chat cannot use it. "
                "Pick a model labelled 'chat' (for example Qwen3.5-2B-GGUF).",
            )
            return
        try:
            self._repository.update({"engine.model": model_id})
            self.model_changed.emit(model_id)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Error", f"Failed to set default model: {exc}")

    def _show_error(self, message: str) -> None:
        if self._deleted:
            return
        self._progress_label.setVisible(True)
        self._progress_label.setText(message)

    def shutdown(self) -> None:
        self._deleted = True
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        if self._refresh_worker and self._refresh_worker.is_alive():
            self._refresh_worker.join(timeout=1.0)


class DownloadWorker(QThread):
    """Worker for model downloads."""

    progress = Signal(dict)
    finished = Signal(list)

    def __init__(self, service: ModelService, model_id: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._service = service
        self._model_id = model_id
        self._cancelled = False

    def run(self) -> None:
        chunks: list[dict[str, Any]] = []
        for chunk in self._service.pull(self._model_id):
            chunks.append(chunk)
            if self._cancelled:
                break
            self.progress.emit(chunk)
        self.finished.emit(chunks)

    def cancel(self) -> None:
        self._cancelled = True
        self._service.cancel()
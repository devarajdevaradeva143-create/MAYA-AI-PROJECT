"""In-app voiceprint enrollment wizard."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _CaptureWorker(QThread):
    finished = Signal(object)

    def __init__(self, security: Any, seconds: int, parent: Any = None) -> None:
        super().__init__(parent)
        self._security = security
        self._seconds = seconds

    def run(self) -> None:
        try:
            result = self._security.voice_capture_sample(self._seconds)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        self.finished.emit(result)


class VoiceprintWizard(QDialog):
    def __init__(self, security: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._security = security
        self._samples_needed = 3
        try:
            from custom.tools import biometrics as _b

            self._samples_needed = int(_b.default_samples())
        except Exception:  # noqa: BLE001
            pass
        self._transcripts: list[str] = []
        self._vectors: list[Any] = []
        self._worker: _CaptureWorker | None = None
        self._generation = 0

        self.setWindowTitle("Enroll voiceprint")
        self.setModal(True)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Voiceprint enrollment is stored locally only. "
            "Your PIN remains the fallback. Speak the same phrase each time."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._phrase = QLineEdit("maya open the door")
        self._phrase.setPlaceholderText("Enrollment phrase (2-14 words)")
        layout.addWidget(QLabel("Phrase:"))
        layout.addWidget(self._phrase)

        self._status = QLabel("Ready.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, self._samples_needed)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        row = QHBoxLayout()
        self._record_btn = QPushButton("Record sample")
        self._record_btn.clicked.connect(self._record)
        row.addWidget(self._record_btn)
        self._finish_btn = QPushButton("Finish enrollment")
        self._finish_btn.setEnabled(False)
        self._finish_btn.clicked.connect(self._finish)
        row.addWidget(self._finish_btn)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_ready()

    def _refresh_ready(self) -> None:
        ready = self._security.voice_enroll_ready()
        if not isinstance(ready, dict):
            ready = {"ready": False, "reasons": ["unknown"]}
        if not ready.get("ready", False):
            self._record_btn.setEnabled(False)
            reasons = ready.get("reasons") or []
            self._status.setText("Not ready: " + "; ".join(str(r) for r in reasons))
        else:
            self._record_btn.setEnabled(True)

    def _record(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        ready = self._security.voice_enroll_ready()
        if not (isinstance(ready, dict) and ready.get("ready")):
            self._refresh_ready()
            return
        self._generation += 1
        gen = self._generation
        self._record_btn.setEnabled(False)
        self._status.setText("Recording… 5s")
        worker = _CaptureWorker(self._security, 5, self)
        worker.finished.connect(lambda res, g=gen: self._on_captured(res, g))
        self._worker = worker
        worker.start()

    def _on_captured(self, result: Any, generation: int) -> None:
        if generation != self._generation:
            return
        self._worker = None
        self._record_btn.setEnabled(True)
        if not isinstance(result, dict) or not result.get("ok"):
            err = result.get("error") if isinstance(result, dict) else "capture failed"
            self._status.setText(f"Capture failed: {err}")
            return
        text = str(result.get("text", "")).strip()
        vector = result.get("vector")
        phrase = self._phrase.text().strip()
        from custom.tools.biometrics import normalize_phrase, phrase_problem

        norm = normalize_phrase(phrase)
        problem = phrase_problem(norm)
        if problem:
            self._status.setText(problem)
            return
        # accept sample regardless of transcript mismatch? Enforce phrase match lightly.
        if normalize_phrase(text) != norm and text:
            self._status.setText(f"Heard '{text}'. Please repeat the same phrase.")
            # still count? We'll not count mismatched samples.
            return
        self._transcripts.append(text if text else phrase)
        self._vectors.append(vector)
        self._progress.setValue(len(self._transcripts))
        self._status.setText(f"Sample {len(self._transcripts)}/{self._samples_needed} recorded: {text}")
        if len(self._transcripts) >= self._samples_needed:
            self._finish_btn.setEnabled(True)

    def _finish(self) -> None:
        if len(self._transcripts) < self._samples_needed:
            return
        self._finish_btn.setEnabled(False)
        self._status.setText("Enrolling…")
        res = self._security.voice_enroll(self._transcripts, self._vectors)
        if isinstance(res, dict) and res.get("ok"):
            self._status.setText("Enrollment successful.")
            self.accept()
        else:
            err = res.get("error") if isinstance(res, dict) else str(res)
            self._status.setText(f"Enrollment failed: {err}")
            # clear samples on mismatch
            msg = str(err).lower()
            if "match" in msg or "mismatch" in msg:
                self._transcripts.clear()
                self._vectors.clear()
                self._progress.setValue(0)
                self._finish_btn.setEnabled(False)
                self._status.setText("Samples did not match. Please repeat the same phrase.")
            else:
                self._finish_btn.setEnabled(True)

    def closeEvent(self, event) -> None:  # noqa: N802
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(2000)
        super().closeEvent(event)

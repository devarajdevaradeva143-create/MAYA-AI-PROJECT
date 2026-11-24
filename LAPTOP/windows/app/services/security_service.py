"""Thin adapter over JARVIS/custom SecurityManager (PBKDF2 PIN store).

Never stores a PIN in settings.yaml. PIN lives in the security store
(MAYA AI/memory/offline/security.json) hashed with PBKDF2-SHA256 + salt.
"""

from __future__ import annotations

from typing import Any

try:
    from custom.tools.security import SecurityManager
except Exception:  # pragma: no cover - defensive
    SecurityManager = None  # type: ignore[assignment,misc]

try:
    from custom.tools import biometrics as _biometrics
except Exception:  # pragma: no cover
    _biometrics = None  # type: ignore[assignment]


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - UI must not crash
        return {"error": str(exc), "ok": False}


class SecurityService:
    """UI-facing wrapper. Keeps the manager injectable for tests."""

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager if manager is not None else (
            SecurityManager() if SecurityManager is not None else None
        )

    # -- PIN -----------------------------------------------------------
    def pin_is_set(self) -> bool:
        if self._manager is None:
            return False
        return bool(self._manager.is_locked())

    def session_locked(self) -> bool:
        if self._manager is None:
            return False
        return bool(self._manager.is_session_locked())

    def set_pin(self, pin: str, old_pin: str | None = None) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.set_pin(pin, old_pin))

    def verify_pin(self, pin: str) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.verify_pin(pin))

    def lock(self) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.lock())

    def unlock(self, method: str = "pin") -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.unlock(method))

    def status(self) -> dict[str, Any]:
        if self._manager is None:
            return {}
        try:
            return self._manager.status()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def alerts(self) -> list[dict[str, Any]]:
        if self._manager is None:
            return []
        try:
            return list(self._manager.get_unauthorized_alerts() or [])
        except Exception:  # noqa: BLE001
            return []

    # -- biometrics (fail-soft) ---------------------------------------
    def face_available(self) -> bool:
        st = self.face_status()
        return bool(st.get("available")) if isinstance(st, dict) else False

    def face_status(self) -> dict[str, Any]:
        if _biometrics is None:
            return {}
        res = _safe_call(_biometrics.face_status)
        return res if isinstance(res, dict) else {}

    def face_verify(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.face_verify)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

    def open_face_settings(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.open_face_settings)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

    def voice_status(self) -> dict[str, Any]:
        if _biometrics is None:
            return {}
        res = _safe_call(_biometrics.voice_status)
        return res if isinstance(res, dict) else {}

    def voice_reset(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.voice_reset)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

    # -- voiceprint enrollment ----------------------------------------
    def voice_enroll_ready(self) -> dict[str, Any]:
        reasons: list[str] = []
        speaker_model = False
        mic = False
        try:
            if _biometrics is None:
                reasons.append("biometrics module unavailable")
            else:
                speaker_model = bool(_biometrics.speaker_available())
                if not speaker_model:
                    reasons.append("speaker model missing (vosk-spk)")
        except Exception as exc:  # noqa: BLE001
            reasons.append(str(exc))
        try:
            import sys

            if sys.platform != "win32":
                reasons.append("microphone capture is Windows-only")
            else:
                from custom.tools import voice_stt

                st = voice_stt.status()
                mic = bool(st.get("windows_mic")) and bool(st.get("vosk_installed"))
                if not mic:
                    reasons.append("microphone or Vosk model unavailable")
        except Exception as exc:  # noqa: BLE001
            reasons.append(str(exc))
        return {"ready": not reasons, "speaker_model": speaker_model, "mic": mic, "reasons": reasons}

    def voice_capture_sample(self, seconds: int = 5) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        try:
            from custom.tools import voice_stt

            wav, _peak = voice_stt.record(seconds=seconds)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Could not record audio: {exc}"}
        try:
            text = _biometrics.transcribe_wav(wav)
            vector = _biometrics.speaker_vector(wav)
            return {"ok": True, "text": text, "vector": vector, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Could not process sample: {exc}"}
        finally:
            try:
                from pathlib import Path

                Path(wav).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

    def voice_enroll(self, transcripts: list[str], vectors: list[list[float]]) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.voice_enroll, transcripts, vectors)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

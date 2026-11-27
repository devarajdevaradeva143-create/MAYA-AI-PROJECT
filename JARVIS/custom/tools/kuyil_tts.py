"""Kuyil TTS adapter — tiny offline Tamil/Tanglish voice.

Model: https://huggingface.co/zhagaramlabs/kuyil-20m (CC BY 4.0, Zhagaram
Labs / IndicTTS IIT Madras). Inference code is vendored under
``custom/vendor/kuyil`` (Apache-2.0).

Why this exists: Piper Tamil voices read English words with Tamil phonemes,
so Tanglish comes out wrong. Kuyil's frontend sends Latin-script words
through CMUdict and reads them with an Indian accent, which makes mixed
Tamil/English sentences usable.

Everything stays on disk — no network calls at runtime.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..config import PROJECT_ROOT, load_settings

_REQUIRED_MODULES = ("torch", "onnxruntime", "safetensors", "cmudict", "uraikal")


def _patch_cmudict_metadata() -> None:
    """Frozen builds (PyInstaller) bundle cmudict without its dist-info."""
    try:
        import cmudict  # noqa: F401
        return
    except Exception as exc:  # noqa: BLE001 - only the metadata case is recoverable
        if "cmudict" not in str(exc).lower() and "package metadata" not in str(exc).lower():
            return
    import sys

    if "cmudict" in sys.modules:
        del sys.modules["cmudict"]
    try:
        import importlib.metadata as _md

        _original = _md.version

        def _patched(name: str) -> str:
            if name == "cmudict":
                return "1.1.3"
            return _original(name)

        _md.version = _patched
    except Exception:  # pragma: no cover - defensive
        pass


_patch_cmudict_metadata()


def _module_available(name: str) -> bool:
    if importlib.util.find_spec(name) is None:
        return False
    try:
        if name == "cmudict":
            _patch_cmudict_metadata()
            import cmudict  # noqa: F401
        else:
            importlib.import_module(name)
    except Exception:  # noqa: BLE001 - treat an unusable module as missing
        return False
    return True


def _missing_modules() -> list[str]:
    return [name for name in _REQUIRED_MODULES if not _module_available(name)]


HAS_KUYIL = not _missing_modules()
IMPORT_ERROR = "" if HAS_KUYIL else "missing " + ", ".join(_missing_modules())



DEFAULT_MODEL_DIR = "MAYA AI/Model/models/kuyil-20m"
DEFAULT_VOICE = "female"
SAMPLE_RATE = 16000

# Loaded voices are ~90 MB; keep one per model directory.
_CACHE: dict[str, tuple[Any, list[str], list[str]]] = {}
_CACHE_LOCK = threading.Lock()


def _kuyil_cfg() -> dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash voice
        return {}
    voice = settings.get("voice") if isinstance(settings, dict) else None
    tts = voice.get("tts") if isinstance(voice, dict) else None
    cfg = tts.get("kuyil") if isinstance(tts, dict) else None
    return cfg if isinstance(cfg, dict) else {}


def _resolve(value: Any, default: str) -> Path:
    raw = str(value or default)
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def split_text(text: str, limit: int = 180) -> list[str]:
    """Split long text on sentence boundaries (tiny model degrades past ~20 s)."""
    text = " ".join((text or "").split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?।])\s+", text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            chunks.append(part)
    return chunks


class KuyilTTS:
    """Offline Tamil/Tanglish TTS with a female or male voice."""

    def __init__(
        self,
        lang: str = "tamil",
        model_dir: Optional[str | Path] = None,
        voice: Optional[str] = None,
        lazy: bool = True,
    ) -> None:
        self.lang = (lang or "tamil").lower().strip()
        cfg = _kuyil_cfg()
        self.model_dir = (
            Path(model_dir) if model_dir is not None else _resolve(cfg.get("model"), DEFAULT_MODEL_DIR)
        )
        self.voice = str(voice or cfg.get("voice") or DEFAULT_VOICE).lower().strip()
        self._speak = None
        self._symbols: list[str] = []
        self._voices: list[str] = []
        self._load_error = ""
        if not lazy:
            self._ensure_loaded()

    # -- state --------------------------------------------------------

    def is_available(self) -> bool:
        return HAS_KUYIL and self.model_dir.is_dir()

    def is_loaded(self) -> bool:
        return self._speak is not None

    @property
    def voices(self) -> list[str]:
        return list(self._voices) or [DEFAULT_VOICE, "male"]

    @property
    def model_path(self) -> Optional[Path]:
        return self.model_dir if self.model_dir.is_dir() else None

    def _ensure_loaded(self) -> bool:
        if self._speak is not None:
            return True
        if not HAS_KUYIL:
            self._load_error = f"Kuyil deps missing: {IMPORT_ERROR}"
            return False
        if not self.model_dir.is_dir():
            self._load_error = f"Kuyil model not found: {self.model_dir}"
            return False

        key = str(self.model_dir)
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached is None:
                try:
                    cached = self._load(self.model_dir)
                except Exception as exc:  # pragma: no cover - corrupt model
                    self._load_error = f"Kuyil load failed: {exc}"
                    return False
                _CACHE[key] = cached
        self._speak, self._symbols, self._voices = cached
        if self.voice not in self._voices:
            self.voice = self._voices[0] if self._voices else DEFAULT_VOICE
        return True

    @staticmethod
    def _load(model_dir: Path) -> tuple[Any, list[str], list[str]]:
        import json

        import onnxruntime as ort
        import torch
        from safetensors.torch import load_file

        from ..vendor.kuyil.frontend import phonemize
        from ..vendor.kuyil.model import Config, Kuyil
        from ..vendor.kuyil.resynth import vocode

        torch.set_num_threads(1)  # keep the UI responsive
        ck = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        state = load_file(str(model_dir / "model.safetensors"))
        model = Kuyil(Config(**ck["config"]))
        model.load_state_dict(state)
        model.eval()

        pivo = model_dir / "pivo"
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        cond_net = ort.InferenceSession(
            str(pivo / "onnx" / "conditioning.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        step = ort.InferenceSession(
            str(pivo / "onnx" / "vocoder_step.onnx"), opts, providers=["CPUExecutionProvider"]
        )

        def speak(text: str, voice: str) -> "np.ndarray":
            ids = torch.tensor(
                [ck["symbols"].index(p) for p in ["<bos>"] + phonemize(text) + ["<eos>"]]
            )
            audio = model.synthesize(ids, ck["voices"].index(voice)).numpy()
            return np.clip(vocode(audio, cond_net, step), -1, 1)

        return speak, list(ck["symbols"]), list(ck["voices"])

    # -- synthesis ----------------------------------------------------

    def synthesize_array(self, text: str) -> "np.ndarray":
        """Return 16 kHz float32 audio for ``text`` (raises on failure)."""
        if not self._ensure_loaded():
            raise RuntimeError(self._load_error or "Kuyil is not available")
        pieces = split_text(text)
        if not pieces:
            raise RuntimeError("Nothing to say")
        gap = np.zeros(int(SAMPLE_RATE * 0.12), dtype=np.float32)
        out: list[np.ndarray] = []
        for piece in pieces:
            audio = np.asarray(self._speak(piece, self.voice), dtype=np.float32)
            if out:
                out.append(gap)
            out.append(audio)
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def synthesize_wav(self, text: str, target_path: str | Path) -> str:
        """Synthesize ``text`` to a WAV file. Returns "" on success, else a message."""
        if not self.is_available():
            if not HAS_KUYIL:
                return f"[TTS] Kuyil deps missing: {IMPORT_ERROR}"
            return f"[TTS] Kuyil model not found in {self.model_dir}"
        target = Path(target_path)
        try:
            audio = self.synthesize_array(text)
            if audio.size == 0:
                return "[TTS] Kuyil produced no audio."
            pcm = np.clip(audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype("<i2")
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(target), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(pcm.tobytes())
            if target.stat().st_size <= 44:
                return "[TTS] Kuyil produced an empty WAV."
            return ""
        except ValueError as exc:
            return f"[TTS] Kuyil cannot read some characters: {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            return f"[TTS] Kuyil error: {exc}"

    def speak(self, text: str) -> str:
        """Synthesize and play through the local speakers."""
        import os

        from .voice import _play_wav  # local import avoids a cycle

        if not text or not text.strip():
            return "[TTS] Nothing to say."
        fd, tmp_name = tempfile.mkstemp(prefix="maya_kuyil_", suffix=".wav")
        os.close(fd)
        try:
            err = self.synthesize_wav(text, tmp_name)
            if err:
                return err
            _play_wav(tmp_name)
            return f"[TTS] Spoke (Kuyil): {text[:60]}"
        finally:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass

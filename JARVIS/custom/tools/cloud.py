"""Gemini cloud client — the ONLY place Maya talks to the internet.

Rules this module enforces (AGENTS.md):
  * separate command only (``maya-cloud``) — never called from ``chat``
  * explicit confirmation before anything is sent
  * offline memory is never attached automatically
  * the API key is read from ``.env`` / environment, never logged
  * online history is stored separately in ``memory/online/``

No third-party SDK: plain ``httpx`` to the public REST endpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import PROJECT_ROOT, load_settings

ENV_KEY = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60


class CloudError(RuntimeError):
    """Raised for any cloud failure (no key, network, bad response)."""


# ── Configuration ──────────────────────────────────────────────────────────

def _cloud_cfg() -> dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash cloud
        settings = {}
    cfg = settings.get("cloud", {}) if isinstance(settings, dict) else {}
    return cfg if isinstance(cfg, dict) else {}


def enabled() -> bool:
    """True unless `cloud.enabled: false` is set in settings.yaml."""
    return _cloud_cfg().get("enabled") is not False


def _env_file_path() -> Path:
    override = os.environ.get("MAYA_ENV_FILE", "").strip()
    return Path(override).expanduser() if override else PROJECT_ROOT / ".env"


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Tiny ``.env`` reader — no dependency, never prints values."""
    env_path = path or _env_file_path()
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_key() -> str | None:
    """Resolve the Gemini key from the environment or the project ``.env``."""
    key = os.environ.get(ENV_KEY, "").strip()
    if key:
        return key
    return load_env_file().get(ENV_KEY) or None


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only permissions for the key file."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:R,W"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def save_api_key(key: str) -> dict[str, Any]:
    """Write/replace ``GEMINI_API_KEY`` in ``.env`` atomically.

    The value is never returned or logged. Other lines and comments survive.
    """
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "code": "empty", "error": "No key given."}
    if any(char.isspace() for char in key) or not (20 <= len(key) <= 200):
        return {
            "ok": False,
            "code": "bad_key",
            "error": "That does not look like an API key (20-200 characters, no spaces).",
        }

    path = _env_file_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except OSError as exc:
        return {"ok": False, "code": "read_failed", "error": f"Could not read {path}: {exc}"}

    output: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(ENV_KEY + "="):
            if not replaced:
                output.append(f"{ENV_KEY}={key}")
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(f"{ENV_KEY}={key}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("\n".join(output).rstrip("\n") + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            _restrict_permissions(Path(tmp_name))
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        return {"ok": False, "code": "write_failed", "error": f"Could not write {path}: {exc}"}

    _restrict_permissions(path)
    return {"ok": True, "path": str(path), "looks_google": key.startswith("AIza")}


def model_name() -> str:
    return str(_cloud_cfg().get("model") or DEFAULT_MODEL)


def endpoint() -> str:
    return str(_cloud_cfg().get("endpoint") or DEFAULT_ENDPOINT).rstrip("/")


def log_path() -> Path:
    """Online history lives apart from offline memory — never mixed."""
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash cloud
        settings = {}
    memory = settings.get("memory", {}) if isinstance(settings, dict) else {}
    online = str(memory.get("online") or "memory/online")
    path = Path(online)
    if not path.is_absolute():
        path = PROJECT_ROOT / "MAYA AI" / path
    return path / "cloud_log.jsonl"


def status() -> dict[str, Any]:
    """Honest cloud status — never returns the key itself."""
    key = api_key()
    return {
        "configured": bool(key),
        "key_preview": f"...{key[-4:]}" if key and len(key) > 4 else None,
        "model": model_name(),
        "endpoint": endpoint(),
        "env_file": str(_env_file_path()),
        "env_file_exists": _env_file_path().is_file(),
        "log_path": str(log_path()),
    }


# ── Request building ───────────────────────────────────────────────────────

def build_payload(prompt: str, system: str | None = None) -> dict[str, Any]:
    """Build the REST body. Kept separate so tests can inspect it."""
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(_cloud_cfg().get("temperature", 0.7)),
            "maxOutputTokens": int(_cloud_cfg().get("max_tokens", 1024)),
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload


def _extract_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        feedback = data.get("promptFeedback") or {}
        reason = feedback.get("blockReason") or "no candidates returned"
        raise CloudError(f"Gemini returned nothing ({reason})")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise CloudError("Gemini returned an empty reply")
    return text


def ask(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Send one prompt to Gemini and return the reply text.

    The caller is responsible for asking the user for permission first — this
    function just performs the request.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise CloudError("Empty prompt")

    key = api_key()
    if not key:
        raise CloudError(
            f"No {ENV_KEY} found. Add it to {_env_file_path()} "
            f"(one line: {ENV_KEY}=your-key) and try again."
        )

    cfg = _cloud_cfg()
    if cfg.get("enabled") is False:
        raise CloudError("Cloud is disabled in settings.yaml (cloud.enabled: false)")

    used_model = model or model_name()
    url = f"{endpoint()}/models/{used_model}:generateContent"
    timeout = float(cfg.get("timeout", DEFAULT_TIMEOUT))

    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.post(
            url,
            params={"key": key},
            json=build_payload(prompt, system),
            timeout=timeout,
        )
        if response.status_code == 400:
            raise CloudError(f"Gemini rejected the request: {_short(response)}")
        if response.status_code in (401, 403):
            raise CloudError(
                "Gemini key was rejected. Check GEMINI_API_KEY in .env."
            )
        if response.status_code == 429:
            raise CloudError("Gemini rate limit hit — wait a moment and retry.")
        response.raise_for_status()
        return _extract_text(response.json())
    except httpx.HTTPStatusError as exc:
        raise CloudError(f"Gemini HTTP {exc.response.status_code}: {_short(exc.response)}") from exc
    except httpx.HTTPError as exc:
        raise CloudError(f"Cannot reach Gemini: {exc.__class__.__name__}") from exc
    finally:
        if owns_client:
            http.close()


def _short(response: httpx.Response, limit: int = 200) -> str:
    try:
        data = response.json()
        return str(data.get("error", {}).get("message") or data)[:limit]
    except Exception:
        return response.text[:limit]


# ── Online log (separate from offline memory) ──────────────────────────────

def log_exchange(prompt: str, reply: str, model: str | None = None) -> Path | None:
    """Append one exchange to ``memory/online/cloud_log.jsonl``."""
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model or model_name(),
            "prompt": prompt,
            "reply": reply,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path
    except OSError:
        return None

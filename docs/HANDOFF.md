# HANDOFF PROMPT — Maya AI (copy everything below to another AI)

You are a senior Python engineer continuing **Maya AI**, a local-first personal
assistant for Windows (HP OmniBook 5, Ryzen AI 5 340). All 13 build phases are done; your job is the remaining work listed
at the bottom.

---

## 1. HARD RULES (never break)

1. `JARVIS/OpenJarvis/` is **read-only**. Never edit it. Before you finish,
   `git -C JARVIS/OpenJarvis status --porcelain` must print nothing.
2. All our code lives in `JARVIS/custom/`. Engine changes would go to
   `JARVIS/patches/*.patch` (none exist yet).
3. Config comes only from `MAYA AI/config/settings.yaml` — never hardcode
   paths, model names, or thresholds.
4. Privacy: offline memory never goes to the internet; `memory/offline` and
   `memory/online` are never mixed; biometrics stay local; `DEVARAJ/` personal
   details are never uploaded.
5. Destructive or important actions need explicit user permission.
6. Maya is command-only — it must not act on its own.

---

## 2. ENVIRONMENT (verified working)

- Project root: `C:\Users\devar\Desktop\MAYA AI PROJECT`
- App venv: `JARVIS/.venv` — **Python 3.13.18**
- Engine venv: `JARVIS/.venv-engine` (`jarvis.exe`, OpenJarvis pinned via
  `uv sync --frozen` — do not regenerate `uv.lock`)
- Inference: **AMD Lemonade Server** on `http://localhost:13305` (NPU, FLM
  models already cached). No model download is required.
- Default model `qwen3.5-2b-FLM`, fallback `qwen3-it-4b-FLM`. Also available:
  `qwen3-8b-FLM`, `gemma3-1b-FLM`, `gemma4-it-e2b-FLM`, `gemma4e-flash-e2b-FLM`.
- Endpoints: `GET /v1/models`, `GET /api/v1/health`,
  `POST /v1/chat/completions` (OpenAI-compatible).

> **Interpreter pitfall:** a bare `python` on this machine may resolve to
> **Python 3.14** (no httpx / project deps). Always use
> `JARVIS\.venv\Scripts\python.exe` or `uv run` from `JARVIS/`.

---

## 3. RUN AND VERIFY

```powershell
cd "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS"
$py = ".venv\Scripts\python.exe"

& $py -m custom.cli --help
& $py -m custom.cli chat                 # real LLM chat
& $py -m custom.cli monitor status
& $py -m custom.cli security status
& $py -m custom.cli biometrics status
& $py -m custom.cli security watchdog --help
& $py -m custom.cli voice status
& $py -m custom.cli knowledge rag-index "..\docs"
& $py -m custom.cli knowledge rag-search "session lock"
& $py -m custom.cli devices list

& $py -m pytest custom/tests -q          # must be 333 passed, 1 skipped
git -C OpenJarvis status --porcelain     # must be empty
```

Windows launcher: `MAYA AI\scripts\maya.ps1 <args>`

---

## 4. ARCHITECTURE (what already exists)

```
JARVIS/custom/
├─ cli.py             click CLI, all commands, LockedGroup guard
├─ cloud_cli.py       separate `maya-cloud` command, LockedCloudGroup guard
├─ config.py          settings.yaml loader (PROJECT_ROOT aware)
├─ engine/bridge.py   Lemonade HTTP + openjarvis subprocess modes,
│                     health/list_models/chat/chat_stream, strips  thinking
├─ persona/loader.py  girlfriend + english-teacher personas
├─ tools/
│  ├─ store.py        atomic local JSON store
│  ├─ assistant.py    todos, reminders, daily schedule, reminder scheduler
│  ├─ chat_history.py chat log → memory/offline only
│  ├─ knowledge.py    pdf/txt/md indexing + keyword content search
│  ├─ rag.py          chunking + BM25/semantic hybrid retrieval + grounded answers
│  ├─ embeddings.py   model2vec local embeddings (optional, BM25 fallback)
│  ├─ monitor.py      CPU/RAM/GPU/NPU/temp/battery/SSD + threshold alerts + loop
│  ├─ security.py     PIN (PBKDF2), lockout, backup code, session lock, alerts
│  ├─ watchdog.py     idle/session auto-lock + optional voice re-check
│  ├─ biometrics.py   Windows Hello face + Vosk phrase/voiceprint (local only)
│  ├─ voice.py        Piper TTS → Windows SAPI fallback, wake phrase
│  ├─ voice_stt.py    offline Vosk STT (file + microphone)
│  ├─ voice_clap.py   3-clap wake detection
│  ├─ cloud.py        Gemini REST client, key from .env, confirmation
│  ├─ devices.py      trusted pairing + HMAC-signed bundles; discovery/ADB/wifi
│  └─ language.py     language detection helpers (translations still stubs)
├─ plugins/           extension point (empty)
└─ tests/             333 tests
```

OS layer:
- `WINDOWS APPLICATION/windows/app/maya_tray.py` — tray app (needs `pystray` + `pillow`;
  falls back to terminal chat when missing)
- `WINDOWS APPLICATION/windows/app/install_autostart.ps1` — Task Scheduler autostart
- `MAYA AI/scripts/maya.ps1` — launcher (verified on Windows)

Docs: `docs/ROADMAP.md` (phase status), `docs/ENGINE-SETUP.md`,
`docs/KNOWLEDGE.md`, `docs/VOICE.md`, `docs/CLOUD.md`,
`docs/BIOMETRICS.md`, `docs/DEVICES.md`, `docs/HANDOFF.md` (this file).

---

## 5. DONE — DO NOT REDO

Phases 1–13: foundation/tests · OpenJarvis install + bridge · Lemonade NPU
model selection · real chat + persona + offline history · monitor/knowledge/
assistant hardening · PIN security · voice (English SAPI TTS, Vosk STT,
clap wake) · OS layer + docs · cloud (`maya-cloud`) · hybrid RAG · face +
voice biometrics + full session lock guard · trusted device pairing + signed
sync bundles · session watchdog (idle/session auto-lock + optional voice
re-check).

Verified (latest): **333 tests pass, 1 skipped**, real model reply through the
bridge, `maya chat` produces answers, PIN set/unlock/change flows correct,
voice STT/TTS and hybrid RAG tested end to end, biometrics live-tested (same
voice 1.000, different voice 0.228 rejected), locked CLI and `maya-cloud`
blocked, device pairing/bundle tamper tests green, watchdog live-tested
(auto-locked after idle and recorded an alert), `OpenJarvis` git clean.

Device security audit (0 Critical, 0 High, 5 Medium, 7 Low) completed; all
Medium findings are fixed: 128-bit generated / 16+ char human codes with
whitespace stripping, no code-derived public id in bundles, junction/symlink
containment, staged import with backup/rollback and duplicate/prefix path
pre-validation, and limits enforced before reads/decodes. Hardening also
covers Windows ADS/reserved names/control chars, KDF algorithm+iteration
validation, terminal-escape sanitising, owner-only store/bundle permissions,
corrupt-store preservation, sensitive-file deny-list and `--ask-code`.

---

## 6. PENDING WORK — DO IN THIS ORDER

1. **Tamil TTS** (user action needed)
   English TTS works via Windows SAPI. For Tamil: `uv pip install piper-tts`,
   then place a Tamil `.onnx` voice + config in `MAYA AI/voice/tamil/`.
   `tools/voice.py` already prefers Piper. Do not fake Tamil output.

2. **Tamil STT** (decision needed)
   Offline Vosk STT works for English / Indian English. Official Vosk has no
   Tamil model, so this needs a different recogniser (e.g. Whisper) — a larger
   change, not just a download.

3. **Windows tray** (done in WINDOWS APPLICATION/windows app)
   The PySide6 app (`WINDOWS APPLICATION/windows`) now has a real tray (`--tray`),
   close-to-tray / minimize-to-tray / start-minimized settings, and a
   packaged `dist\mayaai.exe` with a desktop shortcut (`Desktop\Maya AI.lnk`).
   `pystray` + `pillow` are dependencies of `WINDOWS APPLICATION/windows` (not the JARVIS
   venv). Packaged builds resolve `MAYA AI\` from the exe folder
   (`app/paths.py` + `custom/config.py` via `MAYA_AI_HOME`), never from the
   PyInstaller temp directory.

4. **Language Intelligence**
   `tools/language.py` translation functions are placeholders. Detect/phonetic
   helpers work; real Tamil↔English/Tanglish translation needs a model or a
   deliberate local implementation.

5. **Mobile app** — in progress (`MOBILE APP/`): Phases 0-12 implemented,
   debug + release APK built, Phase 9 on-device model (offline reply test)
   pending. See `MOBILE APP/PLAN.md` and `docs/PHASE9-ONDEVICE-MODEL.md`.

6. **Cleanup (ask the user first)**
   Legacy duplicates: `MAYA AI/scripts/maya-launch.ps1`, `maya-launch.sh`,
   `WINDOWS APPLICATION/windows/app/autostart.ps1`. Old embedding cache
   `MAYA AI/Model/hf/hub/models--minishlab--potion-base-8M` (~29 MB).
   Delete only with permission.

Optional: switch RAG embeddings to `minishlab/potion-multilingual-128M` for
better Tamil paraphrase quality (≈512 MB download) via
`knowledge.embedding_model`, then rebuild the index.

---

## 7. KNOWN ISSUES / PITFALLS

- Every Qwen FLM model is **weak in Tamil/Tanglish**. The 8B model is stronger
  but slow (~45 s) and emits ` thinking` blocks; the bridge strips them.
  Change `engine.model` in `settings.yaml`, never in code.
- PowerShell reports `Exit code: 1` for `uv`/`jarvis` even on success because
  they log warnings to stderr. Harmless.
- `openjarvis.security: Failed to set up rate limiter: No module named
  'openjarvis_rust'` is a harmless warning.
- Tests must isolate storage with temporary paths:
  `MAYA_ASSISTANT_STORE`, `MAYA_SECURITY_STORE`, `MAYA_BIOMETRICS_STORE`,
  `MAYA_CHAT_HISTORY`, `MAYA_KNOWLEDGE_INDEX`, `MAYA_RAG_INDEX`,
  `MAYA_DEVICES_STORE`, `MAYA_ENV_FILE`. Never let tests write into
  `MAYA AI/memory/offline/`.
- The real security store is currently absent (`security set-pin` has not been
  run), so the session lock/guard is inactive until the user sets a PIN.
- `security` is both a click group and the manager singleton in `cli.py`; it is
  imported as `security_manager`. Keep that alias.
- Lock guard: `LockedGroup` allows `security`, `biometrics`, `lock`, `version`
  plus all `--help`; `LockedCloudGroup` allows `status` / `--help`. Blocked
  commands exit 1 and do not create alerts.
- `cli.py` needs `if __name__ == "__main__": main()` at the end or
  `python -m custom.cli` prints nothing.
- Importing `custom.cli` eagerly in `custom/__init__.py` triggers a
  `RuntimeWarning`; the lazy `__getattr__` must stay.
- Device bundles are **signed, not encrypted**. Never describe them as
  encrypted, and never bundle `DEVARAJ/` for an untrusted destination.
- Bundles have **no anti-replay/nonce**: re-importing an old signed bundle with
  `--overwrite` restores old contents. Documented in `docs/DEVICES.md`; do not
  claim rollback protection.
- Pairing codes are long-lived shared secrets: never pass them on the command
  line in examples (shell history), and never log or print them after pairing.
- `security watchdog` is **command-only**; never add it to autostart without
  the user asking. Idle lock needs `GetLastInputInfo` (Windows); on Wayland it reports idle locking inactive.
- Voice re-check is periodic and **fail-closed** once enabled: no signal, a
  mismatch or a mic error locks the session. It is skipped (not failed) when
  no voice password is enrolled or the speaker model is missing.

---

## 8. HOW TO WORK

1. Read `AGENTS.md` and `JARVIS/AGENTS.md` before touching anything.
2. Small steps: one feature, then run pytest, then move on.
3. Never edit `OpenJarvis`; check its git status before you report done.
4. Say clearly what is implemented and what is still a stub — no invented
   capabilities.

**First action:** run the verification commands in section 3, report the
current state, then ask the user which pending item to start.

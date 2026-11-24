# MAYA INTELLIGENCE

**Offline intelligence orchestration layer for MAYA AI** — three engines (IQ/EQ/AQ), a 10-step pipeline, SQLite memory, and a warm `maya` persona. Built as a self-contained package that **reuses** the existing `JARVIS/custom/` engine and tools without modification.

## Architecture

```
MAYA INTELLIGENCE/
├─ maya_intelligence/
│  ├─ __init__.py
│  ├─ __main__.py          # python -m maya_intelligence
│  ├─ _bootstrap.py        # adds ../JARVIS to sys.path for `import custom`
│  ├─ config.py            # DB path, persona path, settings
│  ├─ cli.py               # click CLI: chat | memory | persona | status
│  ├─ orchestrator.py      # 10-step orchestration pipeline
│  ├─ adapters/            # thin wrappers over custom.*
│  │  ├─ engine.py         # wraps custom.engine.bridge.EngineBridge
│  │  ├─ pc.py             # wraps custom.tools.pc_control (+ create_folder)
│  │  ├─ assistant.py      # wraps custom.tools.assistant
│  │  ├─ knowledge.py      # wraps custom.tools.knowledge / rag
│  │  ├─ language.py       # wraps custom.tools.language
│  │  └─ voice.py          # wraps custom.tools.voice / voice_stt
│  ├─ engines/
│  │  ├─ iq.py             # Cognitive: answer/plan via engine + RAG
│  │  ├─ eq.py             # Emotional: tone detection + style directive
│  │  └─ aq.py             # Action: intent→tool, confirm, execute, verify
│  ├─ memory/
│  │  ├─ store.py          # SQLite store with FTS5, 4 categories
│  │  └─ schema.sql        # memories table + memories_fts
│  └─ persona/
│     └─ maya.md           # system prompt for maya persona
├─ tests/
│  ├─ conftest.py
│  ├─ test_memory.py
│  ├─ test_eq.py
│  ├─ test_iq.py
│  ├─ test_aq.py
│  └─ test_orchestrator.py
├─ run.ps1 / run.sh        # launchers using JARVIS/.venv python
└─ README.md               # this file
```

## Run Model (No Changes to JARVIS Packaging)

Run inside `JARVIS/.venv` with both roots on `PYTHONPATH`:

```powershell
# Windows PowerShell
.\run.ps1 chat
.\run.ps1 status
.\run.ps1 memory add --category personal --key "name" --value "User"
```

```bash
# Linux/macOS/Git Bash
./run.sh chat
./run.sh status
./run.sh memory add --category personal --key "name" --value "User"
```

Or manually:

```powershell
$env:PYTHONPATH = "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS;C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA INTELLIGENCE"
& "JARVIS\.venv\Scripts\python.exe" -m maya_intelligence chat
```

**Always use `JARVIS\.venv\Scripts\python.exe`** (a bare `python` may be 3.14; project requires 3.13, `pyproject.toml` has `requires-python >=3.10,<3.14`).

## Exception to "Code Only in `custom/`" Rule

This package **intentionally** lives outside `JARVIS/custom/` as a new top-level package `MAYA INTELLIGENCE/maya_intelligence/`. This was user-approved to:
- Keep the orchestration layer cleanly separated from the engine/tools
- Allow independent versioning and testing
- Avoid modifying `JARVIS/pyproject.toml` or any `custom/` file (keeps 333 tests intact)

`JARVIS/OpenJarvis/` remains untouched (`git -C JARVIS/OpenJarvis status --porcelain` empty).

## Key Design Decisions

| Spec Section | Implementation |
|---|---|
| **IQ** (§2) | `engines/iq.py` over `adapters/engine.py` + `adapters/knowledge.py` |
| **EQ** (§2) | `engines/eq.py` — prompt-level styling via tone heuristic + directive (no separate model) |
| **AQ** (§2) | `engines/aq.py` over `adapters/pc.py`, `assistant.py` (+ permission gate) |
| **Personality** (§3) | `persona/maya.md` as system prompt (college-age female: soft, sweet, kind, warm, caring, respectful — **not** romantic) |
| **Language** (§4) | `adapters/language.py` — detect → reply in same language (Tamil/English/Tanglish) |
| **Memory** (§5) | `memory/store.py` — SQLite, 4 categories, FTS5, secret-guard, `MAYA_INTEL_DB` override |
| **Windows Control** (§6) | `adapters/pc.py` + `path_guard`/`control_guard` — confirm destructive ops |
| **Orchestration** (§7) | `orchestrator.py` — 10 steps with fast-path heuristics |
| **Offline** (§8) | All local; honest error if engine down |
| **Voice** (§9) | `adapters/voice.py` — Tamil TTS/STT pending, report honestly |
| **Safety** (§10) | Confirm destructive; verify before claiming success |

## Memory

- **DB default:** `<PROJECT_ROOT>/MAYA AI/memory/offline/maya_intelligence.db` (offline-only, never online/cloud)
- **Override:** `MAYA_INTEL_DB` environment variable
- **Categories:** `personal`, `conversation`, `project`, `knowledge`
- **Schema:** `memories(id, category, key, value, sensitivity, created_at, updated_at)` + `memories_fts` (FTS5)
- **Privacy:** Gitignored, no secrets stored, ask before sensitive, `security.is_session_locked()` gates CLI

## Tamil / Tanglish Support

- **Detection & translation:** via `custom.tools.language` (English-first, Tamil best-effort)
- **Local FLM/Qwen weakness:** Known limitation (see `JARVIS/docs/HANDOFF.md`) — never fake fluency
- **Tamil TTS/STT:** Pending (needs Whisper + Tamil `.onnx`) — voice replies English-only for now

## Safety & Verification

- **Permission gate:** `pc_control.set_permission_gate(confirm_fn)` wired at startup (blocks headless `input()` hang)
- **Destructive ops** (delete, edit, create_folder, run_command, close_app): require confirmation
- **Verification:** Every action verified independently (e.g., `is_app_running` after open/close, `os.path.exists` after file ops)
- **Engine errors:** Returned as strings starting with `"[engine error] "` — never saved as assistant text

## Testing

```powershell
$env:PYTHONPATH = "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS;C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA INTELLIGENCE"
$py = "JARVIS\.venv\Scripts\python.exe"
& $py -m pytest "MAYA INTELLIGENCE\tests" -q          # new tests green
& $py -m pytest custom/tests -q                      # still 333 passed, 1 skipped
git -C JARVIS/OpenJarvis status --porcelain           # empty
```

## Smoke Tests

- `maya-intel status` → engine health ok, memory stats
- `maya-intel chat` → real local reply in `maya` persona
- `maya-intel memory add/list/search/delete` → persists in SQLite
- "open notepad" → confirm prompt → verified via `is_app_running`
- EQ: sad/tired input → supportive style; no fake emotion
- Tamil/Tanglish input → best-effort same-language reply; honest if weak

## Out of Scope

- Replacing `maya` / `maya-cloud` CLIs or the 13 phases
- Editing `JARVIS/custom/`
- Mobile app, Fedora specifics, Gemini/cloud
- Strong Tamil ASR/TTS (needs Whisper + Tamil `.onnx`)
- GUI changes; editable-install packaging
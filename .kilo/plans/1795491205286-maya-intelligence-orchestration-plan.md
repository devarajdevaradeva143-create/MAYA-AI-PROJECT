# MAYA INTELLIGENCE — Implementation Plan

> Goal: Add a fully-offline **intelligence orchestration layer** (3 engines IQ/EQ/AQ + 10-step pipeline), a new `maya` personality, and **SQLite memory** — as a new self-contained package in `MAYA INTELLIGENCE/`, reusing the existing `JARVIS/custom/` engine + tools (no rewrite).

## 1. Context (verified against the real code)

`JARVIS/custom/` (package `maya-custom`, runs in `JARVIS/.venv`, **Python 3.13**) already provides everything the engines need:
- **Engine:** `engine/bridge.py` → `EngineBridge` (+ module singleton `bridge`). `chat(messages, stream=False) -> str` **never raises** — returns a string; on failure it returns a string **starting with `"[engine error] "`** (bridge.py:114-117, 177-181). `chat_stream()` yields **raw** deltas (no ```` ```` stripping — strip yourself if streaming, bridge.py:40-43). Defaults: host `http://localhost:13305`, model `qwen3.5-2b-FLM`, fallback `qwen3-it-4b-FLM`, **timeout 30s**, **max_tokens 512**, **temperature 0.7** (settings.yaml:38-46). Public attrs (`engine.max_tokens`, `engine.temperature`) can be raised per-instance before use. Call `engine.close()` when done.
- **PC control:** `tools/pc_control.py` → `open_app`, `close_app`, `read_file`, `edit_file`, `delete_file`, `run_command`, `list_apps`, `is_app_running`, `set_permission_gate(fn)`, `approve_once()`. **No `create_folder` and no `search_files` here** (search_files is in `knowledge.py`; `create_folder` does not exist anywhere — AQ must add it).
- **Assistant:** `tools/assistant.py` → `set_reminder`, `list_reminders`, `add_todo`, `list_todos`, `complete_todo`, `set_schedule_item`, `get_daily_schedule`.
- **Knowledge/RAG:** `tools/knowledge.py` → `search_files(query, root)`, `read_pdf`, `read_text_file`, `index_documents`, `save_index`, `load_index`, `knowledge_search`. `tools/rag.py` → `RagIndex` (`.build`, `.search`, `.answer_prompt`, `.save`, `.load`).
- **Monitor:** `tools/monitor.py` → `get_full_report`, `get_cpu_usage` (blocks ~1s), etc.
- **Language:** `tools/language.py` → detect/translate (Tamil/English/Tanglish/Hindi).
- **Guards:** `tools/path_guard.py` (`is_path_allowed`, allowed roots = `Path.home()` only), `tools/control_guard.py` (`is_command_blocked`, `safe_cmd`).
- **Security:** `tools/security.py` (`security` singleton: `is_session_locked`, etc.), `tools/biometrics.py`.
- **Config:** `config.py` → `load_settings()`, `PROJECT_ROOT`, honors `MAYA_AI_HOME`.

There is **no** orchestration layer, **no** IQ/EQ/AQ split, **no** SQLite memory — that is the new work.

## 2. Decisions (resolved with user)

1. **Placement:** new package `MAYA INTELLIGENCE/maya_intelligence/` (underscores for import). This **overrides** the "code only in `custom/`" rule — user-approved; document the exception in `MAYA INTELLIGENCE/README.md`. `JARVIS/OpenJarvis/` stays untouched (`git -C JARVIS/OpenJarvis status --porcelain` empty).
2. **Reuse, not rewrite:** import `custom.*` via thin adapters. **Do not modify** `JARVIS/pyproject.toml` or any `custom/` file (keeps 333 tests intact).
3. **Personality:** new `maya` persona (college-age female assistant: soft, sweet, kind, warm, caring, friendly, respectful — **not** romantic), default in the new system. Existing `girlfriend`/`english-teacher` untouched.
4. **Memory:** new **SQLite** store; DB default `MAYA AI/memory/offline/maya_intelligence.db` (offline-only), override via env `MAYA_INTEL_DB`; categories personal/conversation/project/knowledge; never store secrets; ask before sensitive; CLI to inspect/edit/delete.
5. **EQ = prompt-level styling** (tone heuristic + directive), not a separate model (NPU too slow). Never fake emotions.
6. **Fast-path heuristics** for common commands (avoid an LLM call per step); LLM only when needed.
7. **Coexist:** keep `maya` / `maya-cloud` CLIs; new `maya-intel` entry point is additive.

## 3. Package layout & run model

```
MAYA INTELLIGENCE/
├─ README.md                      # what this is + custom/-rule exception + usage
├─ run.ps1 / run.sh               # set PYTHONPATH, run with JARVIS/.venv python
├─ maya_intelligence/
│  ├─ __init__.py
│  ├─ __main__.py                 # python -m maya_intelligence
│  ├─ _bootstrap.py               # insert ../JARVIS on sys.path so `import custom` works
│  ├─ config.py                   # DB path, persona path (reuse custom.config.load_settings)
│  ├─ cli.py                      # click: chat | memory | persona | status
│  ├─ orchestrator.py             # 10-step pipeline
│  ├─ adapters/
│  │  ├─ engine.py                # wrap custom.engine.bridge (+ error-prefix detect, close)
│  │  ├─ pc.py                    # wrap custom.tools.pc_control (+ add create_folder)
│  │  ├─ assistant.py             # wrap custom.tools.assistant
│  │  ├─ knowledge.py             # wrap custom.tools.knowledge / rag
│  │  ├─ language.py              # wrap custom.tools.language
│  │  └─ voice.py                 # wrap custom.tools.voice / voice_stt (optional)
│  ├─ engines/
│  │  ├─ iq.py                    # Cognitive: answer/plan via engine + RAG
│  │  ├─ eq.py                    # Emotional: tone detect + style directive
│  │  └─ aq.py                    # Action: intent→tool, confirm, execute, verify
│  ├─ memory/{store.py, schema.sql}
│  └─ persona/maya.md
└─ tests/
   ├─ conftest.py                 # add JARVIS to sys.path; temp MAYA_INTEL_DB
   └─ test_memory.py, test_eq.py, test_iq.py, test_aq.py, test_orchestrator.py
```

**Run model (no changes to JARVIS packaging):** run inside `JARVIS/.venv` with both roots on `PYTHONPATH` so `import custom` and `import maya_intelligence` resolve:
```powershell
$env:PYTHONPATH = "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS;C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA INTELLIGENCE"
& "JARVIS\.venv\Scripts\python.exe" -m maya_intelligence chat
```
`_bootstrap.py` also inserts `../JARVIS` as a fallback. (Optional later: editable install — out of scope now.) **Always use `JARVIS\.venv\Scripts\python.exe`** (a bare `python` may be 3.14; project needs 3.13, pyproject `requires-python >=3.10,<3.14`).

## 4. Spec → module mapping

| Spec | Implementation |
|---|---|
| §2 IQ | `engines/iq.py` over `adapters/engine.py` + `adapters/knowledge.py` |
| §2 EQ | `engines/eq.py` (tone heuristic + directive) |
| §2 AQ | `engines/aq.py` over `adapters/pc.py`, `assistant.py` (+ permission gate) |
| §3 Personality | `persona/maya.md` as system prompt |
| §4 Language | `adapters/language.py` (detect → reply same language) |
| §5 Memory | `memory/store.py` (SQLite, 4 categories, CRUD + FTS) |
| §6 Windows control | `adapters/pc.py` + path_guard/control_guard (confirm destructive) |
| §7 Orchestration | `orchestrator.py` (10 steps; fast-path) |
| §8 Offline | all local; honest error if engine down |
| §9 Voice | `adapters/voice.py` (Tamil TTS/STT pending — report honestly) |
| §10 Safety | confirm destructive; command-only; verify before claiming |

## 5. Design specifics (from code research)

**Engine adapter (`adapters/engine.py`):** wrap `EngineBridge`; expose `chat(messages) -> {ok, text}` where `ok=False` when text starts with `"[engine error] "`. Optionally raise `engine.max_tokens` (e.g. 800) and set `engine.temperature` per instance. Provide `health()`.

**AQ (`engines/aq.py`):**
- **Mandatory at startup:** call `pc_control.set_permission_gate(confirm_fn)`; otherwise gated calls hit a blocking `input()` and hang headless (pc_control.py:65). Serialize gated actions (the gate is a single module global).
- Intent map (heuristic regex first): open app→`open_app` (confirm), close app→`close_app` (confirm), search files→`knowledge.search_files`, read file→`read_file`, create folder→**new** `create_folder` (path-guard + confirm), delete→`delete_file` (confirm), edit→`edit_file` (confirm), run command→`run_command` (confirm; pre-check `control_guard.is_command_blocked`), todo/reminder→`assistant.*`, monitor→`monitor.get_full_report`, knowledge→`knowledge`/`rag`, else→ IQ chat.
- **Verification (never claim success without it):** open/close→`is_app_running(name)`; delete/create/edit→`os.path.exists`; todo→`list_todos()`; reminder→`list_reminders()`. Note `open_app` uses a bare name (may fail for `chrome.exe`); `close_app` matches by substring and returns `"Closed:"` even if nothing matched — verify independently.
- **New primitive:** `create_folder(path)` using `os.makedirs` + `path_guard.is_path_allowed` + permission gate (none exists today).

**EQ (`engines/eq.py`):** `analyze(text) -> ToneResult(tone, directive)` via keyword/regex (sad/stressed/angry/tired/happy/confused) → a short style directive appended to the system prompt. Never claim human feelings.

**IQ (`engines/iq.py`):** `answer(query, ctx)` calls engine with system = persona + EQ directive + memory context; `plan(task)` returns a step list (LLM) for multi-step; grounded via RAG when knowledge intent. Keep prompts small (max_tokens 512 default).

**Orchestrator (`orchestrator.py`):** steps Perception→Intent→Context(SQLite recall + recent chat)→IQ→EQ→Plan(LLM only if multi-step)→AQ select→Execute(confirm if destructive)→Verify→Respond (same language; optional TTS). Simple questions skip planning/tools.

## 6. Memory (SQLite)

- `schema.sql`: `memories(id, category, key, value, sensitivity, created_at, updated_at)` + `memories_fts` (FTS5) for keyword search; LIKE fallback.
- `store.py`: add/get/search/update/delete/list(category filter); secret-guard (reject obvious tokens/passwords); `MAYA_INTEL_DB` override (resolve per call, like `store.py`); create parent dir; WAL optional. Reuse `security.is_session_locked()` to gate the CLI.
- Location default: `<PROJECT_ROOT>/MAYA AI/memory/offline/maya_intelligence.db` (offline-only; never online/cloud). Gitignore the DB.
- Tests isolate via `monkeypatch.setenv("MAYA_INTEL_DB", str(tmp_path/"intel.db"))`. **Do not modify** existing `custom/tests/conftest.py`.

## 7. Implementation tasks (ordered)

1. **Scaffold** — dirs above; `maya_intelligence/_bootstrap.py` (add `../JARVIS` to sys.path); `run.ps1`/`run.sh` (PYTHONPATH + JARVIS venv python); `README.md` (usage, architecture, custom/-rule exception, Tamil/TTS limits, privacy).
2. **Persona** — `persona/maya.md` per spec §3/§11 (tone, Tamil/English/Tanglish rules, boundaries, no fake emotions).
3. **Adapters (thin)** — `engine.py`, `pc.py` (+`create_folder`), `assistant.py`, `knowledge.py`, `language.py`, `voice.py`; translate errors to a local `MayaIntelError`; no logic duplication.
4. **Memory** — `schema.sql` + `store.py` (+ tests: CRUD, search, secret-guard, category filter, `MAYA_INTEL_DB`).
5. **EQ** — tone detection + directive (+ tests).
6. **IQ** — `answer`/`plan` (stubbed engine in tests).
7. **AQ** — intent→tool map, permission gate wiring, `create_folder`, verification (+ tests with tmp files + stub gate).
8. **Orchestrator** — 10-step pipeline with fast-path; system prompt = persona + EQ directive + memory context (+ end-to-end test with stub engine).
9. **CLI** — `maya-intel chat | memory add|list|search|edit|delete | persona show | status` (mirror `custom/cli.py`: tools silent, CLI echoes; guard with `security.is_session_locked()`).
10. **Docs** — finish `README.md`.
11. **Verify** — run validation below; keep existing suite green.

## 8. Risks / pitfalls (concrete)

- **Blocking `input()`** if `set_permission_gate` not set → headless hang. Wire it at startup.
- **`max_tokens` 512** default truncates long replies; raise per-instance if needed.
- **Streaming deltas un-stripped** — accumulate + strip ```` ```` if using `chat_stream`.
- **Engine errors are strings** (`"[engine error] …"`), not exceptions — check prefix; don't save as assistant text.
- **`path_guard` roots = `Path.home()` only** — C:\ / network paths rejected.
- **`open_app` bare name / `close_app` substring** — verify independently.
- **No `create_folder`** — AQ must add it (guarded + confirm).
- **Tamil/Tanglish weak** on local FLM/Qwen (HANDOFF.md) — English-first, Tamil best-effort, never fake. Tamil TTS/STT pending → voice replies English-only.
- **Rule exception** — new top-level package; keep OpenJarvis read-only.
- **Privacy** — SQLite offline-only, gitignored, no secrets, never online.
- **Don't break 333 tests** — no edits to `custom/`; new tests only.

## 9. Validation

```powershell
$env:PYTHONPATH = "C:\Users\devar\Desktop\MAYA AI PROJECT\JARVIS;C:\Users\devar\Desktop\MAYA AI PROJECT\MAYA INTELLIGENCE"
$py = "JARVIS\.venv\Scripts\python.exe"
& $py -m pytest "MAYA INTELLIGENCE\tests" -q          # new tests green
& $py -m pytest custom/tests -q                      # still 333 passed, 1 skipped
git -C JARVIS/OpenJarvis status --porcelain           # empty
```
Smoke:
- `maya-intel status` → engine health ok, memory stats.
- `maya-intel chat` → real local reply in `maya` persona.
- `maya-intel memory add/list/search/delete` → persists in SQLite.
- "open notepad" → confirm prompt → verified via `is_app_running`.
- EQ: sad/tired input → supportive style; no fake emotion.
- Tamil/Tanglish input → best-effort same-language reply; honest if weak.

## 10. Out of scope

- Replacing `maya` / `maya-cloud` CLIs or the 13 phases; editing `custom/`.
- Mobile app, Gemini/cloud.
- Strong Tamil ASR/TTS (needs Whisper + Tamil `.onnx`).
- GUI changes; editable-install packaging.

## 11. Open questions

- None blocking. (Deferred: whether to later make the orchestrator the default for `maya chat`.)
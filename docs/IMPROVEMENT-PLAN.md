# Maya AI - Improvement Plan

> Deep research pannina improvement roadmap.
> Date: 2026-11-25
> Status: **Proposed** (implementation innum start aagala)
>
> Project rules (ellame follow pannanum):
> - `JARVIS/OpenJarvis/` = read-only, edit pannaadhu.
> - Namma code ellam `JARVIS/custom/` la mattum.
> - Config single source: `MAYA AI/config/settings.yaml`.
> - Offline data eppovum online anuppa koodadhu.
> - Destructive actions-ku user permission venum.

---

## 0. TL;DR

Project structure romba strong:

- 751+ tests irukku (core + intelligence + Windows app).
- CLI, Windows app, Android app ellame same `custom` + `MAYA INTELLIGENCE` core use pannudhu.
- Offline-first privacy model correct.
- Lemonade NPU inference, Kuyil Tamil TTS, phone pairing, PIN/biometrics ellame wired.

Aana 6 real gaps irukku:

1. **2 Windows tests red** - real regression, environment issue illa.
2. **`language.py` la duplicate implementation** - ~400 lines dead code.
3. **CI illa** - regression guard zero.
4. **Android minSdk 36** - Android 16 phones mattum support; reach romba kammi.
5. **Tamil STT/LLM weak** - Vosk-la Tamil illa, Whisper Tamil-la weak, 2B model Tamil-la weak.
6. **Docs/config drift** - same matter 5 docs-la different-a solludhu.

Priority order: **P0 (correctness/security) -> P1 (guardrails + reach + quality) -> P2 (strategic)**.

---

## 1. Verified Snapshot

Docs-la irukradhu nambala, actual-a run pannitu paathen (2026-11-25):

| Area | Status | Evidence |
|---|---|---|
| Core tests | **431 passed, 1 skipped** | `JARVIS\.venv\Scripts\python.exe -m pytest custom/tests -q` |
| Intelligence tests | **72 passed** | `MAYA INTELLIGENCE/tests` |
| Windows app tests | **246 passed, 2 failed** | `WINDOWS APPLICATION\windows\.venv\Scripts\python.exe -m pytest -q` |
| Lint | **110 ruff errors** (core + intelligence) | unused imports, unsorted imports, duplicate defs |
| CI | **Zero** | `.github/workflows` illa |
| Type check | **Zero** | mypy/pyright illa |
| Android minSdk | **36 (Android 16 only)** | `MOBILE APPLICATION/app/build.gradle.kts` |
| Android release | **minify OFF, shrink OFF** | arm64 APK ~118 MB, universal ~179 MB |
| Repo size | **~430 MB `.git`** | 330 MB loose objects + 100 MB garbage, no packs |
| Voice (CLI venv) | **Piper missing, Tamil TTS not ready** | `piper=False`, `faster_whisper=False`, Vosk `ta=no` |
| Voice (Windows venv) | **Piper/torch/faster-whisper installed** | dependency drift between venvs |
| Engine | Reachable, only `qwen3.5-2b-FLM` loaded | `GET http://localhost:13305/v1/models` -> 200 |
| Config | **Conflicting model keys** | `model: qwen3-3b` vs `engine.model: qwen3.5-2b-FLM` |
| Git tracked large files | 24.4 MB `libonnxruntime.so` (x86_64), 21.2 MB (arm64) | sherpa-onnx libs ~16 MB extra |

Note: `dist/mayaai.exe` (~143 MB) and APKs git-la illa. So `.git` bloat history/loose objects-la irundhu varudhu, not current tracked artifacts.

---

## 2. P0 - Red to Green (this week, ~1 day total)

### P0.1 Fix 2 failing Windows tests (paired phone IP bug)

- **Problem:** `_get_paired_phone_ip()` `d.host` read pannudhu, and first device-a return pannudhu. Most recent device-a select pannanum, and `d.last_ip` use pannanum.
- **File:** `WINDOWS APPLICATION/windows/app/services/phone_remote_client.py`
- **Tests:**
  - `test_paired_phone_ip_uses_last_ip_of_most_recent_device`
  - `test_paired_phone_ip_ignores_devices_without_an_ip`
- **Fix:** paired devices-a `last_seen` descending sort pannu; first device with non-empty `last_ip` return pannu.
- **Done when:** Windows suite 248/248 green.
- **Effort:** 30 min.

### P0.2 Clean up `language.py` duplicate implementation

- **Problem:** Two implementations merge aagi irukku. `_LangCode`, `_Detected`, `get_language_settings`, `_resolve_engine` duplicate; F601 duplicate dict key; later definitions earlier ones-a shadow pannudhu. ~400 lines dead/duplicate.
- **File:** `JARVIS/custom/tools/language.py`
- **Fix:** Later/complete implementation mattum vaithu, earlier block delete, duplicate dict key fix.
- **Done when:** core tests green + file single implementation.
- **Effort:** 2-3 hrs.

### P0.3 Fix 110 ruff errors

- **Where:** `JARVIS/custom`, `MAYA INTELLIGENCE`
- **Fix:** `ruff check --fix` (majority auto-fix), manual-a F601/F811 duplicate definitions.
- **Note:** JARVIS venv-la ruff illa; Windows app venv ruff use pannalam, or `ruff` dev dependency add pannalam.
- **Done when:** `ruff check` clean on core + intelligence.
- **Effort:** 2 hrs.

### P0.4 Remove UTF-8 BOM

- **File:** `WINDOWS APPLICATION/windows/app/services/server_service.py`
- **Fix:** BOM strip pannu. Root-la `.editorconfig` add pannu (`charset = utf-8`, `end_of_line = lf` or CRLF project convention).
- **Effort:** 10 min.

### P0.5 Config single source of truth

- **Problem:** `MAYA AI/config/settings.yaml` la `model: qwen3-3b` (legacy) + `engine.model: qwen3.5-2b-FLM` (actual). Engine actually serves only `qwen3.5-2b-FLM`.
- **Fix:** Legacy key remove pannu (or alias + deprecation warning). Loader-la unknown keys warn pannu. `settings.example.yaml` add pannu.
- **Files:** `MAYA AI/config/settings.yaml`, `JARVIS/custom/config.py`
- **Effort:** 1 hr.

### P0.6 Docs truth-up + encoding fix

- **Problem:** Docs-la stale claims + mojibake (`�?"`, `�o.`) irukku.
- **Fix:**
  - `AGENTS.md`: Qwen 3B -> `qwen3.5-2b-FLM`; old paths update.
  - `docs/API-CONTRACT.md`: "implementation innum illa" -> implemented.
  - `MAYA AI PROJECT.md`: "build innum illa" -> done.
  - `docs/ROADMAP.md` / `docs/HANDOFF.md`: statuses align.
  - `docs/VOICE.md`: CLI vs Windows voice status separate-a sollu.
  - Corrupted characters-a clean UTF-8 text-a maatru (ASCII markers use pannalam).
- **Effort:** 2 hrs.

### P0.7 Security: confirmation default-allow-a deny-a maatru

- **Problem:** `AQEngine.__init__` la `self._confirm = confirm_fn or (lambda msg: True)`. Caller confirm_fn pass pannala-na, destructive actions auto-approve aagum.
- **File:** `MAYA INTELLIGENCE/maya_intelligence/engines/aq.py`
- **Fix:** Default **deny** (`lambda msg: False`) or raise explicit error. Caller confirm function pass pannaladhu-nu force pannu. Confirm-gate coverage test add pannu (delete/send/shutdown/phone control).
- **Effort:** 30 min.

### P0.8 Git cleanup

- **Problem:** `.git` ~430 MB (330 MB loose + 100 MB garbage), no packs.
- **Fix:** `git gc --prune=now`. Size check pannu.
- **Note:** Still big-na `git filter-repo` venum - adhu history rewrite + force push, **user permission venum**.
- **Effort:** 10 min.

### P0 checklist

- [ ] P0.1 Paired phone IP bug fix + 2 tests green
- [ ] P0.2 `language.py` dedupe
- [ ] P0.3 Ruff 110 -> 0
- [ ] P0.4 BOM strip + `.editorconfig`
- [ ] P0.5 Config conflict fix + schema/unknown-key warning
- [ ] P0.6 Docs truth-up + encoding
- [ ] P0.7 Confirm default-deny
- [ ] P0.8 `git gc --prune=now`

---

## 3. P1 - Guardrails, Reach, Quality (next 2-3 weeks)

### 3.1 CI + Pre-commit (highest leverage)

GitHub Actions, `windows-latest`, Python 3.13:

- `lint` -> ruff (core + intelligence + Windows app)
- `test-core` -> JARVIS suite
- `test-intel` -> 72 tests
- `test-windows` -> `QT_QPA_PLATFORM=offscreen`
- `android` -> JDK 21 + `gradlew assembleDebug`

Extras:

- Cache: uv + Gradle.
- `.pre-commit-config.yaml`: ruff, trailing whitespace, EOF, BOM check, large-file guard.
- **Benefit:** Red tests merge aagaadhu; 110 ruff errors thirumba varaadhu.

### 3.2 Type checking baseline

- Pyright `basic` on `JARVIS/custom` + `MAYA INTELLIGENCE`.
- CI-la first `continue-on-error: true`; error count ratchet down.
- Engine bridge, voice, server-la `TypeError`/`None` bugs catch aagum.

### 3.3 Android reach + size (biggest user impact)

- **minSdk 36 -> 26** (or 29). Code already API 24/26/29 guards use pannudhu, so feasible.
- Test matrix: API 26, 29, 33, 36 (emulator + real phone).
- **Release R8 ON:** `isMinifyEnabled = true`, `isShrinkResources = true` + ProGuard rules for JNI/sherpa/onnx.
- **ABI splits:** release-la `arm64-v8a` mattum; `x86_64` debug/emulator-ku. Universal APK ship pannaadhu.
- **APK diet:** arm64-la ~32 MB native libs; remaining ~86 MB enna nu APK Analyzer-la paakkanum (llama.cpp build libs irukkum).
- Vendored `libonnxruntime.so`-va Maven `onnxruntime-android` AAR replace panna 45 MB git + APK savings (sherpa conflict verify pannanum).
- **Expected:** 118 MB -> ~60-75 MB arm64.

### 3.4 Voice dependency parity

- **Problem:** Windows venv-la `piper`, `torch`, `faster-whisper` irukku; JARVIS venv-la illa. CLI-la Tamil TTS "not ready".
- **Fix:** `JARVIS/pyproject.toml` la `[project.optional-dependencies] voice = [...]` add pannu; Windows app adhe extras use pannum. CI-la `pip check`.
- Docs-la "Tamil TTS works" nu sollradhu Windows app-ku mattum - CLI-ku separate status.

### 3.5 Tamil STT upgrade (real gap)

- **Current:** Vosk-la Tamil model illa; Whisper Tamil-la weak (public benchmark WER ~67.5%).
- **Research:** IndicConformer 600M open weights - Tamil WER ~27% (FLEURS). Idhu dhaan correct upgrade path.
- **Plan:**
  1. ONNX int8 export.
  2. `custom/tools/voice_stt.py` la third backend add pannu.
  3. 20 own Tamil clips-la WER + latency measure.
  4. Clear-a better-na default-a maatru.
- Sherpa-onnx-la Tamil transducer model irundha adhu innum easy (already bundled) - verify pannanum.

### 3.6 Tamil/Tanglish LLM: measure first, then router

- **Current:** Default `qwen3.5-2b-FLM` (NPU, fast) Tamil-la weak; 4B/8B slow (~45 s for 8B).
- **Research:** `tamil-lm-2b-instruct` (Tamil-adapted Qwen3.5-2B, Tanglish support) - **pilot only**, public claims verify pannanum.
- Android code-la already `tamil-lm-2b` switch reference irukku; core/Windows align pannalam.
- **Plan:**
  1. **Eval set** (50-100 prompts: Tamil chat, Tanglish, translation, tool-calls) - baseline Qwen 2B vs 4B.
  2. Prompt improvements: Tamil few-shot + transliteration normalization (`language.py` cleanup ithuku help aagum).
  3. Pilot tamil-lm-2b via llama.cpp server (separate port). Language-based router: Tamil/Tanglish -> tamil model, English -> Qwen.
  4. Eval + latency clearly better-na mattum default maatru.

### 3.7 Security hardening

- **RAG prompt-injection guard:** Knowledge PDF-la "ignore previous instructions" irundha small model follow pannum. Retrieved text-a delimited "DATA ONLY" block-la wrap pannu; instruction-like lines strip pannu.
- **Tool audit log:** `MAYA AI/memory/offline/tool_audit.jsonl` - tool name, args hash, confirmed?, result status. Local only.
- **Confirm-gate coverage test:** Every destructive tool (delete, send, shutdown, phone control) confirm pass aagudha nu automated test.
- **Phone server:** Token rotation + rate limit + failed-auth logging review.

### 3.8 `maya doctor` + task runner

- `maya doctor`:
  - Settings schema validate.
  - Engine `/v1/models` check + expected model present-ah.
  - Voice model files.
  - Ports 13305 / 8000 free-ah.
  - Disk space.
  - Offline dirs writable.
  - Pass/fail table output.
- `scripts/dev.ps1`: `test`, `lint`, `fmt`, `doctor`, `build-app`, `build-apk`. Root-la single entry point, new tool install venam.

---

## 4. P2 - Strategic (1-2 months)

| Track | What | Why |
|---|---|---|
| **Eval harness** | `evals/tamil_golden.jsonl`, runner script, pass-rate + p50/p95 latency tracking | Model/prompt changes quality-a improve pannudha nu prove panna |
| **Observability** | Structured JSON logs + request ID across CLI/app/server; per-step pipeline timing | "Why slow / why wrong" debug easy aagum |
| **Memory UX** | Windows + Android-la memory view/edit/delete, "forget that" intent, encrypted export | Privacy promise-ku user control venum |
| **Release pipeline** | Signed APK/AAB + Inno Setup/MSIX installer + GitHub Releases + checksums | Manual build/install risk kammi |
| **Docs consolidation** | Single `docs/STATUS.md` (verified date + commands), old phase docs `docs/archive/`-ku | 5 docs same matter different-a sollradhu stop |
| **Optional TTS upgrade** | Maya 2 Native (2.5B, ~5 GB) - laptop-ku heavy; only batch/high-quality mode | Kuyil already Tanglish-ku best; default maatru venam |

---

## 5. Suggested 4-Week Sequence

| Week | Work | Outcome |
|---|---|---|
| **1** | All P0 + CI skeleton (lint + core tests) | Red tests green, regression guard start |
| **2** | Ruff/type baseline, voice dependency parity, Android minSdk 26 + R8 + ABI splits | APK small, old phones support |
| **3** | Tamil eval harness + baseline, IndicConformer STT pilot, security hardening (deny-by-default, audit log, RAG guard) | Measured Tamil quality + safer tools |
| **4** | tamil-lm-2b router pilot decision, `maya doctor`, docs consolidation | Data-driven model decision, clean docs |

**Recommendation:** Week 1 P0 + CI first. Adhu mudinja pinnaadi Android reach (user impact peru), appuram Tamil quality (eval baseline illama model maatrina guess dhaan).

---

## 6. Research Notes

Public benchmarks (Zhagaram Labs Uraikal, Hugging Face model cards) preliminary. Own machine-la, own Tamil clips-la measure pannama default model maatrakoodadhu. Especially `tamil-lm-2b` and `IndicConformer` numbers verify pannanum before committing.

Reference numbers (public, preliminary):

| System | Tamil STT WER (FLEURS) |
|---|---|
| IndicConformer 600M | ~27.1% |
| Indic-Transcribe core | ~26.1% |
| Whisper large-v3 turbo | ~67.5% |

Local agent best practices (industry, 2026):

- Validate every tool call before executing.
- Offer only the tools a task needs; prefer narrow tools.
- Human approval for send/delete/pay/post actions.
- Treat documents + tool results as data that may contain injected instructions.
- Bind local servers to localhost unless deliberately exposed.
- Log every tool call.

Ithu ellame already project-la partial-a irukku (LAN guard, pairing, PIN). Missing: default-deny confirm, audit log, RAG injection guard.

---

## 7. Verification Commands

Core tests:

```powershell
JARVIS\.venv\Scripts\python.exe -m pytest custom/tests -q
```

Intelligence tests:

```powershell
MAYA INTELLIGENCE\.venv\Scripts\python.exe -m pytest -q
```

Windows app tests:

```powershell
WINDOWS APPLICATION\windows\.venv\Scripts\python.exe -m pytest -q
```

Lint (Windows venv ruff):

```powershell
WINDOWS APPLICATION\windows\.venv\Scripts\ruff.exe check "JARVIS\custom" "MAYA INTELLIGENCE"
```

Engine check:

```powershell
JARVIS\.venv\Scripts\python.exe -c "import httpx; r=httpx.get('http://localhost:13305/v1/models', timeout=5); print(r.status_code, [m['id'] for m in r.json()['data']])"
```

Git size check:

```powershell
git count-objects -vH
```

---

## 8. Notes

- Idhu plan file. Implementation start pannina status update pannanum.
- P0 mudinja pinnaadi ithu `docs/STATUS.md`-la move aagalam (single source of truth).
- `JARVIS/OpenJarvis/` edhuvum edit panna koodadhu - patch venum-na `JARVIS/patches/` use pannu.

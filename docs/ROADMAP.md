# MAYA AI — Build Roadmap (13 Phases)

> Ithu build tracker. Ovvoru phase mudinja appuram status update pannuvom.
> Orchestrator: `maya-master`. Agents: coder, tester, reviewer, security, debugger, database, documentation, bug-hunter.

## Status board

| Phase | Velai | Agents | Status |
|---|---|---|---|
| 1 | Foundation: `pyproject.toml`, CLI bugs, persistence, tests | coder → tester → reviewer | ✅ Done |
| 2 | OpenJarvis install + engine bridge | coder, debugger | ✅ Done |
| 3 | Qwen 3B download + CPU/GPU/NPU config | coder, debugger | ✅ Done |
| 4 | Real chat wiring + persona + English teacher | coder, tester, reviewer | ✅ Done |
| 5 | Tools hardening: monitor loop, knowledge index, assistant | coder, database, tester | ✅ Done |
| 6 | Security: PIN (biometrics moved to Phase 11) | security, coder, tester | ✅ Done |
| 7 | Voice: Piper TTS + STT + wake word | coder, tester | ✅ Done (Tamil awaits models) |
| 8 | OS layer: Windows tray, docs, final audit | coder, documentation, security, bug-hunter, reviewer | ✅ Done |
| 9 | Cloud: Gemini as a separate, opt-in command | coder, security, tester | ✅ Done (live key pending) |
| 10 | Knowledge RAG: BM25 + semantic embeddings | coder, tester, documentation | ✅ Done |
| 11 | Biometrics: Hello face + voice phrase/voiceprint + session unlock | security, coder, tester | ✅ Done |
| 12 | Multi-device: trusted pairing + HMAC-signed sync bundles | coder, security, tester, documentation | ✅ Done (manual transport) |
| 13 | Session watchdog: idle/session auto-lock + optional voice re-check | security, coder, tester, documentation | ✅ Done |

Legend: ⬜ pending · ⏳ running · ✅ done · ⚠️ blocked (user action needed)

---

## Phase 1 — Foundation (code only, no download)

**Goal:** `custom` CLI installable + working, confirmed bugs fixed, assistant data persists.

- `JARVIS/pyproject.toml` — hatchling, `maya = custom.cli:main`, deps click/pyyaml/psutil/pypdf
- CLI selectors fixed: `reminder set TIME TEXT`, `todo complete INDEX`, `devices wifi SSID PASS`, `devices sync SRC DEST [REMOTE]`
- Duplicate console output removed (tool layer silent)
- `custom/tools/store.py` — local JSON store → `MAYA AI/memory/offline/assistant.json`
- `custom/__init__.py` lazy import → no RuntimeWarning
- Dead code `_maya_reply` removed
- `custom/plugins/` folder created
- `custom/tests/test_cli.py` added (CliRunner regression tests)
- `custom/README.md` corrected

**Exit criteria:** pytest green · `todo add` → `todo list` across 2 processes keeps data · `reminder set` exits 0.

---

## Phase 2 — Engine (needs user permission: network)

- `uv sync` inside `JARVIS/OpenJarvis` (read-only repo — install only, no edits)
- Bridge module `custom/engine/bridge.py` → OpenJarvis chat entry point
- Settings keys for engine path / backend selection in `settings.yaml`
- Fallback: if engine unavailable → clear error, not crash

**Exit criteria:** engine health check passes · bridge returns one real model reply.

---

## Phase 3 — Model (resolved without a download)

- **Actual decision:** no Qwen download. The laptop already runs **AMD
  Lemonade Server** (`http://localhost:13305`) with FLM models on the NPU.
- Chosen model: `qwen3.5-2b-FLM`, fallback `qwen3-it-4b-FLM`
- Backend config → `MAYA AI/config/settings.yaml` (`engine:` section)
- Details + model table + quality caveat → `docs/ENGINE-SETUP.md`

**Exit criteria:** ✅ model reachable through the bridge · ✅ documented why the
NPU models are used · ⚠️ Tamil quality is limited (documented honestly).

---

## Phase 3b — Model folder note

`MAYA AI/Model/` stays empty on purpose — no local weight files are needed
while Lemonade serves the FLM models. If a downloadable model is added later,
it goes there and `engine.mode` stays `direct`.

---

## Phase 4 — Real chat

- `maya chat` → bridge → model (replace hardcoded template replies)
- Persona injection from `MAYA AI/persona/girlfriend.md`
- English teacher persona switch (`/persona english-teacher`)
- Chat history → `MAYA AI/memory/offline/` only

**Exit criteria:** real answers, persona-consistent, history persists, offline→online never.

---

## Phase 5 — Tools hardening

- Monitor: background loop + threshold alerts (CPU/RAM/disk/temp/battery)
- Knowledge: real content search (`_read_text_snippet` stub replaced), index persisted
- Assistant: alarm/scheduler, daily schedule, calendar basics
- Database: SQLite for knowledge index / memory (local only, migrations)

**Exit criteria:** alerts fire, knowledge search finds content matches, reminders actually trigger.

---

## Phase 6 — Security

- PIN lock first (local hash, no cloud)
- Voice recognition second
- Face recognition last
- Unauthorized user alert

**Exit criteria:** lock out after N fails · biometrics never leave laptop.

---

## Phase 7 — Voice

- Piper TTS (Tamil + English `.onnx`) → `MAYA AI/voice/`
- STT (voice → text → chat)
- Wake: 3 claps / "Maya, Maya, Maya"

**Delivered:**
- `custom/tools/voice.py` — Piper TTS wrapper, SAPI fallback, wake-phrase check
- `custom/tools/voice_stt.py` — **offline Vosk STT** (files + microphone),
  48 kHz capture with anti-alias/resample/high-pass/normalise pipeline
- `custom/tools/voice_clap.py` — **3-clap wake detection** (ported + fixed)
- Vosk models live inside the project: `MAYA AI/Model/models/vosk-en`,
  `vosk-en-in` (121 MB, no runtime downloads)
- Offline wheels kept in `JARVIS/wheels/`
- **English TTS + English/Indian-English STT both work today**
- Tamil: TTS needs `piper-tts` + a `.onnx` voice; official Vosk has no Tamil
  STT model — Maya reports both honestly instead of faking them

Details, commands and troubleshooting: `docs/VOICE.md`.

**Exit criteria:** ✅ speak works · ✅ mic transcription works ·
✅ clap pattern detected (logic verified) · ⬜ Tamil speech awaits models.

---

## Phase 8 — OS layer + polish

- Windows: tray app, autostart (Task Scheduler)
- `MAYA AI/scripts/` launchers
- Final: security audit, bug hunt, review, docs (`UPDATE.md`, setup guide, troubleshooting)

**Exit criteria:** starts on login · full test + security report clean.

---

## Phase 9 — Cloud (Gemini), separate command

- `custom/cloud_cli.py` → `maya-cloud` (second console script)
- `custom/tools/cloud.py` — REST client, no SDK, key from `.env`
- Confirmation before every send; `--dry-run` shows the exact payload
- Offline memory never attached; online log kept in `memory/online/`
- English-only concern: this is a third-party service, so it stays opt-in

**Exit criteria:** ✅ dry-run works · ✅ refuses without a key ·
✅ declining the confirmation sends nothing · ⬜ live call needs the user's key.

Details: `docs/CLOUD.md`.

---

## Phase 10 — Knowledge RAG (BM25 + semantic)

- `custom/tools/rag.py` — 600-char chunks, BM25, atomic JSON index
- `custom/tools/embeddings.py` — model2vec `potion-base-32M` (512-dim), cached
  inside `MAYA AI/Model/hf`; numpy-only, no torch/ONNX runtime
- Hybrid retrieval = reciprocal rank fusion of BM25 + cosine; modes
  `hybrid` / `bm25` / `semantic`; silent BM25 fallback when the model is absent
- Incremental indexing (mtime + size) fills missing vectors for reused chunks
- CLI: `knowledge rag-index [--reset] [--no-semantic]`,
  `rag-search|rag-ask [--mode ...]`, `rag-status`
- `rag-ask` builds a grounded prompt and answers with the local model,
  printing the sources it used

**Exit criteria:** ✅ `docs/` indexed (9 files, all chunks embedded, dim 512) ·
✅ zero-overlap paraphrase: BM25 finds nothing, semantic/hybrid find the right
note · ✅ grounded answer cites the right source · ✅ 12 embedding tests +
11 hybrid tests.

Details: `docs/KNOWLEDGE.md`.

---

## Phase 11 — Biometrics (face + voice)

- **Face** — Windows Hello through the trusted `MAYA.exe` helper, copied to
  `MAYA AI/security/bin/` (`--face-check` → `AVAILABILITY=Available`)
- **Voice passphrase** — Vosk transcript → PBKDF2-SHA256 (260k) hashes;
  ported from the old project's `lock_auth.py`
- **Voiceprint** — Vosk `vosk-spk` x-vectors (128-dim), centroid + cosine
  threshold 0.65; both factors required by default
- Storage: `MAYA AI/memory/offline/biometrics.json` — no audio, no photo
- CLI: `biometrics status | face-check | face-verify | face-settings |
  voice-enroll | voice-verify | voice-reset`
- Lockout after 5 failed voice attempts; PIN remains the fallback
- **Session lock integration** — `maya lock` / `security unlock <pin|--face|--voice>`,
  `biometrics face-verify|voice-verify --unlock`, and a **full CLI guard**:
  every command except unlock/status/verification/help is refused while locked
  (`LockedGroup` in `custom/cli.py`; `session_locked` + `last_unlock` in
  `security.json`); `maya-cloud ask/chat` are guarded too

**Exit criteria:** ✅ Hello reports Available from the project copy ·
✅ enroll 3 samples → 128-dim voiceprint · ✅ same voice 1.000 (verified) ·
✅ different voice 0.228 (rejected even with the correct phrase) ·
✅ locked session: chat blocked, David voice unlocks, Zira voice rejected ·
✅ locked CLI: todo/monitor/config/set-pin blocked, unlock restores them ·
✅ locked `maya-cloud` refuses sends · ✅ 30 biometrics + 47 security +
4 cloud-lock tests · ✅ no raw data stored.

Details: `docs/BIOMETRICS.md`.

---

## Phase 12 — Multi-device pairing + signed bundles

- Trusted device registry in `custom/tools/devices.py`; only a salted
  PBKDF2-SHA256 hash (600k iterations) of the pairing code is stored
  (`memory/offline/devices.json`). The display `id` is random and is not used
  for authentication.
- Pairing codes: generated 128-bit (32 hex) or user-supplied 16+ chars
  (whitespace stripped, hidden `--ask-code` prompt)
- `devices pair | list | revoke` — revoking invalidates old bundles
- `export` collects explicit files/folders; `import` verifies and extracts into
  an explicit destination with staging + backup/rollback
- HMAC-SHA256 over canonical JSON, key derived from the pairing code with
  PBKDF2-SHA256 (600k iterations, per-bundle salt); KDF algorithm/iterations/
  salt are validated (no downgrade)
- Import checks sender pairing, code, signature, size/base64/SHA-256, path
  safety (traversal, ADS, reserved names, junction/symlink), duplicate/prefix
  conflicts and destination conflicts
- Limits are checked before reads/decodes: `devices.bundle.max_files` (200) /
  `max_mb` (25); bundle JSON read is capped
- Export refuses `.env`, security stores, keys and `DEVARAJ/` unless
  `--allow-sensitive`
- No network used; transport is manual (USB / local share)
- Bundles are **signed, not encrypted**; no anti-replay guarantee (documented)

**Exit criteria:** ✅ pair/list/revoke without storing the raw code ·
✅ cross-install export → import roundtrip · ✅ wrong code, unpaired sender,
re-pairing with a new code, tampering, KDF downgrade, path traversal/ADS/
reserved names, duplicate/prefix paths all rejected · ✅ write failure rolls
back · ✅ export/import limits enforced before allocation · ✅ junction/symlink
containment · ✅ sensitive-file deny-list · ✅ 82 device tests + lock guard ·
✅ full suite 299 passed (1 skipped) · ✅ OpenJarvis clean.

Details: `docs/DEVICES.md`.

---

## Phase 13 — Session watchdog (continuous unattended-session check)

- `custom/tools/watchdog.py` + `maya security watchdog`
- Foreground, command-driven loop; Maya never starts it by itself
- **Idle auto-lock** — Windows `GetLastInputInfo`; Wayland reports idle detection unavailable
- **Session expiry** — optional lock N minutes after the last successful unlock
- **Voice re-check** — optional periodic challenge using the enrolled phrase +
  voiceprint; skipped (not failed) without enrollment/model; failures lock and
  raise an unauthorized alert
- Config: `security.watchdog.*` in `settings.yaml`; CLI overrides for idle,
  session, voice interval, check interval and mic seconds; `--once` for one check
- Reuses the existing `SecurityManager` lock + alert log; no new store, no
  network, no service registration

**Exit criteria:** ✅ idle lock triggers exactly at the limit and records an
alert · ✅ unknown idle never locks · ✅ session expiry works independently ·
✅ voice success keeps the session open, failure/exception locks · ✅ voice
disabled or unenrolled never records · ✅ CLI blocked while locked and wired to
the isolated store · ✅ 25 watchdog tests · ✅ full suite 333 passed (1 skipped) ·
✅ OpenJarvis clean.

Details: `docs/BIOMETRICS.md` (session watchdog section).

---

## Rules that never change

- `JARVIS/OpenJarvis/` = read-only ❌
- Namma code `JARVIS/custom/` la mattum ✅
- Offline → Online data ❌
- Important / destructive action → permission ⚠️
- Maya = command only

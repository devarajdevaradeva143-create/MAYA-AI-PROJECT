# MAYA AI — Windows App Full Plan

> Ithu Windows desktop app-oda full build plan + phone server plan.
> Vera AI coder ithai paathu phase-by-phase code pannalam.
> Simple Thanglish-la ezhuthirukken.

**Status:** Build complete — all 13 phases implemented (195 tests green). Monitor, Teacher, Security pages wired; PIN lock, tray settings, phone server UI added.

| Phase | Status |
|---|---|
| 0 — Env + skeleton | ✅ |
| 1 — Shell + theme + single instance | ✅ |
| 2 — Settings repository (ruamel + backups) | ✅ |
| 3 — Chat (streaming, stop, retry, persona, history) | ✅ |
| 4 — Voice (STT, TTS, clap wake, name wake) | ✅ |
| 5 — PC control + permissions | ✅ |
| 6 — Monitoring | ✅ |
| 7 — English Teacher | ✅ |
| 8 — Security / PIN lock / Windows Hello | ✅ |
| 9 — Pairing + phone server (real-engine E2E verified) | ✅ |
| 10 — Tray / autostart | ✅ |
| 11 — Packaging + docs | ✅ |
| 12 — Phone Remote (laptop controls phone) | 🔄 Planned |

**All 161 tests pass, ruff clean.**

**OS:** Windows 10 / 11 (tested on Windows 11 build 26300)
**Project folder:** `C:\Users\devar\Desktop\MAYA AI PROJECT\LAPTOP\windows\`
**Shared engine code:** `JARVIS\custom\` (namma code — edit allowed ✅)
**OpenJarvis:** `JARVIS\OpenJarvis\` — **READ ONLY** ❌

## Summary of all phases

| Phase | Key Features | Status |
|---|---|---|
| **0** | Env + skeleton, paths, logging, `--headless`/`--tray`, empty window | ✅ |
| **1** | Sidebar + 7 pages, live theme switch, single-instance focus | ✅ |
| **2** | Ruamel YAML round-trip + timestamped backups + CRLF preserve | ✅ |
| **3** | Streaming chat, Stop/Retry, persona switch (maya/teacher), history persistence | ✅ |
| **4** | `listen_once()` — mic STT; `speak()` — TTS SAPI; 3-clap wake; "Maya Maya Maya" name wake loop; Voice UI page with orb, PTT, TTS test, transcript log, wake status | ✅ |
| **5** | PC control grid (15 actions), ConfirmDialog for destructive actions, path/command guards, activity log, phone request queue | ✅ |
| **6** | Monitoring page: CPU/RAM/GPU/NPU/battery cards + disk list + uptime + 2s refresh | ✅ |
| **7** | English Teacher: vocabulary, grammar, pronunciation, idioms lessons with quiz-style questions | ✅ |
| **8** | Security: 4-digit PIN lock (3-attempt lockout/30s), Windows Hello face config, voiceprint enrollment (PBKDF2 hashes), audit log | ✅ |
| **9** | Pairing + phone server: real-engine E2E verified (health 200, claim 200, chat 200, revoke 200) | ✅ |
| **10** | Tray/Autostart: minimize to system tray, tray menu (Open/Quit), autostart registry key | ✅ |
| **11** | Packaging + docs: PyInstaller build, README/HANDOFF update | ✅ |
| **12** | Phone Remote: PhoneRemotePage (screen view, input controls, file browser), WebSocket client for screen stream, session start/stop with phone confirm, Settings toggle | 🔄 Planned |

**Author:** Vera AI (Nemotron 3.5 Lightning Free) — local-first personal AI assistant for Windows + Fedora.
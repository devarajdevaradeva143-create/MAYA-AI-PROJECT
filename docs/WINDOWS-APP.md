# Maya AI — Windows Desktop App

Local-first PySide6 desktop app in `WINDOWS APPLICATION\windows\`.

## Features

- Chat: streaming, Stop, Retry, persona switch (Maya / English Teacher), history
- Voice: STT (Vosk), TTS (SAPI), 3-clap wake, "Maya Maya Maya" name wake
- PC control: 15 actions with confirm dialog for risky ones
- Monitoring: CPU, RAM, GPU, NPU, battery, disks, uptime (live cards)
- English Teacher: vocabulary, grammar, pronunciation, idioms
- Security: PIN (PBKDF2, local store), Windows Hello, voiceprint, lock screen
- Cloud AI (optional): Gemini fallback in chat (`Send to Gemini`), key in `.env`
- Settings: YAML + timestamped backups, theme, tray behaviour, phone server
- Phone server: Start/Stop/PIN from Settings; headless mode (`--headless`)
- Phone server auto-start: optional "Start phone server with Maya" checkbox
  in Settings (persisted as `server.auto_start`; runs in a worker thread)
- Tray: close-to-tray, minimize-to-tray, start-minimized (`--tray`)

## Run

```powershell
cd "WINDOWS APPLICATION\windows"
.\.venv\Scripts\python.exe -m app            # GUI
.\.venv\Scripts\python.exe -m app --tray     # start in tray
.\.venv\Scripts\python.exe -m app --headless # phone server only
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q      # 195 tests
.\.venv\Scripts\ruff.exe check app tests      # clean
```

## Build

```powershell
.\.venv\Scripts\python.exe -m PyInstaller mayaai.spec --noconfirm
# -> dist\mayaai\mayaai.exe  (one-folder build)
```

The spec uses `COLLECT` (one-folder), not one-file: a 335 MB one-file exe
extracts itself to `%TEMP%` on every launch (~18 s). The folder build starts in
~2 s. Keep the whole `dist\mayaai\` folder together when moving/copying the app.

### Desktop shortcut

`C:\Users\devar\Desktop\Maya AI.lnk` →
`WINDOWS APPLICATION\windows\dist\mayaai\mayaai.exe`
(working dir `dist\mayaai`, icon from the exe).

### How the exe finds `MAYA AI\`

A packaged build must not use `__file__` (it lives in the PyInstaller temp
extraction folder). Resolution order, implemented in `app/paths.py` and
mirrored in `JARVIS\custom\config.py`:

1. `MAYA_AI_HOME` (validated against `config\settings.yaml`)
2. `MAYA AI\` beside the exe, then at each parent folder up to 5 levels
   (`dist\` → `windows\` → `WINDOWS APPLICATION\` → project root)
3. dev fallback: `WINDOWS APPLICATION\windows\..\..\MAYA AI`

At startup the app publishes the resolved folder as `MAYA_AI_HOME` so
`JARVIS\custom` (config, memory, voice, security) uses the same one.

## Security model

- PIN hashed with PBKDF2-SHA256 (200k iterations) + salt in
  `MAYA AI\memory\offline\security.json`. **Never** stored in `settings.yaml`.
- Windows Hello via the trusted `MAYA.exe` helper (local only).
- Voiceprint via Vosk x-vectors (centroid + cosine, threshold 0.65).
- Lock screen shown at startup when a PIN is set and the session is locked.

## AI Engine switches (Lemonade / Gemini)

Settings → **AI Engine** has two On/Off switches, so you can run either brain
or both:

- **Lemonade (local engine)** writes `engine.enabled`. Off means chat will not
  call the laptop model: every message goes straight to Gemini (no per-message
  prompt), as long as Gemini is on and a key is saved. If it is not, the Chat
  page asks you to turn one on in Settings.
- **Gemini (cloud AI)** writes `cloud.enabled`.

Each switch shows **On** (green) or **Off** (grey) and saves immediately, so
the open Chat page updates its engine badge without a restart. If both switches
are off the settings card says chat cannot answer. Every reply bubble is labelled
with who produced it — `Lemonade (local)` or `Gemini (cloud)` — and shows
"Thinking…" until the first chunk arrives.

## Cloud AI (Gemini) — opt-in

The desktop app is offline by default. Cloud is a fallback the user must ask
for, not a mode you switch on:

1. Settings → **AI Engine → Gemini**: paste an API key (from
   <https://aistudio.google.com/app/apikey>) and press **Save key**. It is
   written to `MAYA AI PROJECT\.env` as `GEMINI_API_KEY`, never printed.
2. Switching the local engine off is the standing confirmation: from then on
   each message is sent to Gemini without asking again. If the local engine is
   on but fails (offline, timeout), Gemini answers that message automatically —
   there is no per-message "Send to Gemini" click any more.
3. **Gemini prompt** — the box under the switch (writes `cloud.system_prompt`)
   is sent as Gemini's `systemInstruction` with every request; empty means
   Gemini's own default. Press **Save prompt** to store it.
4. Only the message you typed leaves the laptop — offline history, memory
   files and personal details are never attached.
5. `cloud.enabled: false` in `settings.yaml` (or the switch) makes every
   cloud call refuse. Cloud exchanges are logged separately in
   `MAYA AI\memory\online\cloud_log.jsonl`.

Code: `app/services/cloud_service.py` wraps `custom/tools/cloud.py`, the only
module that talks to the internet.

## Notes

- `pystray` + `pillow` are dependencies of `WINDOWS APPLICATION\windows` (not the JARVIS venv).
- `JARVIS\OpenJarvis\` is read-only.
- Detailed completion plan: `docs\WINDOWS-APP-COMPLETION-PLAN.md`.

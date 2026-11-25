# Maya AI — Windows Desktop App

Local-first PySide6 desktop app in `WINDOWS APPLICATION\windows\`.

## Features

- Chat: streaming, Stop, Retry, persona switch (Maya / English Teacher), history
- Voice: STT (Vosk), TTS (SAPI), 3-clap wake, "Maya Maya Maya" name wake
- PC control: 15 actions with confirm dialog for risky ones
- Monitoring: CPU, RAM, GPU, NPU, battery, disks, uptime (live cards)
- English Teacher: vocabulary, grammar, pronunciation, idioms
- Security: PIN (PBKDF2, local store), Windows Hello, voiceprint, lock screen
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
# -> dist\mayaai.exe
```

### Desktop shortcut

`C:\Users\devar\Desktop\Maya AI.lnk` → `WINDOWS APPLICATION\windows\dist\mayaai.exe`
(working dir `dist`, icon from the exe).

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

## Notes

- `pystray` + `pillow` are dependencies of `WINDOWS APPLICATION\windows` (not the JARVIS venv).
- `JARVIS\OpenJarvis\` is read-only.
- Detailed completion plan: `docs\WINDOWS-APP-COMPLETION-PLAN.md`.

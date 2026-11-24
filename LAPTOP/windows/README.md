# Laptop — Windows

Maya AI desktop app for Windows (PySide6, Python 3.13).

- UI: PySide6 (Python 3.13)
- Engine: `JARVIS\custom` reuse
- Phone server: FastAPI `:8420`
- Tray + autostart + wake (3 clap / "Maya" x3)

## Full plan

```
LAPTOP\windows\PLAN.md
```

## Shared API

```
docs\API-CONTRACT.md
```

## Status

Build complete — all 7 pages wired (chat, voice, pc, monitor, teacher, security, settings).
243 tests pass (1 skipped), ruff clean. `dist\mayaai.exe` built.

### Implemented
- Chat: streaming, Stop, Retry, persona switch, history persistence
- Voice: STT, TTS, clap wake, name wake, Voice page
- PC control: 15 actions + confirm dialog for risky ones
- Monitoring: CPU/RAM/GPU/NPU/battery/disks/uptime cards
- English Teacher: vocabulary, grammar, pronunciation, idioms
- Security: PIN (PBKDF2, local store), Windows Hello, voiceprint, lock screen
- Settings: YAML + backups, theme, tray behaviour, phone server control
- Phone server: Start/Stop/PIN from Settings; headless mode
- Tray: close-to-tray, minimize-to-tray, start-minimized

### Run (packaged)

```
Desktop\Maya AI.lnk   ->   dist\mayaai.exe
```

The exe locates `MAYA AI\` from its own folder (or `MAYA_AI_HOME`), so the
shortcut works without setting any environment variable. See
`docs\WINDOWS-APP.md` for the resolution order.

### Run

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m app            # GUI
.\.venv\Scripts\python.exe -m app --tray     # start in tray
.\.venv\Scripts\python.exe -m app --headless # phone server only
```

### Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```

## Internet (WAN) remote — Tailscale

LAN/hotspot/USB control works today. For control over the Internet, use
**Tailscale** (recommended in `docs/WAN-REMOTE-DESIGN.md`). It gives the laptop a
stable private IP and WireGuard encryption with no relay to run.

1. Install Tailscale on the laptop and the phone; sign in to the same tailnet
   (<https://tailscale.com>).
2. Find the laptop's Tailscale IP (e.g. `100.x.y.z`).
3. Set it in `MAYA AI\config\settings.yaml`:
   ```yaml
   server:
     wan:
       enabled: true
       host: "100.x.y.z"     # advertised to the phone in /health
   ```
4. Start the phone server, then pair once over LAN. The phone can now use the
   Tailscale IP as the laptop host; all existing endpoints work unchanged.

The custom relay path (`relay_url` + TLS `cert_path`/`key_path`) is a skeleton:
no relay is deployed and WAN TLS ACME is not implemented. Keep `mode: lan` and
`enabled: false` unless you are running your own relay. `/health` reports
`capabilities: [..., "wan"]` and `wan_host` when WAN is enabled.

## Requirements / Modes (from `docs\REQUIREMENTS.md`)

Windows app must support (parity target):
- **AI MODE** — voice + text commands, open/close apps, file/folder creation, code write/run, file management, permission-gated actions.
- **REMOTE MODE** — live screen view, mouse + keyboard control, app open/close, file view/transfer, remote control over Wi-Fi/Hotspot/Internet, Bluetooth nearby device contact.
- **HYBRID MODE** — direct user control + AI autonomous work simultaneously; no control conflicts; user takeover on demand.

### Mode status (Windows)
- AI MODE: ✅ Partial (chat, voice, PC control, monitoring, teacher, security, settings).
- REMOTE MODE: ⚠️ Partial (phone server + screen share + PC actions).
- HYBRID MODE: ❌ Not started.
- Connection Manager: ⚠️ Partial (phone server). Shared module: `JARVIS\custom\tools\connection_manager.py`.
- Dual-boot awareness: ⚠️ Partial (server advertises OS).

## Existing files (keep)

- `app\maya_tray.py` — legacy tray (fallback)
- `app\autostart.ps1` — old autostart
- `app\install_autostart.ps1` — updated autostart

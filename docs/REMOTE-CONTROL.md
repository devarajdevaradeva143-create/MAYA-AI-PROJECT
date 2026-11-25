# MAYA AI — Remote Control & HYBRID mode (phone → laptop)

> Status: implemented 19 Nov 2026. Windows laptop + Android phone.
> Wire contract: `docs/API-CONTRACT.md` §9A / §9B.

## What it does

| Feature | Where |
|---|---|
| Live laptop screen (JPEG, ~1–2 fps) | Phone → Laptop → **Screen** |
| Tap / long-press / drag / scroll / type | Same screen |
| File browse + download + upload (allowed folders) | Phone → Laptop → **Files** |
| User ⇄ AI control bus (takeover / release) | Laptop screen card + `GET /hybrid/status` |
| Confirmation before remote access | Phone dialog on **Start session** |

HYBRID rule: **user always wins**. Starting a remote session takes control away
from AI; stopping it releases control. AI cannot acquire control while the user
holds it.

## How to use

1. Phone and laptop on the same Wi-Fi/hotspot; phone paired (PIN).
2. Settings → Operating mode → **REMOTE** (or **HYBRID**).
3. Laptop tab → **Screen** → **Start session** → **Allow**.
4. Screen appears. Tap = click, long-press = right-click, drag = move,
   scroll buttons = wheel, keyboard field = type text.
5. **Files** → browse allowed folders, download (SAF) or upload (25 MB max).
6. **Stop session** ends screen/input/files immediately.

The session expires after **5 minutes of inactivity**; every screen/input/file
call extends it. Server restart drops all sessions.

## Security rules

- Session token is created only after the owner confirms on the phone.
- Token is bound to one paired device and kept in memory only (never logged,
  never written to disk).
- Screen, input, and files all require the same live session.
- Files are limited to `permissions.allowed_roots`; system folders and `..`
  traversal are blocked.
- Uploads are capped at 25 MB, downloads at 50 MB, and written atomically.
- LAN HTTP only in v1 (no TLS). Do not expose port 8420 to the Internet.
- Instant disconnect: **Stop session**, or revoke the phone under
  `GET /pair/devices` / the laptop UI.

## Limits (honest)

- Frame rate is adaptive polling (~1–2 fps); this is not a low-latency game
  stream.
- Keyboard supports the allowlist in the contract; arbitrary shortcuts use
  the text field.
- Screen capture uses Pillow (Windows only).
- AI task execution inside HYBRID is still laptop-side chat; the phone shows
  the control bus and can take over.
- Internet (WAN) remote control needs a relay/TLS design; use LAN/hotspot/USB
  in v1.

## Laptop → phone control (v0.2)

The reverse direction uses the phone's own server on **port 8421** (enabled in
phone **Settings → Phone remote**). The laptop remembers the phone's last LAN IP
(`last_ip`) after the first authenticated request, so **Phone Remote** can start
a session without asking for the address again.

1. Phone: enable **Settings → Phone remote** and the **Maya AI** accessibility
   service (system Settings → Accessibility).
2. Laptop: **Phone Remote** page → **Start session** → **Allow**.
3. Tap/keys/text are injected through the accessibility service; **Stop session**
   ends it.

Current gap: the phone screen preview needs Android **MediaProjection**
permission. Input control, session start/stop, and file APIs work; the laptop
window stays blank until a screen-sharing consent screen is added to the phone
app. Phone remote also stops when Android unbinds the accessibility service
(e.g. after an app reinstall — re-enable it once).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Switch to REMOTE or HYBRID" | Settings → Operating mode |
| "Remote session expired" | Start session again |
| "Screen capture unavailable" | Laptop is not Windows, or Pillow missing |
| Files empty | Check `permissions.allowed_roots` in `MAYA AI\config\settings.yaml` |
| Upload fails | Parent folder must exist; file ≤ 25 MB |
| Phone cannot connect | Same network + laptop server running + private IP |

# MAYA AI — Laptop ↔ Phone API Contract (v1)

> Ithu **single source of truth** — phone app + laptop server rendum ithai follow pannanum.
> Vera AI code pannum bothu ithai first padikkum.
> Simple Thanglish-la ezhuthirukken.

**Status:** Design locked (v1) — implementation innum illa.
**Owner files:**
- Server: `JARVIS\custom\server\` (Windows + Fedora share)
- Client: `MOBILE APP\app\src\main\java\com\devaraj\maya\data\remote\`
- Plans: `MOBILE APPLICATION\PLAN.md`, `WINDOWS APPLICATION\windows\PLAN.md`

---

## 0. Hard rules

1. **LAN only.** No internet, no cloud relay, no public IP.
2. Server binds `0.0.0.0:8420` aana **private IP mattum accept pannum**
   (10/8, 172.16/12, 192.168/16, 169.254/16, 127.0.0.1). Public source IP → reject `403`.
3. Phone-la irundhu **Gemini / cloud AI-ku call illa** ❌
4. Offline → online data flow **illa** ❌
5. Pairing illama auth-required endpoint call panna koodadhu.
6. Chat content server-la **store pannaadhu** — phone-la mattum history.
7. API change = **additive only**. Existing field name/type change panna koodadhu.
8. Ellam JSON UTF-8, field names `snake_case`.
9. Timestamps = Unix seconds (integer), unless noted.
10. Error format always same envelope (section 3).

---

## 1. Basics

| Item | Value |
|---|---|
| Base URL | `http://<laptop-ip>:8420/api/v1` |
| Protocol | HTTP/1.1 + WebSocket |
| Default port | `8420` |
| WS base | `ws://<laptop-ip>:8420/api/v1/ws/...` |
| JSON body limit | 1 MB |
| Audio upload limit | 5 MB |
| Server | Python FastAPI + uvicorn |
| Client | Kotlin + OkHttp |

**No TLS in v1.** Threat model = trusted home LAN. TLS + certificate pinning future-la.

`GET /health` mattum unauthenticated (phone laptop-ah kandupidikka).

---

## 2. Auth

### 2.1 Token

- Format: `maya_<43 chars urlsafe>` (opaque).
- Server stores **SHA-256(token)** mattum — plain token never disk-la.
- Header: `Authorization: Bearer <token>`
- TTL: `server.token_ttl_hours` (default **720 h = 30 days**).
- Refresh: TTL 7 days-ku kammi aanaa `POST /pair/refresh`.
- Revoke: phone-lum laptop UI-lum possible.
- Token device-ku bind aagum. Device revoke aanaa → `401 / 1007`.

### 2.2 Pairing — PIN flow

1. Laptop UI-la **Pair Phone** open → 6-digit PIN generate (TTL **120 s**, memory only).
2. Phone → `POST /pair/claim` with `pin`, `device_id`, `device_name`.
3. Server PIN verify (constant time), 5 attempts max → 10 min lockout.
4. Success → device record create + token return.
5. Phone secure storage-la token save (Android Keystore AES-GCM).

### 2.3 Pairing — QR flow

Laptop QR payload (JSON, 120 s, single-use):

```json
{
  "v": 1,
  "h": "192.168.1.5",
  "p": 8420,
  "t": "<32-byte hex one-time token>",
  "n": "Devaraj-Laptop"
}
```

- QR token server-la **hash**-ah mattum store, single use.
- Phone scan → `POST /pair/qr/claim`.
- Expired / used → `1004`.

### 2.4 Auto-connect (optional)

- User setting. Default **off**.
- Enable = stored valid token irundhaa app auto-connect pannum (prompt illa).
- Token invalid → pairing screen-ku pogum.
- "Auto-connect without pairing" **never** allowed.

### 2.5 Pairing rules

| Rule | Value |
|---|---|
| PIN length | 6 digits |
| PIN TTL | 120 s |
| PIN attempts | 5 |
| Lockout | 10 min |
| QR TTL | 120 s, single use |
| Max paired devices | 8 |
| Token TTL | 30 days |

---

## 3. Errors

```json
{
  "error": {
    "code": 1003,
    "message": "Invalid PIN",
    "details": null
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| 1001 | 401 | Missing / invalid token |
| 1003 | 401 | Wrong PIN |
| 1004 | 401 | PIN / QR expired or used |
| 1005 | 429 | Rate limited / locked out |
| 1006 | 401 | Token expired |
| 1007 | 401 | Device revoked |
| 2001 | 400 | Bad request / validation |
| 2002 | 400 | Unsupported action |
| 2003 | 413 | Payload too large |
| 2004 | 404 | Not found |
| 3001 | 503 | Engine unavailable (laptop model down) |
| 3002 | 504 | Engine timeout |
| 3003 | 503 | STT unavailable |
| 3004 | 503 | TTS unavailable |
| 4002 | 403 | Permission denied |
| 4003 | 403 | Action blocked (dangerous) |
| 5000 | 500 | Internal error |

Error message = English, user-safe. Stack trace / path ellam client-ku anuppaadhu.

---

## 4. Endpoints — overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | ❌ | Server alive + capabilities |
| POST | `/pair/claim` | ❌ | PIN pairing |
| POST | `/pair/qr/claim` | ❌ | QR pairing |
| POST | `/pair/refresh` | ✅ | Token refresh |
| GET | `/pair/devices` | ✅ | Paired device list |
| DELETE | `/pair/devices/{device_id}` | ✅ | Revoke device |
| POST | `/chat` | ✅ | Non-streaming chat |
| WS | `/ws/chat` | ✅ | Streaming chat |
| POST | `/voice/stt` | ✅ | Audio → text |
| POST | `/voice/tts` | ✅ | Text → audio (WAV) |
| GET | `/voice/status` | ✅ | TTS/STT engines |
| GET | `/pc/status` | ✅ | CPU / RAM / GPU / battery / disk |
| POST | `/pc/command` | ✅ | Laptop action request |
| POST | `/pc/confirm` | ✅ | Execute confirmed action |
| POST | `/pc/cancel` | ✅ | Discard pending action |
| POST | `/pc/remote/start` | ✅ | Confirm + open a remote-control session |
| POST | `/pc/remote/stop` | ✅ | Close the remote-control session |
| GET | `/pc/remote/status` | ✅ | Session state |
| GET | `/pc/screen` | ✅ + session | Live screen frame (JPEG/PNG) |
| POST | `/pc/input` | ✅ + session | Mouse / keyboard events |
| GET | `/pc/files/roots` | ✅ + session | Allowed folders |
| GET | `/pc/files/list` | ✅ + session | Folder listing |
| GET | `/pc/files/download` | ✅ + session | File download (binary) |
| PUT | `/pc/files/upload` | ✅ + session | File upload (raw body) |
| GET | `/hybrid/status` | ✅ | HYBRID controller + AI tasks |
| POST | `/hybrid/takeover` | ✅ | User takes control (AI yields) |
| POST | `/hybrid/release` | ✅ | Release user control |
| GET | `/wake/status` | ✅ | Wake listener state |
| POST | `/wake/listen` | ✅ | Start 60 s wake listen |
| POST | `/wake/stop` | ✅ | Stop wake listen |
| WS | `/ws/events` | ✅ | Live status + events |

---

## 5. Health

### `GET /api/v1/health`

No auth. Personal data illa.

```json
{
  "status": "ok",
  "app": "maya-laptop",
  "version": "0.1.0",
  "api": 1,
  "platform": "windows",
  "model": "qwen3-3b",
  "engine": "lemonade",
  "capabilities": [
    "chat",
    "chat_stream",
    "voice_stt",
    "voice_tts",
    "pc_control",
    "file_transfer",
    "wake",
    "monitor",
    "screen",
    "remote_input",
    "hybrid"
  ],
  "paired_devices": 1,
  "uptime_s": 360
}
```

---

## 6. Pairing endpoints

### `POST /pair/claim`

```json
{
  "device_id": "android-id-32-hex",
  "device_name": "Devaraj Phone",
  "pin": "482913",
  "app_version": "0.1.0",
  "api": 1
}
```

Success `200`:

```json
{
  "token": "maya_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "expires_at": 1767000000,
  "laptop_name": "Devaraj-Laptop",
  "api": 1,
  "host": "192.168.1.5",
  "port": 8420
}
```

### `POST /pair/qr/claim`

```json
{
  "qr_token": "a1b2c3...",
  "device_id": "android-id-32-hex",
  "device_name": "Devaraj Phone",
  "app_version": "0.1.0",
  "api": 1
}
```

Response = same as PIN success.

### `POST /pair/refresh`

Auth header with current token.

```json
{ "device_id": "android-id-32-hex" }
```

→ `{ "token": "...", "expires_at": 1767000000 }`

### `GET /pair/devices`

```json
{
  "devices": [
    {
      "device_id": "android-id-32-hex",
      "name": "Devaraj Phone",
      "paired_at": 1760000000,
      "last_seen": 1760100000,
      "current": true
    }
  ]
}
```

### `DELETE /pair/devices/{device_id}`

→ `{ "revoked": true }`

Current device-ah revoke panna client token-ah delete pannum.

---

## 7. Chat

Server stateless. History phone-la. Client last **24 messages** mattum anuppum.

### `POST /chat`

```json
{
  "conversation_id": "c_01JABCDEF",
  "persona": "maya",
  "messages": [
    { "role": "user", "content": "enna panra?" },
    { "role": "assistant", "content": "Un pakkathula dhaan da 😊" },
    { "role": "user", "content": "time enna?" }
  ]
}
```

Rules:
- `role` = `user` | `assistant` mattum. `system` reject (`2001`).
- Max messages 24, total chars 12 000.
- Server persona system prompt-ah prepend pannum. Client system prompt anuppa koodadhu.
- `persona`: `maya` | `teacher`. Default `maya`.

Success:

```json
{
  "conversation_id": "c_01JABCDEF",
  "reply": "Ippo 7:42 PM da.",
  "model": "qwen3-3b",
  "engine": "lemonade",
  "elapsed_ms": 1830,
  "pending_action": null
}
```

`pending_action` (future tool use):

```json
{
  "confirm_token": "cf_...",
  "description": "Open Notepad",
  "action": "app.open",
  "expires_in": 60
}
```

Client `POST /pc/confirm` call pannum (section 9.3).

### `WS /ws/chat?token=<token>`

Client → server:

```json
{
  "type": "user",
  "conversation_id": "c_01JABCDEF",
  "persona": "maya",
  "messages": [{ "role": "user", "content": "Hi" }]
}
```

Server → client:

```json
{ "type": "start", "conversation_id": "c_01JABCDEF", "model": "qwen3-3b" }
{ "type": "token", "text": "Van" }
{ "type": "token", "text": "akkam" }
{ "type": "done", "elapsed_ms": 1830, "tokens": 42, "pending_action": null }
```

Error:

```json
{ "type": "error", "code": 3001, "message": "Engine unavailable" }
```

Rules:
- `ping` / `pong` every 25 s.
- Client disconnect → server generation cancel.
- Client reconnect → new request (resume illa in v1).
- One active generation per connection.

---

## 8. Voice

### `POST /voice/stt`

`multipart/form-data`:

| Field | Type | Notes |
|---|---|---|
| `audio` | file | WAV, PCM 16-bit, mono, 16 kHz |
| `lang` | text | `en` / `en-in` / `ta` |
| `duration_ms` | text | Optional |

Limits: 30 s, 5 MB.

```json
{ "text": "enna time", "lang": "en-in", "engine": "vosk" }
```

Silence → `{ "text": "", "lang": "en-in" }` (error illa).

### `POST /voice/tts`

```json
{
  "text": "Sollu da, enna venum?",
  "engine": "sapi",
  "voice": "heera",
  "lang": "en",
  "speed": 1.0
}
```

- `engine`: `sapi` | `piper` | `auto`
- `text` max 1 000 chars
- Response: `audio/wav` binary (22 050 Hz mono)
- Unavailable → `3004`

### `GET /voice/status`

```json
{
  "stt": { "engine": "vosk", "available": true, "languages": ["en", "en-in"] },
  "tts": {
    "engine": "sapi",
    "available": true,
    "voices": ["heera", "neerja", "zira"],
    "piper": { "available": false, "voices": [] }
  }
}
```

---

## 9. Laptop control

### 9.1 `GET /pc/status`

```json
{
  "ts": 1760100000,
  "cpu": { "percent": 12.5, "cores": 8, "freq_mhz": 3200 },
  "ram": { "total_gb": 15.3, "used_gb": 7.1, "percent": 46.4 },
  "gpu": { "name": "AMD Radeon 840M", "percent": null },
  "npu": { "name": "AMD XDNA", "tops": 50, "percent": null },
  "battery": { "percent": 82, "plugged": true, "seconds_left": null },
  "temps": { "cpu_c": 48.0 },
  "disks": [
    { "mount": "C:\\", "total_gb": 476.0, "used_gb": 210.0, "percent": 44.1 }
  ],
  "uptime_s": 12345
}
```

Unknown value = `null`. Client "—" kaattum.

### 9.2 `POST /pc/command`

```json
{
  "action": "app.open",
  "params": { "name": "notepad" },
  "confirm_token": null
}
```

Three possible responses:

**Done:**
```json
{ "status": "done", "result": { "message": "Opened notepad" } }
```

**Confirmation needed:**
```json
{
  "status": "needs_confirmation",
  "confirm_token": "cf_9f2...",
  "description": "Open application: notepad",
  "expires_in": 60
}
```

**Denied / blocked:**
```json
{ "status": "denied", "reason": "Action not allowed" }
```

### 9.3 `POST /pc/confirm`

```json
{ "confirm_token": "cf_9f2..." }
```

→ executes stored action → `{ "status": "done", "result": { ... } }`

Token single-use, 60 s, exact action + params-ku bind.

### 9.4 `POST /pc/cancel`

```json
{ "confirm_token": "cf_9f2..." }
```

→ `{ "status": "cancelled" }`

### 9.5 Action catalog

| Action | Params | Default permission | Notes |
|---|---|---|---|
| `app.list` | – | allow | Installed apps |
| `process.list` | – | allow | Running apps |
| `app.open` | `name` | ask | |
| `app.close` | `name` | ask | |
| `file.read` | `path` | allow* | *allowed roots only |
| `dir.list` | `path` | allow* | *allowed roots only |
| `file.write` | `path`, `content` | ask | max 256 KB |
| `file.delete` | `path`, `recursive` | ask | recycle bin prefer |
| `cmd.run` | `command`, `cwd` | ask | denylist check |
| `system.lock` | – | ask | |
| `system.sleep` | – | ask | |
| `system.shutdown` | `delay_s` (10–120) | ask | countdown + cancel |
| `system.volume` | `level` 0–100 | ask | |
| `system.mute` | `mute` bool | ask | |
| `system.screenshot` | `save_path` | ask | |
| `media.play` / `media.pause` / `media.next` / `media.prev` | – | ask | media keys |
| `clipboard.get` | – | ask | |
| `clipboard.set` | `text` | ask | max 64 KB |
| `notify` | `title`, `body` | allow | toast only |
| `whatsapp.message` | `number`, `text` | ask | opens WhatsApp prefilled; user presses Send. max 4 KB |

**Allowed roots** (settings `permissions.allowed_roots`):
project root, Desktop, Documents, Downloads. System folders (`C:\Windows`, `C:\Program Files`, `AppData`) deny.

**`cmd.run` always blocked** (4003):
`format`, `diskpart`, `bcdedit`, `vssadmin delete`, `cipher /w`, `takeown /f C:\`, `icacls C:\ /reset`, `netsh advfirewall off`, `Set-MpPreference`, `net user`, `reg delete HKLM`, `del /f /s C:\`, `rm -rf /`, `Remove-Item -Recurse C:\`.

Path rules:
- Resolve absolute path, `..` reject.
- Symlink / junction target re-check.
- Denied root → `4002`.

Rate limit: 30 PC commands / min per device.

---

## 9A. Remote control (REMOTE / HYBRID mode)

A **remote session** is a short-lived capability token created only after the
owner confirms on the phone. It gates screen view, input, and file transfer so
the normal `/pc/command` confirmation is not repeated for every mouse event.
The session dies after **5 minutes of inactivity**, on `remote/stop`, or on
server restart.

### `POST /pc/remote/start`

First call (no token) → permission prompt:

```json
{
  "status": "needs_confirmation",
  "confirm_token": "cf_xxxxxxxx",
  "description": "Allow remote screen and input from this phone?",
  "expires_in": 60
}
```

Second call with `{"confirm_token": "cf_xxxxxxxx"}`:

```json
{
  "status": "done",
  "session_token": "s_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "expires_in": 300
}
```

### `POST /pc/remote/stop`

```json
{ "session_token": "s_..." }
```

`{ "status": "done", "active": false, "expires_in": 0 }` — idempotent.
Only a valid session token for the calling device releases HYBRID control.

Only **one** remote session exists at a time: starting one on any paired device
drops the previous session.

### `GET /pc/remote/status?session_token=...`

```json
{ "active": true, "expires_in": 287 }
```

### `GET /pc/screen?session_token=...&max_width=1280&quality=60`

Returns `image/jpeg` binary. `max_width` 320–1920, `quality` 30–85.
`X-Maya-Width` / `X-Maya-Height` headers carry the real frame size.
Poll at most **2 fps**. No auth token + session → `4002`.

### `POST /pc/input`

```json
{
  "session_token": "s_...",
  "events": [
    { "type": "move", "x": 0.42, "y": 0.73 },
    { "type": "click", "button": "left" },
    { "type": "scroll", "dy": -3 },
    { "type": "text", "text": "hello" },
    { "type": "key", "key": "enter" }
  ]
}
```

- `x`, `y` are **normalized 0.0–1.0** (phone maps the displayed image).
- 1–32 events per call. `text` max 500 chars. `dy` −10..10.
- `button`: `left`, `right`, `middle`.
- `key` allowlist: `enter`, `tab`, `esc`, `backspace`, `delete`, `space`,
  `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`,
  `ctrl+a`, `ctrl+c`, `ctrl+v`, `ctrl+x`, `ctrl+z`, `alt+tab`, `f5`.
- Response `{ "status": "done", "applied": 2 }`.
- Rate limit: 600 events-requests / min per device (client throttles ~10/s).

### `GET /pc/files/roots`

```json
{ "roots": ["C:\\Users\\devar\\Desktop"] }
```

### `GET /pc/files/list?session_token=...&path=C:\\Users\\...`

```json
{
  "path": "C:\\Users\\devar\\Desktop",
  "entries": [
    { "name": "notes", "path": "C:\\Users\\devar\\Desktop\\notes", "is_dir": true, "size": null },
    { "name": "todo.txt", "path": "C:\\Users\\devar\\Desktop\\todo.txt", "is_dir": false, "size": 412 }
  ]
}
```

### `GET /pc/files/download?session_token=...&path=...`

Binary stream, `Content-Disposition: attachment`, 50 MB cap, allowed roots
only. System folders denied.

### `PUT /pc/files/upload?session_token=...&path=...`

Raw request body (not multipart). 25 MB cap. Parent folder must already exist
and be inside an allowed root. Existing file is replaced atomically.

```json
{ "status": "done", "path": "C:\\...\\todo.txt", "size": 412 }
```

---

## 9B. HYBRID mode

HYBRID mode guarantees **user > AI**: a user takeover instantly pauses/cancels
AI work, and AI cannot acquire control while the user holds it.

### `GET /hybrid/status`

```json
{
  "controller": "user",
  "ai_busy": false,
  "queued_tasks": 1,
  "running_task": null,
  "conflicts": 2,
  "last_takeover": 1760100000,
  "uptime_s": 420,
  "tasks": [
    { "id": "t_ab12cd34", "description": "Summarise notes", "status": "queued" }
  ]
}
```

### `POST /hybrid/takeover` → `{ "status": "done", "controller": "user" }`

### `POST /hybrid/release` → `{ "status": "done", "controller": "none" }`

Starting a remote session auto-takes over (`controller=user`); stopping it
releases control. AI task execution itself stays on the laptop.

---

## 9C. Phone remote (laptop controls phone)

**New in v1.1** — Laptop initiates control session on paired phone.

### Flow

1. Laptop UI → `POST /phone/remote/start` (auth: paired phone token)
2. Phone shows **confirmation dialog** (user must Allow)
3. Phone returns `session_token` + `ws_url` for screen stream
4. Laptop connects WebSocket → receives JPEG frames
5. Laptop sends input events via `POST /phone/remote/input` or WS
6. Either side can stop: `POST /phone/remote/stop` or phone notification

### Endpoints (on PHONE server)

Phone runs a minimal HTTP server on port **8421** (LAN only) when "Allow laptop control" is enabled.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/phone/remote/start` | Paired token | Start session, returns `{session_token, ws_url, expires_in}` |
| POST | `/phone/remote/stop` | Session token | Stop session |
| GET | `/phone/remote/status` | Session token | `{active, expires_in, controller}` |
| POST | `/phone/remote/input` | Session token | Inject input events |
| WS | `/phone/remote/ws?token=<session_token>` | Session token | Binary JPEG frames (server→client) + input ack (client→server) |
| GET | `/phone/remote/screen` | Session token | MJPEG stream (fallback) |
| POST | `/phone/remote/files/list` | Session token | List files in allowed root |
| GET | `/phone/remote/files/download` | Session token | Download file |
| POST | `/phone/remote/files/upload` | Session token | Upload file |

### `POST /phone/remote/start`

**Request:**
```json
{ "max_width": 1280, "quality": 60, "fps": 10 }
```

**Response (200):**
```json
{
  "session_token": "maya_<43 chars>",
  "ws_url": "ws://<phone-ip>:8421/phone/remote/ws?token=...",
  "expires_in": 300,
  "screen": { "width": 1080, "height": 2400, "density": 3.0 }
}
```

**Errors:**
- `409` — session already active
- `403` — "Allow laptop control" disabled in phone settings
- `400` — invalid params

### `POST /phone/remote/input`

**Request:**
```json
{
  "session_token": "...",
  "events": [
    { "type": "move", "x": 0.5, "y": 0.3 },
    { "type": "click", "button": "left" },
    { "type": "scroll", "dy": -3 },
    { "type": "text", "text": "hello" },
    { "type": "key", "key": "back" },
    { "type": "key", "key": "home" },
    { "type": "key", "key": "recents" }
  ]
}
```

**Response:** `{ "applied": 3 }`

**Errors:** `401` (invalid/expired token), `403` (secure window), `400` (bad event)

### WebSocket `/phone/remote/ws`

**Server → Client (binary frames):**
- Each frame = JPEG image (Content-Type not sent, binary only)
- Frame rate ≤ requested `fps`
- Phone sends frames only when screen content changes

**Client → Server (JSON text):**
```json
{ "type": "input", "events": [...] }  // same as POST /input
{ "type": "ping" }
```

**Server → Client (JSON text, occasional):**
```json
{ "type": "screen_info", "width": 1080, "height": 2400, "density": 3.0 }
{ "type": "error", "message": "secure window" }
{ "type": "pong" }
```

### File operations

Allowed roots = user-selected folders via SAF (persisted URI permissions).

**List:**
```
POST /phone/remote/files/list
{ "session_token": "...", "path": "/Documents" }
→ { "path": "...", "entries": [{ "name": "file.txt", "is_dir": false, "size": 1234 }] }
```

**Download:**
```
GET /phone/remote/files/download?session_token=...&path=/Documents/file.txt
→ file stream (octet-stream)
```

**Upload:**
```
POST /phone/remote/files/upload
multipart: session_token, path=/Documents/, file=<bytes>
→ { "size": 1234 }
```

### Session rules

- Max 1 active session per paired laptop
- TTL: 5 min (sliding, reset on activity)
- Phone shows persistent notification "Remote control active — Tap to stop"
- Secure windows (banking, password fields) → input rejected, error sent
- Phone user can stop anytime via notification or Settings

### Rate limits

| Scope | Limit |
|---|---|
| `/phone/remote/start` | 2 / min |
| `/phone/remote/input` | 600 / min |
| `/phone/remote/ws` | 1 concurrent |
| `/phone/remote/files/*` | 30 / min |

---

## 10. Events WebSocket

### `WS /ws/events?token=<token>`

Server → client every **2 s** (only while connected):

```json
{ "type": "status", "data": { "...": "same schema as /pc/status" } }
```

Other events:

```json
{ "type": "wake", "state": "listening" }
{ "type": "wake", "state": "idle" }
{ "type": "notification", "title": "Reminder", "body": "Drink water" }
{ "type": "server", "state": "shutting_down" }
{ "type": "ping", "ts": 1760100000 }
```

Client → server `{"type":"pong"}` optional.

Rules:
- Phone screen off / app background → socket close (battery).
- Reconnect backoff: 1, 2, 4, 8, 16, 30 s (cap).

---

## 11. Wake endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/wake/status` | – | `{ "listening": false, "clap": true, "name": true }` |
| POST | `/wake/listen` | `{ "seconds": 60 }` | `{ "listening": true, "expires_at": ... }` |
| POST | `/wake/stop` | – | `{ "listening": false }` |

`seconds` max 300. Server wake listener start pannum; wake aanaa events WS-la `wake` + desktop chat open.

---

## 12. Rate limits

| Scope | Limit | Lockout |
|---|---|---|
| Pair claim (per IP + device_id) | 5 / 10 min | 10 min |
| Auth failures | 10 / min | 1 min |
| General authenticated | 120 / min | 1 min |
| `/chat` | 20 / min | – |
| `/voice/stt` | 10 / min | – |
| `/pc/command` | 30 / min | – |
| `/pc/screen` | 120 / min | – |
| `/pc/input` | 600 / min | – |
| `/pc/files/*` | 120 / min | – |
| `/wake/listen` | 5 / min | – |

Exceed → `429 / 1005`.

---

## 13. Confirm token lifecycle

1. `POST /pc/command` → permission `ask` → token create (60 s).
2. Client user-ku dialog kaattum.
3. Approve → `POST /pc/confirm` → execute → token delete.
4. Cancel / timeout → token delete, action never execute.
5. Token single-use. Replay → `4002`.

Confirm token store = server memory only. Server restart → pending actions cancel (safe default).

---

## 14. Compatibility

- `api: 1` — breaking change = `api: 2` + new base path `/api/v2`.
- New field add = old client ignore pannum.
- New endpoint add = old client use pannaadhu.
- Enum values extend aagalam; existing value remove koodadhu.
- `capabilities` list check pannitu client feature show pannum.

---

## 15. Implementation split

### Laptop (Python)

```
JARVIS\custom\server\
├─ __init__.py
├─ app.py            ← create_app(services)
├─ contracts.py      ← Protocol interfaces (Engine, Voice, Pc, Monitor, Pairing, Wake)
├─ models.py         ← Pydantic request/response
├─ auth.py           ← token store, hashing, rate limit
├─ pair.py           ← PIN / QR sessions
├─ confirm.py        ← confirm tokens
├─ lan.py            ← private IP guard
├─ routes\
│  ├─ health.py
│  ├─ pair.py
│  ├─ chat.py
│  ├─ voice.py
│  ├─ pc.py
│  ├─ remote.py       ← remote session + screen + input + files
│  ├─ hybrid.py       ← HYBRID control bus
│  ├─ wake.py
│  └─ events.py
└─ ws.py
```

Server **headless** — PySide6 import panna koodadhu. UI callbacks `contracts.py` Protocol moolam.

### Phone (Kotlin)

```
data\remote\
├─ ApiClient.kt
├─ MayaApi.kt
├─ Dto.kt
├─ ChatSocket.kt
├─ EventsSocket.kt
├─ DiscoveryClient.kt
├─ PrivateNetworkInterceptor.kt
└─ ErrorMapper.kt
```

---

## 16. Security checklist (implementation time)

- [ ] Token plain text disk-la illa (hash only)
- [ ] PIN constant-time compare
- [ ] PIN attempts + lockout
- [ ] QR single-use + TTL
- [ ] Revoked device → immediate 401
- [ ] Private IP guard
- [ ] Confirm token single-use + TTL
- [ ] Remote session confirm + device-bound + 5 min sliding TTL
- [ ] Screen/input/files all require the live session
- [ ] Path traversal + symlink guard
- [ ] Command denylist
- [ ] Rate limits
- [ ] No personal data in logs
- [ ] No cloud calls
- [ ] `DEVARAJ\` folder never served
- [ ] `.env` never served
- [ ] Server error detail client-ku illa

---

## 17. Changelog

| Version | Date | Change |
|---|---|---|
| v1 | 2026-11-17 | Initial contract — pairing, chat, voice, PC control, events, wake |
| v1.1 | 2026-11-19 | Additive: remote session + screen + input + file transfer + hybrid status/takeover |
| v1.2 | 2026-11-19 | Additive: WAN remote capability (`wan_host`, `wan` capability) — design only |

---

## 18. WAN remote (design only)

Internet remote control is **not enabled by default**. When configured, the
laptop advertises a stable address and TLS is mandatory.

### `GET /health` additions

```json
{
  "capabilities": ["chat", "...", "wan"],
  "wan_host": "100.x.y.z"
}
```

- `wan` appears in `capabilities` only when `server.wan.enabled` is true.
- `wan_host` is the stable address (Tailscale IP / relay address) or `null`.

### Rules

- WAN transport is TLS only; cleartext HTTP is refused.
- The same pairing token is required; WAN does not weaken auth.
- Relay (if used) only tunnels framed bytes; it cannot read control payloads.
- Config: `server.wan.enabled`, `server.wan.relay_url`, `server.wan.mode`
  (`lan` | `wan`), `server.wan.cert_path`, `server.wan.key_path`.
- Design: `docs/WAN-REMOTE-DESIGN.md`.

> Implementation status: `wan_relay.py` + `tls.py` are compilable skeletons.
> No relay is deployed and no certs are provisioned.

---

## 19. Bluetooth PAN remote (design)

Bluetooth Personal Area Network (PAN) enables remote control over Bluetooth without WiFi.

### Architecture

```
Phone (PANU) ←→ Laptop (NAP/GN) via Bluetooth PAN
```

- Phone acts as PANU (PAN User) — provides network via Bluetooth
- Laptop acts as NAP (Network Access Point) — connects to phone PAN
- IP assignment: DHCP or link-local (169.254.x.x)
- Fallback: RFCOMM (Serial Port Profile) for legacy devices

### Connection Flow

1. **Pairing:** Phone + laptop pair via Bluetooth settings (OS-level)
2. **PAN activation:** Phone enables Bluetooth tethering / PAN server
3. **Laptop connects:** `BluetoothAdapter` discovers phone → connects to PAN
4. **IP assignment:** Phone DHCP server assigns IP to laptop (or static link-local)
5. **API access:** Laptop uses phone IP (e.g., 192.168.44.1) for API calls

### Endpoints (same as LAN, different transport)

All existing endpoints work over Bluetooth PAN:
- `GET /api/v1/health` → health check
- `POST /api/v1/pc/command` → laptop control
- `WS /api/v1/ws/events` → monitor events
- `POST /phone/remote/start` → phone remote (laptop controls phone)

### Config (settings.yaml)

```yaml
bluetooth:
  enabled: false
  mode: pan          # pan | rfcomm
  pan_role: nap      # nap (laptop) | panu (phone)
  auto_connect: false
```

### Security

- OS-level Bluetooth pairing required (PIN/confirmation)
- PAN traffic encrypted by Bluetooth link layer
- Same API token auth required after connection

### Rate limits (same as LAN)

| Scope | Limit |
|---|---|
| `/pc/command` | 30 / min |
| `/pc/screen` | 120 / min |
| `/pc/input` | 600 / min |

---

## 20. Internet/WAN Remote Control (full spec)

Complete internet remote via self-hosted relay + TLS.

### Architecture

```
Phone ←→ Relay Server ←→ Laptop
   WS/TLS        WS/TLS
```

### Components

| Component | Role | Protocol |
|---|---|---|
| **Phone** | Client | WebSocket Secure (WSS) |
| **Relay** | Broker | WSS + TLS termination |
| **Laptop** | Server | WSS + TLS |

### Relay Server Spec

- **Port:** 443 (HTTPS) or custom (e.g., 8443)
- **Protocol:** WebSocket Secure (WSS) with TLS 1.3
- **Auth:** Token-based (reuse pairing token)
- **Routing:** Phone device_id → Laptop device_id mapping
- **Frame format:** JSON messages + binary frames (for screen)
- **Rate limit:** Per-device, per-IP

### Phone → Relay Connection

```
WSS: wss://relay.example.com:443/wan/phone?token=<pairing_token>
```

**Messages:**
```json
// Phone → Relay (register)
{ "type": "register", "device_id": "...", "capabilities": ["phone_remote"] }

// Relay → Phone (ack)
{ "type": "registered", "wan_id": "wan_..." }

// Phone → Relay (screen frame)
{ "type": "screen", "data": "<base64_jpeg>", "seq": 123 }

// Relay → Laptop (forward)
{ "type": "screen", "data": "<base64_jpeg>", "seq": 123, "from": "phone_..." }

// Laptop → Relay (input)
{ "type": "input", "events": [...], "to": "phone_..." }
```

### Laptop → Relay Connection

```
WSS: wss://relay.example.com:443/wan/laptop?token=<pairing_token>
```

**Messages:** Same framing, opposite direction.

### TLS Certificates

- **Relay:** Cert + key (self-signed or CA-signed)
- **Phone:** Embeds relay CA cert for pinning
- **Laptop:** Uses same cert/key as relay for WSS server
- **Cert pinning:** Phone validates relay cert SHA-256 fingerprint

### Config (settings.yaml)

```yaml
server:
  wan:
    enabled: false
    relay_url: "wss://relay.example.com:443"
    cert_path: "MAYA AI/security/certs/wan_cert.pem"
    key_path: "MAYA AI/security/certs/wan_key.pem"
    mode: "wan"          # lan | wan
    cert_pin_sha256: "abc123..."  # phone-side pinning
```

### Pairing Token Reuse

- Same `maya_<43 chars>` token used for LAN + WAN
- Token scope includes `wan` capability
- Relay validates token with laptop's token store (or shared secret)

### Handoff (LAN ↔ WAN)

1. Phone detects WiFi disconnect → switches to WAN mode
2. Opens WSS to relay → registers with token
3. Laptop accepts relay connection → resumes session
4. When WiFi returns → closes WAN → reconnects LAN
5. Session state preserved (screen stream, input queue)

### Security

- TLS 1.3 mandatory (no cleartext)
- Cert pinning on phone
- Token auth on every frame
- Relay cannot decrypt control payloads (end-to-end)
- Rate limiting per device

### Deployment

- **Self-hosted relay:** Docker container on VPS/home server
- **Tailscale alternative:** Use Tailscale IP as `wan_host` (no relay needed)
- **Cert management:** `mkcert` for local CA, or Let's Encrypt for public relay

---

## 21. Implementation split (updated)

### Laptop (Python)

```
JARVIS\custom\server\
├─ __init__.py
├─ app.py
├─ contracts.py
├─ models.py
├─ auth.py
├─ pair.py
├─ confirm.py
├─ lan.py
├─ bluetooth.py          # PAN/RFCOMM server
├─ wan_relay.py          # WAN relay client/server
├─ tls.py                # Cert management
├─ routes\
│  ├─ __init__.py
│  ├─ chat.py
│  ├─ events.py
│  ├─ health.py
│  ├─ hybrid.py
│  ├─ pair.py
│  ├─ pc.py
│  ├─ remote.py
│  ├─ voice.py
│  ├─ wake.py
│  ├─ wan.py             # WAN endpoints
│  └─ bluetooth.py       # Bluetooth endpoints
```

### Phone (Android)

```
MOBILE APP\app\src\main\java\com\devaraj\maya\
├─ data\remote\
│  ├─ WanRemoteClient.kt      # WSS client + relay
│  ├─ BluetoothRemoteClient.kt # PAN/RFCOMM client
│  └─ ConnectionManager.kt    # LAN/USB/BT/WAN switch
├─ service\
│  ├─ WanRemoteService.kt     # Background WSS connection
│  ├─ BluetoothRemoteService.kt # PAN server
│  └─ RelayCertificatePinner.kt # Cert pinning
└─ ui\settings\
   ├─ WanRemoteSettings.kt
   └─ BluetoothRemoteSettings.kt
```

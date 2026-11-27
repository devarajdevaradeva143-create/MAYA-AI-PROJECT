# P2P Internet Design (Phone ↔ Laptop)

Status: design note. Windows/core work is implemented. Android work is in progress by other agents; this document does not claim Android is complete.

## 1. Goal

Let a phone and a laptop talk over the internet directly, with no cloud data server.

Simple meaning:

- No always-on MAYA server for chat, files, screen, or commands.
- No phone number, email login, or cloud account needed.
- The two devices exchange small signaling text by hand: QR code or copy/paste.
- After that, WebRTC data channels carry control, chat, files, and screen frames.
- Direct P2P is preferred. A relay is only used when the user clearly allows it.

## 2. Architecture

### Local identity

Each device makes its own Ed25519 key pair on the device.

- Private key stays on the device.
- Public key and fingerprint can be shown in the UI.
- Fingerprint is used to confirm "I am talking to the right device".
- Signaling messages are signed. Tampered messages are rejected.

This is a local identity, not a cloud account.

### Manual signaling

Signaling is done by the user, not by a MAYA server.

1. One device shows an invite QR or invite text.
2. The other device scans it or pastes it.
3. One side makes an SDP offer.
4. The offer is sent back by QR or copy/paste.
5. The other side makes an SDP answer.
6. The answer is sent back by QR or copy/paste.
7. WebRTC starts ICE and opens data channels.

No signaling content is stored by the app after the session ends.

### WebRTC data channels

Use separate data channels:

- `control`: command requests and replies. Every command needs a permission gate.
- `chat`: user text only. Chat text is never treated as a command.
- `files`: file chunks with size and checksum shown before accept.
- `screen`: live screen frames in memory only.

WebRTC gives encrypted transport. The app still does its own permission checks.

### STUN and TURN

- Public STUN is an address helper only. It tells a device its public IP and port. No app data goes through STUN.
- TURN is optional and user-owned. It relays WebRTC packets when direct P2P fails.
- TURN credentials are never put in QR, SDP, logs, or settings.yaml.
- When TURN is used, the UI shows a visible badge: `RELAY: <turn name>`.
- When direct P2P is used, the UI shows `DIRECT`.

Default is direct P2P. Cloud relay is not used by default.

## 3. Privacy Rules

These rules are hard rules for this design.

### No data storage

- No cloud data server for chat, files, screen, or command history.
- No app database for message or screen content.
- Chat and screen frames stay in memory for the live session.
- File download goes only to a folder the user picks.
- Temporary file chunks are removed after success or failure.
- Content is not written to debug logs.

### Secrets and config

- Secrets stay in `.env` on desktop/repo setups.
  Examples: identity seed/private key material, TURN username, TURN credential.
- Non-secret config stays in `settings.yaml`.
  Examples: STUN URLs, TURN display name, UI choices, "ask every time" defaults.
- Never put secrets in signaling payloads, QR codes, SDP text, settings.yaml, or source code.
- Keep `.env` out of git.
- On Android, use protected local storage / Android Keystore as the `.env` equivalent. Never ship secrets inside the APK.

### Offline → online never

A device seen only on LAN must never be silently promoted to an online/WAN peer.

- LAN pairing and online P2P are separate states.
- If the LAN path goes offline, do not auto-switch to WAN relay.
- Online P2P needs a fresh explicit QR/SDP exchange.
- WAN relay skeleton must not wake up by itself.

### Command-only permission gates

- Remote commands run only after clear user approval.
- The prompt shows the exact action and peer fingerprint.
- Deny is the default.
- Approval is one command at a time, or a short visible session grant with clear UI state.
- Chat text never runs as a command.
- File receive does not auto-open. Screen view does not auto-start.

## 4. Compatibility With Existing Paths

This P2P path is additive.

- Existing LAN pairing stays as the first choice when both devices are on the same network.
- Existing WAN relay skeleton may stay for explicit user-selected remote use.
- Do not use the cloud relay by default for P2P sessions.
- Do not auto-fallback from LAN/offline to cloud relay.
- A session must show which path is active: `LAN`, `DIRECT`, or `RELAY: <name>`.

## 5. Signaling Payload Schema v2

All invite, offer, and answer payloads use a common envelope.

Encoding: compact UTF-8 JSON. QR can hold the JSON directly or a base64url wrapper; the receiver must accept the documented v2 form. Signature is over canonical JSON with sorted keys and the `signature` field removed.

### Common envelope fields

| Field | Type | Meaning |
| --- | --- | --- |
| `v` | int | Must be `2`. |
| `type` | string | `invite`, `offer`, or `answer`. |
| `session_id` | string | Random UUID for this session. |
| `from` | object | `device_id`, `ed25519_pub` (base64url), `fingerprint`. |
| `to` | object or string | Target `device_id`/fingerprint, or `"*"` for an open invite. |
| `created_at` | string | RFC3339 time. |
| `expires_at` | string | RFC3339 time. Short TTL. |
| `nonce` | string | Random base64url value to stop replay. |
| `capabilities` | array | Example: `control`, `chat`, `files`, `screen`. |
| `relay_policy` | string | `direct_only` or `user_turn_allowed`. |
| `turn_hint` | object or null | Non-secret relay name and URLs only. No credentials. |
| `signature` | string | Ed25519 signature, base64url. |

Receiver must reject when:

- `v` is not `2`.
- Signature is bad.
- Fingerprint does not match the shown peer identity.
- Message is expired.
- Session ID or nonce is reused in a wrong place.
- Target does not match this device, unless `to` is `"*"`.
- Any secret field appears.

SDP and ICE fields are short-lived session values. They are allowed in offer/answer. Identity private keys and TURN credentials are not allowed.

### Invite fields

`type: "invite"`

| Field | Type | Meaning |
| --- | --- | --- |
| `protocol` | string | `maya-p2p/2`. |
| `display_name` | string | Friendly name, not used for trust. |
| `mode` | string | `direct_prefer`. |
| `stun_urls` | array | Public STUN helper URLs. |
| `channels` | array | Requested channels: control/chat/files/screen. |
| `permission_policy` | string | Must be `ask_each_command` or stricter. |
| `lan_hint` | object or null | Optional existing LAN pairing hint. No secret. |

### Offer fields

`type: "offer"`

| Field | Type | Meaning |
| --- | --- | --- |
| `sdp` | string | WebRTC SDP offer text. |
| `sdp_type` | string | Must be `offer`. |
| `ice_ufrag` | string | ICE short-lived session value. |
| `ice_pwd` | string | ICE short-lived session value. |
| `reply_to_nonce` | string | Invite nonce this offer answers. |
| `relay_allowed` | bool | Must match `relay_policy` and local user choice. |
| `turn_name` | string or null | Display name only if user-owned TURN is allowed. |

### Answer fields

`type: "answer"`

| Field | Type | Meaning |
| --- | --- | --- |
| `sdp` | string | WebRTC SDP answer text. |
| `sdp_type` | string | Must be `answer`. |
| `ice_ufrag` | string | ICE short-lived session value. |
| `ice_pwd` | string | ICE short-lived session value. |
| `reply_to_nonce` | string | Offer nonce this answer accepts. |
| `accepted_channels` | array | Channels accepted by answerer. |
| `relay_used` | bool | True only when user-owned TURN is allowed and selected. |
| `turn_name` | string or null | Display name for the relay badge. |

### Small example shape

```json
{
  "v": 2,
  "type": "offer",
  "session_id": "9e6a0d4c-6d6a-4b0e-8df4-4e2f6e0a2a11",
  "from": {
    "device_id": "laptop-01",
    "ed25519_pub": "BASE64URL_PUBLIC_KEY",
    "fingerprint": "sha256:BASE64URL_FINGERPRINT"
  },
  "to": "*",
  "created_at": "2026-11-27T10:00:00Z",
  "expires_at": "2026-11-27T10:05:00Z",
  "nonce": "BASE64URL_NONCE",
  "capabilities": ["control", "chat", "files", "screen"],
  "relay_policy": "direct_only",
  "turn_hint": null,
  "sdp": "v=0...",
  "sdp_type": "offer",
  "ice_ufrag": "SESSION_UFRAG",
  "ice_pwd": "SESSION_PWD",
  "reply_to_nonce": "INVITE_NONCE",
  "relay_allowed": false,
  "turn_name": null,
  "signature": "BASE64URL_ED25519_SIGNATURE"
}
```

## 6. NAT Reality

Direct P2P is not guaranteed.

- STUN helps with simple home NAT. It does not punch every NAT.
- Symmetric NAT, CGNAT, mobile carrier NAT, or strict firewalls may block a direct path.
- In those cases, a user-owned TURN relay may be required.
- If TURN is not configured or not allowed, the call should fail clearly with "No direct path".
- Do not silently switch to a cloud relay.
- Show `DIRECT` or `RELAY: <name>` so the user knows the path.

## 7. Test Matrix

### Automated tests

| Area | Test idea | Expected result |
| --- | --- | --- |
| Identity | Generate local Ed25519 identity | Private key stays local; public key and fingerprint are shown. |
| Schema | Parse v2 invite/offer/answer | All required fields accepted; unknown version rejected. |
| Signature | Change one field after signing | Payload rejected. |
| Replay | Reuse old nonce/session | Payload rejected. |
| Expiry | Use expired payload | Payload rejected. |
| Secrets | Put TURN credential in payload | Rejected by validator; no secret in output. |
| Permission | Chat text contains command | No command runs. |
| Permission | Control command without approval | No command runs. |
| Permission | Approved one command | Only that command runs. |
| Privacy | End session | No chat/file/screen content stored by app. |
| Path state | LAN offline peer | No auto WAN or cloud relay switch. |
| Relay badge | TURN selected | UI shows `RELAY: <name>`. |
| Direct path | STUN-only direct connect | UI shows `DIRECT`; no relay badge. |

### Manual tests

| Setup | Steps | Expected result |
| --- | --- | --- |
| Same LAN, already paired | Use existing LAN pairing; chat, file, screen | Works as before. No relay badge. |
| Same home NAT, internet P2P | Manual QR invite, offer, answer | Direct channel if NAT allows. Shows `DIRECT`. |
| Phone on mobile data, laptop on home Wi-Fi | Manual SDP copy/paste | Direct if possible; otherwise clear failure or user-owned TURN. |
| Symmetric NAT / CGNAT | Try direct, then allow user TURN | Direct may fail. With TURN, session works and shows relay badge. |
| STUN unavailable | Start session | Address helper fails clearly. No app data sent to STUN. |
| TURN unavailable | Allow user TURN but give bad config | Clear error. No cloud fallback. |
| QR tamper | Edit QR payload | Signature/fingerprint check fails. |
| Wrong device | Scan peer with different fingerprint | UI warns; user can reject. |
| File receive | Send file, do not accept | No file opened. Cancel removes temp data. |
| Screen share | Start and stop screen channel | Frames are live only; no app recording. |
| Reconnect | Drop network, then return | Old session is not reused. New QR/SDP needed. |

### How to run tests

From the project root in Windows PowerShell:

```powershell
python -m pytest -q
python -m pytest -q -k "p2p or signaling or privacy"
```

If the repo uses an existing virtual environment, activate that environment first. Do not add a new service or cloud dependency for tests.

Android checks, when the Android module is ready:

```powershell
gradlew.bat test
gradlew.bat connectedAndroidTest
```

`connectedAndroidTest` needs a device or emulator. Manual NAT/CGNAT cases cannot be fully proven by unit tests; run the manual matrix on real networks.

## 8. Current Status

- Windows/core: implemented work exists.
- Android: work in progress by other agents. Do not claim Android parity yet.
- Cloud relay: not default and not part of this P2P design path.
- This document only records the design and test expectations.

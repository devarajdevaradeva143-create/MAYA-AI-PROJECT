# Mobile App Folder

Ithula Android phone-la run aagura **Maya AI** app irukkum.

- App name: **Maya AI**
- Package: `com.devaraj.maya`
- Min Android: **16 (API 36)**
- Kotlin native + Jetpack Compose

## Full plan

Ella design decision-um ithula irukku:

```
MOBILE APP\PLAN.md
```

## Shared API

Phone ↔ laptop API contract:

```
docs\API-CONTRACT.md
```

## Status

Build Complete ✅ — All core phases (0 to 12) implemented & APK built.
APK path: `app/build/outputs/apk/debug/app-debug.apk`

### Implemented Modules:
- **Chat**: WebSocket streaming, Room persistence, Persona switch (Maya / Teacher)
- **Voice**: SpeechRecognizer (STT), Android TextToSpeech (TTS), animated Voice Orb
- **Laptop Control & Pairing**: Auto-discovery NSD, PIN pairing, Remote PC actions (Open app, volume, lock, sleep, media, clipboard, screenshot)
- **Phone Control**: App launcher, SMS send (with confirmation), Call dial (with confirmation), Notification capture, SAF File browser, Accessibility screen reader/actions
- **System Monitoring**: Real-time laptop CPU/RAM/Battery metrics with sparklines + Phone system stats
- **Background & Wake**: Clap-to-wake service, foreground control notification
- **Settings**: Theme (Light/Dark/System), connection modes (WiFi/USB/Bluetooth), SAF Data Export & Delete

## Requirements / Modes (from `docs\REQUIREMENTS.md`)

Mobile app must support (parity target):
- **AI MODE** — voice + text commands to MAYA AI.
- **REMOTE MODE** — laptop screen view + control, file transfer, connect/disconnect.
- **HYBRID MODE** — direct control + AI work simultaneously; no conflicts.

### Mode status (Android)
- AI MODE: ✅ Chat (WS streaming), voice STT/TTS, on-device model.
- REMOTE MODE: ✅ Screen view, mouse/keyboard, PC actions, file transfer, pairing.
- HYBRID MODE: ✅ Control bus (takeover/release), AI task status, conflict tracking.
- Connection Manager: ✅ Wi-Fi/USB/Bluetooth PAN (NSD discovery).
- Dual-boot awareness: ⚠️ Partial (shows active OS).

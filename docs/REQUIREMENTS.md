# MAYA AI — Requirements Specification

> **Source:** User-provided spec (Tamil), captured 2026-11-19.  
> **Status:** Design / requirements only.  
> **Scope:** Integrated Computer Control System — Windows + Fedora + Android, three modes (AI / REMOTE / HYBRID).

## Summary

MAYA AI is an AI + Remote Computer Control System that runs on **Windows and Fedora Linux (KDE)**. Three applications:

1. Windows Application
2. Fedora Application
3. Android Mobile Application

Three operating modes:

1. **AI MODE** — MAYA understands commands (voice/text) and performs PC tasks with user permission.
2. **REMOTE MODE** — user controls the laptop directly from mobile (screen view, mouse, keyboard, files, apps).
3. **HYBRID MODE** — combination of AI + REMOTE; user and AI work simultaneously without control conflicts.

## Mode descriptions

### AI MODE
- Voice & text command input.
- Open/close software.
- Create files & folders.
- Write & run programs.
- File management.
- Permission-gated PC actions.
- Confirm before important actions.

### REMOTE MODE
- Live laptop screen view.
- Mouse & keyboard control.
- Open/close apps.
- View & transfer files.
- Remote control over Wi-Fi/Hotspot/Internet.
- Bluetooth contact with nearby devices.

### HYBRID MODE
- Direct user control + AI autonomous work.
- Voice & text commands.
- Live monitoring of AI work.
- User can take over control anytime.
- No control conflicts when user & AI work together.

## Per-OS apps

### Windows Application
Windows MAYA AI, Windows PC control, screen sharing, mouse/keyboard control, AI task execution, all three modes.

### Fedora Application (KDE)
Fedora MAYA AI, Fedora PC control, screen sharing, mouse/keyboard control, AI task execution, all three modes. Target: Fedora 40+, Plasma 6.x, Wayland primary.

### Android Mobile Application
- Laptop ID + Password input.
- Connect to Windows or Fedora.
- AI / REMOTE / HYBRID mode selection.
- Voice & text commands to MAYA.
- View & control laptop screen.
- File transfer.
- Connect / disconnect.

## Dual Boot
Single laptop with Windows + Fedora (dual boot). Only one OS runs at a time.
- Boot Windows → Windows MAYA AI active.
- Boot Fedora → Fedora MAYA AI active.
- Mobile auto-detects running OS.
- Non-running OS shown as Offline.
- On OS switch, old connection drops, new connection forms.

## Security
- Secure password authentication.
- Encrypted transport.
- Permission-based remote access.
- AI action permission control.
- Confirmation for critical actions.
- Instant disconnect.

## Connection Manager
Manages four connection types:
1. Wi-Fi
2. Mobile Hotspot
3. Bluetooth
4. Internet

Capabilities: discover available connections, check status, secure connect, retry on drop, switch connection type on demand, integrate across Windows/Fedora/Android. Bluetooth for nearby devices; Internet/Network for remote control.

Shared implementation: `JARVIS/custom/tools/connection_manager.py`.

## Final goal
One MAYA AI controlling both Windows and Fedora, three apps (Windows/Fedora/Android), three modes (AI/REMOTE/HYBRID), consistent experience across all three.

## Implementation status (design only where marked)

| Area | Windows | Fedora | Android |
|---|---|---|---|
| AI MODE | Partial | Placeholder | Partial |
| REMOTE MODE | Implemented (screen/input/files) | Partial (no screen/input adapter yet) | Implemented |
| HYBRID MODE | Implemented (control bus) | Partial | Implemented |
| Connection Manager | Partial | Not started | Partial |
| Security | Done | Not started | Partial |
| Dual-boot awareness | Partial | Not started | Partial |

Windows app reference: `WINDOWS APPLICATION/windows/README.md` (build complete, tests pass).  
Fedora app reference: `WINDOWS APPLICATION/fedora/README.md` (placeholder).  
Android app reference: `MOBILE APP/README.md` (build complete, phases 0-12).
path: C:\Users\devar\Desktop\MAYA AI PROJECT\docs\REQUIREMENTS.md
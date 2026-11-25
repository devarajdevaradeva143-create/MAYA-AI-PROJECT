# Maya AI — Biometrics (face + voice)

> Everything local. No camera frame, no audio, no transcript is ever stored or
> uploaded. The PIN always remains the fallback.

## What works

| Factor | How | Secure? |
|---|---|---|
| **Face** | Windows Hello through the trusted `MAYA.exe` helper | Yes — IR camera, anti-spoof, managed by Windows |
| **Voice phrase** | Vosk STT → PBKDF2-SHA256 hash (260k iterations) | Proves you know the phrase |
| **Voiceprint** | Vosk x-vector (`vosk-spk`, 128-dim) + cosine | Proves the voice is similar |
| **PIN** | Existing `maya security` PBKDF2 PIN | Fallback, unchanged |

Voice uses **both** factors by default: the right phrase said by the wrong
voice is rejected (verified: 0.23 similarity vs 1.00 for the same voice).

## Face — Windows Hello

The helper is the user's own build from the earlier PA project, copied to:

```
MAYA AI/security/bin/MAYA.exe
```

It only prints status lines:

```
MAYA.exe --face-check        -> AVAILABILITY=Available
MAYA.exe --face-auth 60      -> RESULT=Verified
```

Exit codes: `0` verified · `2` not verified/cancelled · `3` no window ·
`4` timeout · `1` error. Override the path with `MAYA_EXE` if needed.

Requirements: Windows Hello face must be enrolled in Windows Settings
(`maya biometrics face-settings` opens that page). This laptop has an HP IR
camera and reports `Available`.

```powershell
python -m custom.cli biometrics status
python -m custom.cli biometrics face-check
python -m custom.cli biometrics face-verify --timeout 60
python -m custom.cli biometrics face-settings
```

`face-verify` shows the real Hello prompt — it needs your face and a gesture;
it cannot be scripted.

## Voice — phrase + voiceprint

### Enrollment (3 samples by default)

```powershell
# with the microphone (Windows)
python -m custom.cli biometrics voice-enroll

# or from WAV files (16 kHz mono, or 48 kHz mono — converted automatically)
python -m custom.cli biometrics voice-enroll --wav a.wav --wav b.wav --wav c.wav
```

Say the **same** short phrase every time (2–14 words, e.g. *"maya open the
door"*). The samples must match each other (text similarity ≥ 0.82) or
enrollment is refused.

What is stored (in `MAYA AI/memory/offline/biometrics.json`):

```json
{
  "voice": {
    "algo": "pbkdf2_sha256",
    "iterations": 260000,
    "salt": "...",
    "hashes": ["..."],
    "speaker": {
      "model": "vosk-spk",
      "dim": 128,
      "threshold": 0.65,
      "samples": 3,
      "centroid": ["..."]
    }
  }
}
```

No phrase text, no audio. The hash proves the phrase; the centroid is an
average voice vector.

### Verification

```powershell
python -m custom.cli biometrics voice-verify            # mic: phrase + voice
python -m custom.cli biometrics voice-verify --wav x.wav
python -m custom.cli biometrics voice-verify --text "..." --explain   # diagnostic
```

`--text` checks the phrase only (no audio) and is for troubleshooting. Normal
use never bypasses the voiceprint.

Five failed attempts trigger a 30 s lockout (doubling up to 300 s). A success
resets the counter.

## Unlocking Maya

The lock has a real session state now (`security.json`:

`session_locked`, `last_unlock`):

```powershell
python -m custom.cli lock                        # lock the session
python -m custom.cli security unlock 1234        # PIN
python -m custom.cli security unlock --face      # Windows Hello
python -m custom.cli security unlock --voice     # mic: phrase + voiceprint
python -m custom.cli security unlock --voice --wav sample.wav

# Shortcuts on the biometric commands
python -m custom.cli biometrics face-verify --unlock
python -m custom.cli biometrics voice-verify --unlock
```

While the session is locked, the **whole CLI is guarded**. Any command that is
not explicitly allowed prints the three unlock options and exits with code 1:

```
Error: Maya is locked.
Unlock with one of:
  maya security unlock <pin>
  maya security unlock --face
  maya security unlock --voice
```

What stays available while locked:

| Command | Why |
|---|---|
| `security unlock <pin>` / `--face` / `--voice` | the way back in |
| `security status` | shows PIN/session/last-unlock state, no secrets |
| `biometrics status / face-check / face-verify / face-settings / voice-verify` | verification and Hello setup |
| `lock` | idempotent (already locked) |
| `version` | harmless |
| any `--help` | help must always work |

Everything else — `chat`, `todo`, `reminder`, `monitor`, `knowledge`, `devices`,
`voice`, `config` — is blocked until unlock. The separate cloud command is
guarded too: `maya-cloud ask` / `chat` refuse while locked (`status` still
works), so a locked session cannot leak local files to Gemini. `security
set-pin`, `security backup-code`, `security alerts`, `biometrics voice-enroll`
and `voice-reset` are also blocked, so a stranger cannot replace factors or add
a backup code. Blocked attempts are not written to the alert list (they may just
be a forgetful owner); only failed face/voice unlock attempts are.

A successful unlock stores the method and time (shown by `security status`); a
failed face/voice unlock is recorded as an unauthorized alert. `maya lock`
itself is a normal action, not an alert. The diagnostic `--text` voice mode can
never unlock.

## Session watchdog (continuous check)

`maya security watchdog` is a foreground loop that protects an **unlocked**
session. It never starts by itself — you run it (or your own launcher does).

```powershell
python -m custom.cli security watchdog
# Watchdog: idle lock 5 min | session off | voice off | every 15s
```

| Check | Default | Action |
|---|---|---|
| Idle | 5 min | no keyboard/mouse input → lock + alert |
| Session | off | N minutes after the last unlock → lock + alert |
| Voice | off | every N minutes ask for the enrolled phrase + voiceprint; failure → lock + alert |

Flags: `--idle-minutes`, `--max-session-minutes`, `--voice-every`,
`--check-seconds`, `--voice-seconds`, `--once`.

```powershell
# Lock after 10 idle minutes; require the voice phrase every 30 minutes
python -m custom.cli security watchdog --idle-minutes 10 --voice-every 30

# One evaluation (useful for scripts and tests)
python -m custom.cli security watchdog --once
```

Idle detection uses `GetLastInputInfo` on Windows. On Wayland, the command warns that idle locking is inactive (session and voice checks still work). A voice check is **skipped, not failed**
when no voice password is enrolled or the speaker model is missing. Once the
check is enabled and runnable, a failed, silent or errored check locks the
session — fail closed.

Watchdog alerts are visible with `security alerts` after unlocking (that
command is intentionally blocked while locked).

**Honest limits:** idle lock reacts to *absence of input*, not to recognising a
different person. Windows Hello cannot run silently (it needs a gesture), so
there is no continuous face recognition. The voice re-check is periodic, not
continuous, and the usual replay caveat applies. This is a session guard on top
of the CLI lock, not disk encryption.

### Reset

```powershell
python -m custom.cli biometrics voice-reset
```

Deletes the phrase hashes and the voiceprint. Face is managed by Windows, not
by Maya.

## Configuration

`MAYA AI/config/settings.yaml`:

```yaml
security:
  biometrics:
    face: windows_hello
    voice:
      enabled: true
      require_speaker: true    # false = phrase only (weaker)
      speaker_model: vosk-spk  # folder under voice.stt.model_root
      speaker_threshold: 0.65  # cosine; raise for stricter
      samples: 3
      max_attempts: 5
  watchdog:
    idle_lock_minutes: 5     # 0 = off
    max_session_minutes: 0   # 0 = off
    voice_check_minutes: 0   # 0 = off; needs voice enrollment
    check_seconds: 15
    voice_seconds: 5
```

Model location: `MAYA AI/Model/models/vosk-spk` (13 MB, inside the project).
The STT model is the existing `vosk-en`.

Threshold guidance: same voice on this laptop's synthetic test measured
**1.000**; a different voice **0.22–0.23**. Real humans vary more, so 0.65 is a
reasonable start — try `--explain` and tune for your own voice.

## Privacy

- No audio file survives a recording: it is transcribed, vectorised, deleted.
- No photo ever reaches Maya — Windows Hello handles the camera.
- Only hashes + one averaged vector are written, to offline memory.
- `MAYA AI/memory/offline/*.json` is git-ignored.
- No biometric data is ever sent to `maya-cloud`; `maya chat` only reads the
  local lock state.

## Honest limits

- **Voice can be replayed.** A recording of you saying the phrase may pass the
  voiceprint. It is a convenience factor, not a replacement for the PIN or for
  disk encryption.
- Similar voices (siblings, close impressions) may pass. Raise the threshold if
  that matters.
- The phrase is recognised by an **English** Vosk model — use English words.
- Windows Hello needs the account's face enrollment; Maya cannot create it.
- The helper binary is unsigned. Windows may warn the first time; it is your
  own build and only opens the Hello prompt.
- The full CLI guard is a **convenience gate**, not disk encryption. It stops
  `maya` commands while locked, but the offline JSON files can still be read by
  another program or a user with OS access. Use Windows disk encryption / a
  Windows account password for real protection.

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `face: unavailable` | enroll a face in Windows Settings (`face-settings`) |
| `helper_missing` | `MAYA AI/security/bin/MAYA.exe` missing — copy it back |
| `helper_blocked` | Defender/Smart App Control blocked the helper |
| `not_verified` | face not recognised or the prompt was cancelled |
| `speaker model: missing` | `MAYA AI/Model/models/vosk-spk` missing — re-extract the 13 MB model |
| `No mic signal` | mic muted or wrong device |
| `phrase mismatch` at enrollment | samples differed — say the same words again |
| voice always fails | check `--explain`: phrase vs speaker score; lower the threshold slightly if your voice scores just under it |

## Verified with

| Check | Result |
|---|---|
| `MAYA.exe --face-check` from the project copy | `AVAILABILITY=Available` |
| Enroll 3 × David (SAPI) samples | 128-dim voiceprint, 1 phrase variant |
| Verify David | verified, similarity **1.000** |
| Verify Zira (different voice, same phrase) | rejected, **0.228** |
| Same phrase + Zira vector | `passphrase_ok: True`, `speaker_score: 0.2282`, rejected |
| Locked session → `maya chat` | refused, exit 1, unlock options printed |
| Zira `security unlock --voice --wav` | rejected, session stayed locked, alert recorded |
| David `security unlock --voice --wav` | **Unlocked via voice**, chat started |
| Locked CLI: `todo`, `monitor`, `config`, `set-pin` | blocked, exit 1, no data written |
| Locked CLI: `security status`, `biometrics status`, `todo --help` | allowed |
| Unlock → `todo add/list` | works; lock again → `knowledge status` blocked |
| Locked `maya-cloud ask` / `chat` | refused; `status` and `--help` allowed |
| `security watchdog --once --idle-minutes 0.001` | auto-locked, 1 alert recorded |
| Watchdog loop (`--check-seconds 1`) | printed lock event and exited cleanly |
| Tests | 30 biometrics + 48 security + 25 watchdog + 4 cloud-lock |

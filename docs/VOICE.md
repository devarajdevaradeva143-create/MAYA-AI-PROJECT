# Maya AI — Voice (offline)

> Voice pipeline-oda unmaiyana status. Ellame laptop-la dhaan — cloud illa.

## Enna work aagudhu (verified)

| Feature | Status | Engine |
|---|---|---|
| English TTS (speak) | ✅ works | Piper `en_US-amy` (fallback: Windows SAPI) |
| Tamil TTS | ✅ works | Piper `ta_IN-rasa_female` **or** Kuyil |
| Tanglish TTS (Tamil + English words) | ✅ works | Kuyil `kuyil-20m` |
| English STT (file) | ✅ works | Vosk `vosk-en` |
| Indian English STT | ✅ works | Vosk `vosk-en-in` |
| Tamil STT | ❌ not supported | official Vosk has no Tamil model |
| Mic recording (STT) | ✅ works | Windows `waveIn` |
| 3-clap wake detection | ✅ logic verified | pure Python + `waveIn` |
| Wake phrase ("maya maya maya") | ✅ text check | `check_wake()` |

## TTS engines — user-ku option

`voice.tts.engine` (or the **Voice** dropdown on the Voice page):

| Value | Enna aagum |
|---|---|
| `auto` | Tamil → Kuyil (illena Piper), English → Piper (illena SAPI) |
| `kuyil` | Tiny offline voice. Tamil + English words correct-a pesum (Tanglish-ku best) |
| `piper` | Natural voice, aana Tamil text-la English word vandha thapp-a ucharikkum |
| `sapi` | Windows built-in voices only |

CLI-la force panna:

```powershell
python -m custom.cli voice speak "Vanakkam da, enna pandra?" --lang tamil --engine kuyil
python -m custom.cli voice speak "Vanakkam" --lang tamil --engine piper
```

## Commands

```powershell
python -m custom.cli voice status              # honest status of everything
python -m custom.cli voice speak "Hello da"    # English TTS
python -m custom.cli voice speak "Vanakkam" --lang tamil   # reports missing model

python -m custom.cli voice listen recording.wav            # file -> text
python -m custom.cli voice listen recording.wav --lang en-in
python -m custom.cli voice mic --seconds 6                 # mic -> text

python -m custom.cli voice clap status         # tunables + self-test
python -m custom.cli voice clap test           # synthetic claps (no mic)
python -m custom.cli voice clap listen --once --seconds 30
```

## Where the models live

Everything is inside the project — nothing is downloaded at runtime:

```
MAYA AI/Model/models/
├─ vosk-en/        English (US) small      (~40 MB)
├─ vosk-en-in/     Indian English small    (~80 MB)
├─ vosk-ta/        not available officially (Maya reports this honestly)
└─ kuyil-20m/      Kuyil TTS — Tamil + Tanglish (86 MB, CC BY 4.0)

MAYA AI/voice/
├─ tamil/ta_IN-rasa_female-medium.onnx                active Piper Tamil voice
├─ tamil/candidates/ta_IN-ValluvarNeural-medium.onnx  spare Piper voice
└─ english/en_US-amy-medium.onnx                      active Piper English voice
```

Paths come from `MAYA AI/config/settings.yaml`:

```yaml
voice:
  stt:
    engine: vosk
    model_root: MAYA AI/Model/models
    models: { en: vosk-en, en-in: vosk-en-in, ta: vosk-ta }
```

## Why 48 kHz capture and then down-sample

On this laptop, capturing at 16 kHz **pitch-distorts** the audio (a 1 kHz test
tone came back as ~1536 Hz). `voice_stt.record()` therefore captures at 48 kHz
and cleans it offline:

```
anti-alias low-pass 7.2 kHz -> resample 16 kHz -> high-pass 120 Hz -> normalise
```

Vosk only ever sees a clean 16 kHz mono WAV. Do not "simplify" this without
re-running the tone test.

## Privacy

- Microphone audio is written to a temp WAV, transcribed, then **deleted
  immediately**. No transcript is stored on disk.
- Nothing is sent anywhere. No cloud STT, no cloud TTS.

## Tamil voice — what is actually needed

1. `uv pip install piper-tts`
2. Put a Tamil voice (`.onnx` + `.onnx.json`) in `MAYA AI/voice/tamil/`
3. Maya then uses Piper for Tamil automatically (`PiperTTS.is_available()`).

Until that exists, `voice speak --lang tamil` returns a clear message instead of
pretending to speak. Tamil **STT** is a separate problem: official Vosk has no
Tamil model, so it needs a different recogniser.

## 3-clap wake tuning

Defaults come from the old PA project's calibration on this mic (peak 2800,
3 claps, 120–900 ms gaps, 3 s window, 8 s cooldown). Override in
`settings.yaml` (`voice.clap`) or with `MAYA_CLAP_*` environment variables.

Maya is **command-only** (AGENTS.md rule 7): a clap trigger only reports itself.
It never launches anything on its own.

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `No mic signal (peak N)` | mic muted, or too far — check Windows input device |
| `Could not open the microphone` | another app holds the mic; close it |
| `No 'ta' STT model` | expected — Vosk has no Tamil model |
| `Vosk is not installed` | `uv pip install --no-index --find-links wheels vosk` (wheel is in `JARVIS/wheels/`) |
| Clap never triggers | quiet claps — lower `threshold`, or clap louder/closer |
| Clap triggers randomly | raise `threshold`; check for keyboard/fan transients |

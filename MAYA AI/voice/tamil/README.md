# Tamil Voice (Piper)

Tamil TTS voice files inga irukkum. Ellame **offline** — cloud illa.

## Installed voice

| File | Purpose |
|---|---|
| `ta_IN-rasa_female-medium.onnx` | Active Tamil Piper voice (VITS, 22.05 kHz, female) |
| `ta_IN-rasa_female-medium.onnx.json` | Voice config (phonemes, inference params) |
| `candidates/ta_IN-ValluvarNeural-medium.*` | Spare voice — not used while another `.onnx` is active |

- Source: <https://huggingface.co/tinisoft/piper-ta_IN-rasa_female-medium> (CC-BY-4.0)
- Spare: <https://huggingface.co/Jeyaram-K/piper-tamil-voices> (Apache-2.0)
- Runtime: `piper-tts` Python API (`PiperVoice.load(...).synthesize_wav(...)`).
  The piper 1.8 CLI has a file-output bug on this machine, so Maya uses the API.

**Limits:** Piper Tamil voices read English words with Tamil phonemes, so
"vanakkam da how are you" comes out wrong. Use the Kuyil engine for Tanglish
(`voice.tts.engine: kuyil`).

## Re-install / extra voices

1. Put any Piper Tamil `.onnx` + `.onnx.json` pair in this folder.
2. Maya picks the first `.onnx` file (sorted by name) — keep **one** voice here.
3. English voices go in `../english/` — Tamil never falls back to an English voice.

Tamil TTS code path: `JARVIS/custom/tools/voice.py` (`PiperTTS`),
`JARVIS/custom/tools/kuyil_tts.py` (`KuyilTTS`), and
`WINDOWS APPLICATION/windows/app/services/voice_service.py` (`VoiceAdapter`).

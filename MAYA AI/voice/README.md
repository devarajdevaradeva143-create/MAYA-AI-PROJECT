# Voices

Maya AI voice files inga irukkum. Ellame **offline** — cloud illa.

```
voice/
├─ tamil/                 → Tamil voices (Piper .onnx)
│  └─ candidates/         → extra voices (Maya use pannaadhu)
├─ english/               → English voices (Piper .onnx)
└─ README.md
```

## Active voices

| Folder | File | Voice |
|---|---|---|
| `tamil/` | `ta_IN-rasa_female-medium.onnx` | Piper Tamil female (AI4Bharat Rasa) |
| `english/` | `en_US-amy-medium.onnx` | Piper English female |
| `MAYA AI/Model/models/kuyil-20m/` | `model.safetensors` | Kuyil — Tamil + Tanglish |

## Which one when?

`voice.tts.engine` (settings.yaml) or the **Voice** dropdown on the Voice page:

- `auto` → Tamil: Kuyil (illena Piper), English: Piper (illena SAPI)
- `kuyil` → Tanglish-ku best (Tamil + English words correct-a pesum)
- `piper` → natural, aana Tamil text-la English word thapp-a ucharikkum
- `sapi` → Windows built-in voices only

Piper first `.onnx` file-a (alphabetical) eduthukkum. So oru folder-la
**oru voice mattum** vachuko — spare voices `candidates/`-la podu.

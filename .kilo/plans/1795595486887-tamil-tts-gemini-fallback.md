# Plan: Offline Tamil TTS (sherpa-onnx + Piper) + Gemini fallback

**Path:** `C:\Users\devar\Desktop\MAYA AI PROJECT\.kilo\plans\1795595486887-tamil-tts-gemini-fallback.md`
**Repo:** `MOBILE APP\` (`C:\Users\devar\Desktop\MAYA AI PROJECT\MOBILE APP\`)
**Package:** `com.devaraj.maya`, minSdk 36
**Do NOT touch:** `MOBILE APPLICATION\`

---

## 1. Verification Result (BLOCKER)

| Check | Result |
|---|---|
| Model `ta_IN-rasa_female-medium.onnx` (~60 MB) | EXISTS at `MAYA AI\voice\tamil\` |
| Model `.onnx.json` config | EXISTS |
| `tokens.txt` | **MISSING** — not found anywhere in repo |
| `espeak-ng-data` directory | **MISSING** — not found anywhere in repo |

**Conclusion:** sherpa-onnx Piper VITS requires `tokens.txt` + `espeak-ng-data` alongside the `.onnx` model. Neither is present, so the Tamil voice **cannot be loaded as-is**. Per task instructions: stop here for the Tamil voice and report alternatives (see §4). The rest of the plan (settings, Gemini fallback, TTS abstraction, sherpa-onnx integration) can proceed but the Piper engine will be a no-op/unavailable until the blocker is resolved.

## 2. sherpa-onnx Android Artifact/Version

Official docs (`k2-fsa.github.io/sherpa/onnx/android/build-sherpa-onnx.html`):
- Download `sherpa-onnx-v2.0.1-android.tar.bz2` from GitHub releases (`github.com/k2-fsa/sherpa-onnx/releases/download/v2.0.1/`)
- Extract `jniLibs/{arm64-v8a,armeabi-v7a,x86,x86_64}` 
- Build AAR from `android/SherpaOnnxAar` module → `sherpa_onnx-release.aar`
- No published Maven artifact found; AAR must be built from source or included as a local `flatDir` file dependency.

**Recommended version:** `2.0.1` (verify latest at release time; APK names in docs reference `2.0.2` — use latest stable).

ABIs needed: `arm64-v8a` (device) + `x86_64` (emulator), matching existing `ndk.abiFilters`.

Piper text frontend: sherpa-onnx uses espeak-ng phonemize internally; the `piper-phonemize` Maven artifact (`com.github.csukuangfj:piper-phonemize:v1.5.9`) is only needed for models without a lexicon — not required if `tokens.txt` is present.

## 3. Alternatives for Tamil Voice (unblock options)

**Option A (Recommended):** Download sherpa-onnx-converted Tamil model from k2-fsa releases (`github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models`). Converted bundles include `.onnx` + `tokens.txt` + `espeak-ng-data`. Search for a Tamil Piper voice there.

**Option B:** Generate `tokens.txt` from the existing `.onnx.json` lexicon + download `espeak-ng-data.tar.bz2` from sherpa-onnx `tts-models` release. Place both next to the `.onnx` in assets.

**Option C:** Use Android TTS system Tamil voice (if installed on device) as the only TTS engine; skip sherpa-onnx/Piper entirely for now.

## 4. Implementation Plan

### Task 1 — Add TTS settings to SettingsStore
**Files:**
- `app/src/main/java/com/devaraj/maya/data/prefs/SettingsStore.kt`

**Changes:**
- Add to `MayaSettings` data class:
  - `val ttsEngine: String = "system"` (`"piper"` | `"system"`)
  - `val ttsSpeed: Float = 1.0f` (range 0.5–2.0)
- Add DataStore keys `TTS_ENGINE = stringPreferencesKey("tts_engine")`, `TTS_SPEED = floatPreferencesKey("tts_speed")`
- Map both in `settings` flow
- Add `setTtsEngine(engine: String)` and `setTtsSpeed(speed: Float)` suspend functions

### Task 2 — Create PiperTts wrapper (sherpa-onnx)
**Files:** NEW `app/src/main/java/com/devaraj/maya/voice/PiperTts.kt`

**Design:**
- Wrap sherpa-onnx `OfflineTts` API (Kotlin/Java API from the AAR)
- `load(modelPath, tokensPath, espeakDir, numThreads)` → initialize once
- `speak(text, speed)` → synthesize to PCM, play via `AudioTrack` (STREAM, mono, model sample rate)
- `stop()` / `shutdown()`
- All synthesis local — **no cloud calls**
- If load fails (missing tokens/espeak), throw/return false so caller falls back to Android TTS

**Note:** Because `tokens.txt` + `espeak-ng-data` are missing, `load()` will fail in the current repo state. The wrapper must degrade gracefully.

### Task 3 — Wire sherpa-onnx AAR into Gradle
**Files:**
- `gradle/libs.versions.toml` — add sherpa-onnx AAR version + (optionally) piper-phonemize
- `app/build.gradle.kts` — add `flatDir` repo + `implementation` of local AAR; add jniLibs `src/main/jniLibs/{arm64-v8a,x86_64}` extracted from the android tarball
- `app/src/main/assets/piper/` — model assets (git-ignored; copy script)

### Task 4 — Model copy script (git-ignored assets)
**Files:** NEW `copy_piper_model.ps1` (or `.sh`) at repo root `MOBILE APP\`

**Purpose:** Copy `..\MAYA AI\voice\tamil\ta_IN-rasa_female-medium.onnx` (+ `.onnx.json`, `tokens.txt`, `espeak-ng-data/` when available) into `app/src/main/assets/piper/`.

**Git-ignore:** Ensure `app/src/main/assets/piper/*` is in `.gitignore` (already present for `*.onnx`; extend to cover `tokens.txt` + `espeak-ng-data/`).

### Task 5 — VoiceViewModel: TTS engine selection + speak()
**Files:**
- `app/src/main/java/com/devaraj/maya/ui/voice/VoiceViewModel.kt`

**Changes:**
- Constructor: add `settingsStore: SettingsStore` and `piperTts: PiperTts` (or a TTS provider interface)
- Replace hardcoded `Locale.US` (line 77) with settings-driven language (use `ta-IN` for Piper Tamil, system default for Android TTS)
- `speak(text)`:
  - Read `ttsEngine` + `ttsSpeed` from settings
  - If `piper` and PiperTts loaded → `piperTts.speak(text, speed)`
  - Else → existing Android TTS path (fallback)
- `stopSpeakingInternal()`: stop both TTS engines
- `onCleared()`: shutdown PiperTts

### Task 6 — VoiceViewModel.sendToMaya(): Gemini fallback
**Files:** `app/src/main/java/com/devaraj/maya/ui/voice/VoiceViewModel.kt`

**Changes:** Mirror `ChatViewModel.send()` order (laptop → phone model → Gemini):
1. If `connectionRepository.state` is `Connected` → existing `apiClient.chat(...)` (laptop)
2. Else if phone model ready → (future; for now, fall through to Gemini or error — the phone model path uses `ChatRepository`/local engine which VoiceViewModel doesn't currently have access to; document as TODO or add `OnDeviceModelManager` dependency)
3. Else → Gemini via `GeminiRepository` (needs API key from settings; add to constructor via AppContainer)
4. On each path's success, save message with correct `AiSource` (`LAPTOP` / `PHONE` / `CLOUD`) and call `speak(replyText)`
- **Speak `AiSource.CLOUD` replies with the Tamil voice** (Piper if engine=piper, else Android TTS Tamil)

### Task 7 — DI wiring
**Files:**
- `app/src/main/java/com/devaraj/maya/di/AppContainer.kt`
- `app/src/main/java/com/devaraj\maya\ui\navigation\MayaNavHost.kt`

**Changes:**
- AppContainer: add `piperTts: PiperTts` lazy; add `geminiRepository` already exists
- VoiceViewModel.Factory: add `settingsStore` + `piperTts` (+ `geminiRepository` if needed)
- MayaNavHost.kt:116: pass new Factory args

## 5. Validation

| Command | Purpose |
|---|---|
| `.\gradlew.bat :app:testDebugUnitTest` | Run all unit tests (JUnit 4) |
| `.\gradlew.bat :app:assembleDebug` | Build debug APK |

**Metrics to report after build:**
- APK size delta (before vs after sherpa-onnx AAR + model assets)
- First-load time (PiperTts model load + first synthesis)

## 6. Files Affected (summary)

| File | Action |
|---|---|
| `SettingsStore.kt` | Edit — add tts_engine + tts_speed |
| `PiperTts.kt` | Create — sherpa-onnx wrapper |
| `app/build.gradle.kts` | Edit — sherpa-onnx AAR dependency + jniLibs |
| `gradle/libs.versions.toml` | Edit — sherpa-onnx version |
| `.gitignore` | Edit — extend piper asset ignores |
| `copy_piper_model.ps1` | Create — model copy script |
| `VoiceViewModel.kt` | Edit — TTS routing + Gemini fallback |
| `AppContainer.kt` | Edit — PiperTts + GeminiRepository DI |
| `MayaNavHost.kt` | Edit — Factory args |

## 7. Open Questions / Decisions Needed

1. **Tamil voice blocker:** tokens.txt + espeak-ng-data missing. User must choose Option A/B/C (§3) before Piper TTS can work.
2. **Phone model path in VoiceViewModel:** VoiceViewModel currently has no `OnDeviceModelManager`/`GeminiRepository` dependency. Decide whether to inject both for the full laptop→phone→Gemini fallback, or only Gemini (laptop→Gemini).
3. **sherpa-onnx version:** confirm 2.0.1 vs latest (2.0.2 seen in APK names).

---

**Status:** Planning complete. Awaiting resolution of the Tamil voice blocker (missing tokens.txt + espeak-ng-data) before implementation can proceed.

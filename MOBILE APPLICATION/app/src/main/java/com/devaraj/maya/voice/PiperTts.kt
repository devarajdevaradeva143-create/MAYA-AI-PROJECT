package com.devaraj.maya.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

/**
 * Offline Piper TTS engine.
 *
 * Synthesis happens entirely on-device — no network calls. The real backend
 * is sherpa-onnx + a Piper VITS model. To enable it you need:
 *
 *   1. The sherpa-onnx Android AAR (built from
 *      github.com/k2-fsa/sherpa-onnx/android/SherpaOnnxAar, v2.0.2)
 *         → placed in `app/libs/sherpa-onnx-release.aar`
 *   2. The model `.onnx` + `tokens.txt` + `espeak-ng-data/`
 *         → copied into `app/src/main/assets/piper/`
 *
 * Until those are present, [create] returns null and the caller falls back
 * to Android TextToSpeech. The Tamil voice at
 * `MAYA AI\voice\tamil\ta_IN-rasa_female-medium.onnx` cannot load right now
 * because `tokens.txt` and `espeak-ng-data` are missing from the repo.
 *
 * All file I/O and synthesis are local — zero cloud calls.
 */
class PiperTts private constructor(
    private val context: Context,
) {

    /** Whether the native engine was initialised successfully. */
    val isLoaded: Boolean get() = false

    /**
     * Synthesise [text] to PCM and play it through the speaker.
     * [speed] > 0 — larger means faster (1.0 = normal).
     * Returns false if the engine is not loaded.
     */
    fun speak(text: String, speed: Float): Boolean {
        if (!isLoaded || text.isBlank()) return false
        Log.w("PiperTts", "PiperTts.create() returned null — engine not loaded")
        return false
    }

    /** Stop any in-progress playback immediately. */
    fun stop() {}

    fun shutdown() {}

    /** Companion: build a [PiperTts] from assets. Returns null if load fails. */
    companion object {
        private const val PIPER_ASSET_DIR = "piper"

        fun create(context: Context): PiperTts? {
            val assets = context.assets
            val modelOk = assetExists(assets, "$PIPER_ASSET_DIR/ta_IN-rasa_female-medium.onnx")
                || assetExists(assets, "$PIPER_ASSET_DIR/ta_IN-ValluvarNeural-medium.onnx")
            val tokensOk = assetExists(assets, "$PIPER_ASSET_DIR/tokens.txt")
            val espeakOk = assetDirExists(assets, "$PIPER_ASSET_DIR/espeak-ng-data")

            if (!modelOk || !tokensOk || !espeakOk) {
                Log.w("PiperTts", "Piper assets incomplete — " +
                    "model=$modelOk tokens=$tokensOk espeak=$espeakOk. " +
                    "Run copy_piper_model.ps1 and add tokens.txt + espeak-ng-data.")
                return null
            }

            // The sherpa-onnx AAR is not on Maven Central. Build it from
            // github.com/k2-fsa/sherpa-onnx/android/SherpaOnnxAar (v2.0.2)
            // and place it at app/libs/sherpa-onnx-release.aar, then
            // replace this stub with a real OfflineTts-backed implementation.
            Log.w("PiperTts", "sherpa-onnx AAR not on classpath — PiperTts is a stub")
            return null
        }

        private fun assetExists(assets: android.content.res.AssetManager, path: String): Boolean {
            return try {
                assets.open(path).use { }
                true
            } catch (_: Exception) {
                false
            }
        }

        private fun assetDirExists(assets: android.content.res.AssetManager, dir: String): Boolean {
            return try {
                assets.list(dir) != null
            } catch (_: Exception) {
                false
            }
        }
    }
}

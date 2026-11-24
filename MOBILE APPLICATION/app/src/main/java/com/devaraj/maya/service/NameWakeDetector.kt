package com.devaraj.maya.service

import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.Closeable
import java.io.File

/**
 * Offline "Maya" detector backed by a Vosk model.
 *
 * The recognizer grammar is limited to `maya` plus the unknown token, so the
 * decoder cannot output other words. Final transcripts are returned to the
 * caller; [WakeWordCounter] decides when three hits are enough. Recognition is
 * synchronous — the caller feeds 16 kHz mono PCM from its audio loop.
 */
class NameWakeDetector(modelDir: File) : Closeable {

    private val model = Model(modelDir.absolutePath)
    private val recognizer = Recognizer(model, SAMPLE_RATE, GRAMMAR)

    /** Feed 16 kHz mono PCM. Returns a final transcript, or null mid-utterance. */
    fun accept(samples: ShortArray, length: Int): String? {
        if (length <= 0) return null
        val bytes = ByteArray(length * 2)
        var index = 0
        for (i in 0 until length) {
            val value = samples[i].toInt()
            bytes[index++] = (value and 0xFF).toByte()
            bytes[index++] = ((value shr 8) and 0xFF).toByte()
        }
        if (!recognizer.acceptWaveForm(bytes, bytes.size)) return null
        val result = runCatching { JSONObject(recognizer.result).optString("text") }
            .getOrDefault("")
            .trim()
        return result.ifBlank { null }
    }

    override fun close() {
        runCatching { recognizer.close() }
        runCatching { model.close() }
    }

    private companion object {
        const val SAMPLE_RATE = 16000.0f
        const val GRAMMAR = "[\"maya\", \"[unk]\"]"
    }
}

package com.devaraj.maya.voice

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import java.io.File

/**
 * Plays a WAV byte array produced by Gemini TTS.
 *
 * Kept separate from [PiperTts] on purpose: Piper is the offline engine, this
 * is the cloud-voice engine used only for Gemini replies.
 */
class GeminiVoicePlayer(private val context: Context) {

    private var player: MediaPlayer? = null
    private var currentFile: File? = null

    /** True while a clip is playing. */
    val isPlaying: Boolean
        get() = try {
            player?.isPlaying == true
        } catch (_: Exception) {
            false
        }

    /**
     * Write [wav] to the cache dir and start playback.
     *
     * @return true when playback started, false when it failed (caller should
     *         fall back to the system TTS).
     */
    fun play(
        wav: ByteArray,
        onDone: () -> Unit = {},
        onError: (Throwable) -> Unit = {},
    ): Boolean {
        if (wav.isEmpty()) return false
        stop()
        return try {
            val file = File.createTempFile("maya-gemini-", ".wav", context.cacheDir)
            file.writeBytes(wav)
            currentFile = file

            val mp = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                setDataSource(file.absolutePath)
                setOnCompletionListener {
                    releasePlayer()
                    onDone()
                }
                setOnErrorListener { _, _, _ ->
                    releasePlayer()
                    onError(RuntimeException("Gemini voice playback failed"))
                    true
                }
                prepare()
                start()
            }
            player = mp
            true
        } catch (t: Throwable) {
            releasePlayer()
            onError(t)
            false
        }
    }

    fun stop() {
        try {
            player?.stop()
        } catch (_: Exception) {
            // Already stopped / not started.
        }
        releasePlayer()
    }

    fun release() {
        stop()
    }

    private fun releasePlayer() {
        try {
            player?.release()
        } catch (_: Exception) {
            // Ignore.
        }
        player = null
        currentFile?.delete()
        currentFile = null
    }
}

package com.devaraj.maya.data.model

import android.content.ComponentCallbacks2
import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.IOException
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

data class ModelStatus(
    val installed: Boolean = false,
    val valid: Boolean = false,
    val sizeBytes: Long = 0,
    val fileName: String? = null,
    val loaded: Boolean = false,
    val error: String? = null,
) {
    val sizeText: String
        get() = when {
            sizeBytes >= 1024L * 1024L * 1024L ->
                String.format("%.2f GB", sizeBytes / (1024.0 * 1024.0 * 1024.0))
            sizeBytes >= 1024L * 1024L -> "${sizeBytes / (1024L * 1024L)} MB"
            else -> "$sizeBytes bytes"
        }
}

/**
 * Owns the on-device GGUF model (Phase 9).
 *
 * - The model lives in private app storage and is imported through SAF.
 * - Import verifies the `GGUF` magic and a minimum size before replacing the
 *   previous file, so a half-copied download can never become "installed".
 * - llama.cpp is loaded once and guarded by a native lock; unloading is
 *   best-effort and refuses to run while generation is active.
 */
class OnDeviceModelManager(private val context: Context) {

    val modelDir: File = File(context.filesDir, "models").apply { mkdirs() }

    val expectedModelName: String = MODEL_FILE_NAME

    /** Import target: always the current model name. */
    val modelFile: File get() = File(modelDir, expectedModelName)

    /**
     * The file the app should actually use. A model imported before the
     * tamil-lm-2b switch keeps working instead of showing "not installed";
     * it is replaced on the next import.
     */
    private val activeModelFile: File
        get() = modelFile.takeIf { it.exists() }
            ?: LEGACY_MODEL_FILE_NAMES.asSequence()
                .map { File(modelDir, it) }
                .firstOrNull { it.exists() }
            ?: modelFile

    private val nativeLock = ReentrantLock()

    @Volatile
    private var loadedPath: String? = null

    @Volatile
    private var generating = false

    private val _status = MutableStateFlow(readStatus())
    val status: StateFlow<ModelStatus> = _status.asStateFlow()

    val modelPath: String? get() = if (_status.value.valid) activeModelFile.absolutePath else null

    val isInstalled: Boolean get() = _status.value.valid

    fun refresh(): ModelStatus {
        val next = readStatus()
        _status.value = next
        return next
    }

    fun statusText(): String {
        val current = refresh()
        return when {
            current.valid -> buildString {
                append("Model ready: ${current.fileName} (${current.sizeText})")
                append(if (current.loaded) " · loaded in memory" else " · not loaded")
                if (current.error != null) append(" · ${current.error}")
            }
            current.installed -> "Model file invalid: ${current.error ?: "unknown error"}"
            else ->
                "Model not installed. Import a $MODEL_DISPLAY_NAME GGUF (about $MODEL_APPROX_SIZE)."
        }
    }

    /**
     * Copy a user-picked GGUF into app storage. Runs on [Dispatchers.IO].
     * The previous model is replaced only after the new file passes checks.
     */
    suspend fun importModel(
        uri: Uri,
        onProgress: (copied: Long, total: Long) -> Unit = { _, _ -> },
    ): Result<ModelStatus> = withContext(Dispatchers.IO) {
        val temp = File(modelDir, "$expectedModelName.part")
        try {
            if (generating) throw IOException("Cannot import while generating")
            if (NativeLlama.safeIsLoaded() && !unload()) {
                throw IOException("Could not unload the current model")
            }

            val total = querySize(uri)
            val input = context.contentResolver.openInputStream(uri)
                ?: throw IOException("Could not open the selected file")

            var copied = 0L
            var lastReported = 0L
            input.use { raw ->
                BufferedInputStream(raw, BUFFER_SIZE).use { source ->
                    BufferedOutputStream(temp.outputStream(), BUFFER_SIZE).use { sink ->
                        val buffer = ByteArray(BUFFER_SIZE)
                        while (true) {
                            val read = source.read(buffer)
                            if (read < 0) break
                            sink.write(buffer, 0, read)
                            copied += read
                            if (copied - lastReported >= PROGRESS_STEP) {
                                lastReported = copied
                                onProgress(copied, total)
                            }
                        }
                    }
                }
            }
            onProgress(copied, total)

            if (temp.length() < MIN_MODEL_BYTES) {
                throw IOException("File is too small to be a usable model (${temp.length()} bytes)")
            }
            if (!hasGgufMagic(temp)) {
                throw IOException("Not a GGUF model file")
            }

            val target = modelFile
            if (target.exists() && !target.delete()) {
                throw IOException("Could not replace the existing model")
            }
            if (!temp.renameTo(target)) {
                throw IOException("Could not save the model file")
            }
            // The legacy model is no longer used; free its ~1.1 GB.
            LEGACY_MODEL_FILE_NAMES.forEach { File(modelDir, it).delete() }
            loadedPath = null
            val next = refresh()
            if (!next.valid) throw IOException(next.error ?: "Model verification failed")
            Result.success(next)
        } catch (e: Exception) {
            temp.delete()
            Result.failure(e)
        }
    }

    /** Unload and delete the model file. Returns false when the model is busy. */
    fun delete(): Boolean {
        if (NativeLlama.safeIsLoaded() || loadedPath != null) {
            if (!unload()) return false
        }
        File(modelDir, "$expectedModelName.part").delete()
        val deleted = modelFile.delete()
        LEGACY_MODEL_FILE_NAMES.forEach { File(modelDir, it).delete() }
        loadedPath = null
        refresh()
        return deleted || !modelFile.exists()
    }

    /** Best-effort unload. Returns false if generation is using the model. */
    fun unload(): Boolean {
        if (!nativeLock.tryLock()) return false
        return try {
            if (generating) return false
            NativeLlama.unload()
            loadedPath = null
            refresh()
            true
        } finally {
            nativeLock.unlock()
        }
    }

    fun cancel() = NativeLlama.cancel()

    /**
     * Generate a reply on the phone. Blocks the calling (IO) thread until the
     * reply is complete; [onToken] receives complete UTF-8 chunks as they are
     * produced so the UI can stream.
     */
    fun generate(
        prompt: String,
        maxTokens: Int = PromptBuilder.MAX_NEW_TOKENS,
        onToken: (String) -> Unit = {},
    ): Result<String> {
        if (!_status.value.valid) {
            return Result.failure(IllegalStateException("Phone model not installed"))
        }
        nativeLock.lock()
        try {
            if (!ensureLoaded()) {
                return Result.failure(IllegalStateException("Could not load the phone model"))
            }
            generating = true
            val raw = NativeLlama.safeGenerateStream(prompt, maxTokens, onToken)
                .getOrElse { return Result.failure(it) }
            val text = PromptBuilder.stripThink(raw).trim()
            if (text.isBlank()) {
                return Result.failure(IllegalStateException("Phone model returned an empty reply"))
            }
            return Result.success(text)
        } catch (e: Exception) {
            return Result.failure(e)
        } finally {
            generating = false
            nativeLock.unlock()
        }
    }

    /** Called from Application.onTrimMemory; never blocks the main thread. */
    fun onTrimMemory(level: Int) {
        if (level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW) unload()
    }

    fun onLowMemory() {
        unload()
    }

    private fun ensureLoaded(): Boolean {
        val path = modelPath ?: return false
        if (loadedPath == path && NativeLlama.safeIsLoaded()) return true
        NativeLlama.unload()
        loadedPath = null
        val loaded = NativeLlama.safeLoad(path)
        loadedPath = if (loaded) path else null
        refresh()
        return loaded
    }

    private fun readStatus(): ModelStatus {
        val file = activeModelFile
        if (!file.exists()) {
            loadedPath = null
            return ModelStatus()
        }

        val size = file.length()
        val installed = size >= MIN_MODEL_BYTES
        val valid = installed && hasGgufMagic(file)
        val error = when {
            !installed -> "File is too small to be a model"
            !valid -> "Not a GGUF model file"
            else -> null
        }
        if (!valid) loadedPath = null
        return ModelStatus(
            installed = installed,
            valid = valid,
            sizeBytes = size,
            fileName = file.name,
            loaded = valid && loadedPath == file.absolutePath && NativeLlama.safeIsLoaded(),
            error = error,
        )
    }

    private fun querySize(uri: Uri): Long {
        return runCatching {
            context.contentResolver.query(
                uri,
                arrayOf(OpenableColumns.SIZE),
                null,
                null,
                null,
            )?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getLong(0) else -1L
            } ?: -1L
        }.getOrDefault(-1L)
    }

    private fun hasGgufMagic(file: File): Boolean = runCatching {
        file.inputStream().use { input ->
            val header = ByteArray(4)
            if (input.read(header) != 4) return@use false
            header.contentEquals(GGUF_MAGIC)
        }
    }.getOrDefault(false)

    companion object {
        /** Current phone model: tamil-lm-2b (Qwen3.5-2B tuned for Tamil/Tanglish). */
        const val MODEL_FILE_NAME = "tamil-lm-2b-instruct-q4_k_m.gguf"
        const val MODEL_DISPLAY_NAME = "tamil-lm-2b Instruct Q4_K_M"
        const val MODEL_APPROX_SIZE = "1.3 GB"

        /** Models imported before the switch: still loadable, replaced on import. */
        private val LEGACY_MODEL_FILE_NAMES = listOf("qwen3-1.7b-instruct-q4_k_m.gguf")

        /** Small GGUFs (0.6B) are still valid; this rejects thumbnails/partials. */
        const val MIN_MODEL_BYTES = 50L * 1024L * 1024L

        private const val BUFFER_SIZE = 1024 * 1024
        private const val PROGRESS_STEP = 16L * 1024L * 1024L

        private val GGUF_MAGIC = byteArrayOf(
            'G'.code.toByte(),
            'G'.code.toByte(),
            'U'.code.toByte(),
            'F'.code.toByte(),
        )
    }
}

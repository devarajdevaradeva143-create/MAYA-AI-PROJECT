package com.devaraj.maya.data.wake

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedInputStream
import java.io.File
import java.io.FilterInputStream
import java.io.InputStream
import java.util.Locale
import java.util.UUID
import java.util.zip.ZipInputStream

data class VoskModelStatus(
    val installed: Boolean = false,
    val sizeBytes: Long = 0,
    val error: String? = null,
) {
    val sizeText: String
        get() = when {
            sizeBytes >= 1024L * 1024L * 1024L ->
                String.format(Locale.US, "%.1f GB", sizeBytes / (1024.0 * 1024.0 * 1024.0))
            sizeBytes >= 1024L * 1024L ->
                String.format(Locale.US, "%.0f MB", sizeBytes / (1024.0 * 1024.0))
            else -> "${sizeBytes / 1024} KB"
        }
}

/**
 * Stores an imported Vosk model inside private app storage:
 * `filesDir/vosk/model/am/final.mdl` etc.
 *
 * The user downloads `vosk-model-small-en-us-0.15.zip` (about 40 MB) from
 * alphacephei.com/vosk/models and imports the zip from Settings. Nothing is
 * downloaded by the app and nothing leaves the phone.
 */
class VoskModelStore(private val context: Context) {

    private val rootDir: File
        get() = File(context.filesDir, "vosk")

    val modelDir: File
        get() = File(rootDir, "model")

    fun status(): VoskModelStatus {
        val marker = File(modelDir, "am/final.mdl")
        if (!marker.isFile) {
            return VoskModelStatus(installed = false)
        }
        val size = modelDir.walkTopDown().filter { it.isFile }.sumOf { it.length() }
        return VoskModelStatus(installed = true, sizeBytes = size)
    }

    fun isInstalled(): Boolean = File(modelDir, "am/final.mdl").isFile

    /**
     * Import a Vosk model zip. Accepts either a zip whose top folder is the
     * model (official Vosk packages) or a zip that directly contains `am/`.
     */
    suspend fun importZip(
        uri: Uri,
        onProgress: (Int?) -> Unit = {},
    ): Result<VoskModelStatus> = withContext(Dispatchers.IO) {
        val tempRoot = File(context.cacheDir, "vosk-import-${UUID.randomUUID()}")
        try {
            val totalBytes = contentLength(uri)
            var extractedBytes = 0L
            var modelRoot: File? = null

            tempRoot.mkdirs()
            val input = context.contentResolver.openInputStream(uri)
                ?: return@withContext Result.failure(IllegalArgumentException("Cannot open the selected file"))

            BufferedInputStream(CountingStream(input) { read ->
                extractedBytes += read
                if (totalBytes > 0) {
                    onProgress(((extractedBytes * 100) / totalBytes).toInt().coerceIn(0, 100))
                }
            }).use { buffered ->
                ZipInputStream(buffered).use { zip ->
                    var entry = zip.nextEntry
                    var totalExtracted = 0L
                    while (entry != null) {
                        val name = entry.name.replace('\\', '/')
                        if (name.startsWith("/") || name.contains("..")) {
                            return@withContext Result.failure(IllegalArgumentException("Unsafe zip entry: $name"))
                        }
                        val outFile = File(tempRoot, name)
                        if (entry.isDirectory) {
                            outFile.mkdirs()
                        } else {
                            outFile.parentFile?.mkdirs()
                            outFile.outputStream().use { out -> zip.copyTo(out) }
                            totalExtracted += outFile.length()
                            if (totalExtracted > MAX_EXTRACTED_BYTES) {
                                return@withContext Result.failure(
                                    IllegalArgumentException("Model zip is larger than 600 MB"),
                                )
                            }
                        }
                        zip.closeEntry()
                        entry = zip.nextEntry
                    }
                }
            }

            modelRoot = findModelRoot(tempRoot)
            if (modelRoot == null) {
                return@withContext Result.failure(
                    IllegalArgumentException("Not a Vosk model zip (missing am/final.mdl)"),
                )
            }

            // Swap the model in only after a complete extraction.
            val staging = File(rootDir, "model.new")
            staging.deleteRecursively()
            rootDir.mkdirs()
            if (!modelRoot.renameTo(staging)) {
                modelRoot.copyRecursively(staging, overwrite = true)
                modelRoot.deleteRecursively()
            }
            modelDir.deleteRecursively()
            if (!staging.renameTo(modelDir)) {
                staging.copyRecursively(modelDir, overwrite = true)
                staging.deleteRecursively()
            }
            onProgress(100)
            val status = status()
            if (!status.installed) {
                Result.failure(IllegalStateException("Model files are incomplete"))
            } else {
                Result.success(status)
            }
        } catch (error: Exception) {
            Result.failure(error)
        } finally {
            tempRoot.deleteRecursively()
        }
    }

    suspend fun delete(): Boolean = withContext(Dispatchers.IO) {
        val deleted = modelDir.deleteRecursively()
        if (rootDir.listFiles()?.isEmpty() == true) rootDir.delete()
        deleted || !modelDir.exists()
    }

    private fun findModelRoot(directory: File): File? {
        val marker = directory.walkTopDown()
            .firstOrNull { it.isFile && it.name == "final.mdl" && it.parentFile?.name == "am" }
            ?: return null
        return marker.parentFile?.parentFile
    }

    private fun contentLength(uri: Uri): Long = runCatching {
        context.contentResolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L
    }.getOrDefault(-1L)

    private class CountingStream(
        input: InputStream,
        private val onRead: (Int) -> Unit,
    ) : FilterInputStream(input) {
        override fun read(): Int = super.read().also { if (it >= 0) onRead(1) }
        override fun read(b: ByteArray, off: Int, len: Int): Int =
            super.read(b, off, len).also { if (it > 0) onRead(it) }
    }

    private companion object {
        const val MAX_EXTRACTED_BYTES = 600L * 1024L * 1024L
    }
}

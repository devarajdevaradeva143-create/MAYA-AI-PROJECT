package com.devaraj.maya.service

import android.content.Context
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import androidx.annotation.RequiresApi
import com.devaraj.maya.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Captures the phone screen via MediaProjection and emits JPEG frames.
 * Runs on a dedicated handler thread to avoid blocking the main thread.
 */
class ScreenCaptureService private constructor(
    private val context: Context,
    private val mediaProjection: MediaProjection,
    private val width: Int,
    private val height: Int,
    private val dpi: Int,
    private val quality: Int = 70,
) {

    companion object {
        private const val TAG = "ScreenCaptureService"
        private const val MAX_DIMENSION = 1920
        private const val FRAME_INTERVAL_MS = 66 // ~15 fps

        @Volatile
        private var instance: ScreenCaptureService? = null

        /** True while frames are actually being captured; observed by the Settings UI. */
        private val _running = MutableStateFlow(false)
        val running: StateFlow<Boolean> = _running

        fun start(
            context: Context,
            mediaProjection: MediaProjection,
            width: Int = 1280,
            height: Int = 720,
            dpi: Int = 240,
        ): ScreenCaptureService? {
            if (instance != null) {
                instance?.stop()
            }
            val displayMetrics = context.resources.displayMetrics
            val w = width.coerceAtMost(MAX_DIMENSION)
            val h = height.coerceAtMost(MAX_DIMENSION)
            instance = ScreenCaptureService(context, mediaProjection, w, h, dpi)
            instance?.startCapture()
            return instance
        }

        fun getInstance(): ScreenCaptureService? = instance

        fun stop() {
            instance?.stop()
            instance = null
        }

        fun isRunning(): Boolean = instance?.isCapturing?.get() == true
    }

    private val handlerThread = HandlerThread("ScreenCapture", android.os.Process.THREAD_PRIORITY_BACKGROUND).apply { start() }
    private val handler = Handler(handlerThread.looper)
    private val imageReader = ImageReader.newInstance(width, height, 0x1, 3) // RGBA_8888 = 1
    private var virtualDisplay: VirtualDisplay? = null
    private val isCapturing = AtomicBoolean(false)
    val isCapturingValue: Boolean get() = isCapturing.get()
    private val frameCount = AtomicInteger(0)
    private var lastFrameTime = 0L

    // Frame output channel for WebSocket consumers
    private val frameChannel = Channel<ByteArray>(capacity = 5)
    val frames: ReceiveChannel<ByteArray> = frameChannel

    // State flow for monitoring
    private val _state = MutableStateFlow(CaptureState.IDLE)
    val state: StateFlow<CaptureState> = _state

    // Android 14+ refuses createVirtualDisplay() unless a callback is registered,
    // and the system ends the session through this callback when the user stops it.
    private val projectionCallback = object : MediaProjection.Callback() {
        override fun onStop() {
            Log.d(TAG, "MediaProjection stopped by the system")
            stop()
        }
    }

    private fun startCapture() {
        if (isCapturing.getAndSet(true)) return
        _state.value = CaptureState.STARTING

        runCatching { mediaProjection.registerCallback(projectionCallback, handler) }
            .onFailure { Log.w(TAG, "Could not register MediaProjection callback", it) }

        imageReader.setOnImageAvailableListener({ reader ->
            handler.post { onImageAvailable(reader) }
        }, handler)

        virtualDisplay = mediaProjection.createVirtualDisplay(
            "MayaScreenCapture",
            width,
            height,
            dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR
                or DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC
                or DisplayManager.VIRTUAL_DISPLAY_FLAG_SECURE,
            imageReader.surface,
            null,
            handler,
        )

        if (virtualDisplay == null) {
            Log.e(TAG, "Failed to create VirtualDisplay")
            stop()
            return
        }

        _state.value = CaptureState.RUNNING
        _running.value = true
        Log.d(TAG, "Screen capture started: ${width}x${height}@${dpi}dpi")
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun onImageAvailable(reader: ImageReader) {
        if (!isCapturing.get()) return

        val now = System.currentTimeMillis()
        if (now - lastFrameTime < FRAME_INTERVAL_MS) {
            reader.acquireLatestImage()?.close()
            return
        }
        lastFrameTime = now

        val image = reader.acquireLatestImage() ?: return
        try {
            val jpeg = imageToJpeg(image)
            if (jpeg != null && jpeg.isNotEmpty()) {
                frameCount.incrementAndGet()
                frameChannel.trySend(jpeg)
            }
        } finally {
            image.close()
        }
    }

    private fun imageToJpeg(image: Image): ByteArray? {
        val planes = image.planes
        if (planes.size != 1) {
            Log.w(TAG, "Unexpected plane count: ${planes.size}")
            return null
        }

        val buffer = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
        val w = image.width
        val h = image.height

        if (pixelStride != 4) {
            Log.w(TAG, "Unexpected pixel stride: $pixelStride")
            return null
        }

        val bitmap = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888)
        bitmap.copyPixelsFromBuffer(buffer)

        val outputStream = ByteArrayOutputStream()
        val success = bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, quality, outputStream)
        bitmap.recycle()

        return if (success) outputStream.toByteArray() else null
    }

    fun stop() {
        _running.value = false
        if (!isCapturing.getAndSet(false)) return
        _state.value = CaptureState.STOPPING

        runCatching { mediaProjection.unregisterCallback(projectionCallback) }
            .onFailure { Log.w(TAG, "Could not unregister MediaProjection callback", it) }

        try {
            virtualDisplay?.release()
        } catch (e: Exception) {
            Log.w(TAG, "Error releasing VirtualDisplay", e)
        }
        virtualDisplay = null

        try {
            imageReader.setOnImageAvailableListener(null, null)
            imageReader.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing ImageReader", e)
        }

        handlerThread.quitSafely()
        frameChannel.close()
        _state.value = CaptureState.IDLE
        Log.d(TAG, "Screen capture stopped. Frames captured: ${frameCount.get()}")
    }

    fun getFrameCount(): Int = frameCount.get()

    enum class CaptureState { IDLE, STARTING, RUNNING, STOPPING }
}
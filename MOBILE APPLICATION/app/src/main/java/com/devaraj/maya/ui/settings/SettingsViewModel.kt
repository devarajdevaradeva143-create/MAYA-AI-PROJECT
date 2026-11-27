package com.devaraj.maya.ui.settings

import android.app.Application
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.model.ModelStatus
import com.devaraj.maya.data.model.OnDeviceModelManager
import com.devaraj.maya.data.prefs.MayaSettings
import com.devaraj.maya.domain.model.OperatingMode
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.secure.TokenVault
import com.devaraj.maya.data.wake.VoskModelStatus
import com.devaraj.maya.data.wake.VoskModelStore
import com.devaraj.maya.service.MayaAccessibilityService
import com.devaraj.maya.service.PhoneRemoteForegroundService
import com.devaraj.maya.service.PhoneRemoteHttpServer
import com.devaraj.maya.service.ScreenCaptureService
import com.devaraj.maya.service.WakeForegroundService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class SettingsUiState(
    val settings: MayaSettings = MayaSettings(),
    val exportStatus: String? = null,
    val deleteStatus: String? = null,
    val modelStatus: ModelStatus = ModelStatus(),
    val modelBusy: Boolean = false,
    val modelProgress: Int? = null,
    val modelMessage: String? = null,
    val voskModel: VoskModelStatus = VoskModelStatus(),
    val voskBusy: Boolean = false,
    val voskProgress: Int? = null,
    val voskMessage: String? = null,
    val screenSharing: Boolean = false,
)

class SettingsViewModel(
    private val app: Application,
    private val settingsStore: SettingsStore,
    private val db: MayaDatabase,
    private val tokenVault: TokenVault,
    private val modelManager: OnDeviceModelManager,
    private val voskModelStore: VoskModelStore,
) : ViewModel() {

    private val _state = MutableStateFlow(SettingsUiState())
    val state: StateFlow<SettingsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            settingsStore.settings.collect { s ->
                _state.update { it.copy(settings = s) }
            }
        }
        viewModelScope.launch {
            modelManager.status.collect { status ->
                _state.update { it.copy(modelStatus = status) }
            }
        }
        modelManager.refresh()
        viewModelScope.launch(Dispatchers.IO) {
            val status = voskModelStore.status()
            _state.update { it.copy(voskModel = status) }
        }
        viewModelScope.launch {
            ScreenCaptureService.running.collect { running ->
                _state.update { it.copy(screenSharing = running) }
            }
        }
    }

    fun setTheme(mode: com.devaraj.maya.data.prefs.ThemeMode) {
        viewModelScope.launch { settingsStore.setTheme(mode) }
    }

    fun setConnectionMode(mode: String) {
        viewModelScope.launch { settingsStore.setConnectionMode(mode) }
    }

    fun setOperatingMode(mode: com.devaraj.maya.domain.model.OperatingMode) {
        viewModelScope.launch { settingsStore.setOperatingMode(mode) }
    }

    fun setWakeName(enabled: Boolean) {
        viewModelScope.launch {
            settingsStore.setWakeNameEnabled(enabled)
            restartWakeIfRunning()
        }
    }

    fun importVoskModel(uri: Uri) {
        if (_state.value.voskBusy) return
        viewModelScope.launch {
            _state.update {
                it.copy(voskBusy = true, voskProgress = 0, voskMessage = null)
            }
            val result = voskModelStore.importZip(uri) { progress ->
                _state.update { it.copy(voskProgress = progress) }
            }
            result.fold(
                onSuccess = { status ->
                    _state.update {
                        it.copy(
                            voskBusy = false,
                            voskProgress = null,
                            voskModel = status,
                            voskMessage = "Wake-word model installed (${status.sizeText}).",
                        )
                    }
                    restartWakeIfRunning()
                },
                onFailure = { error ->
                    _state.update {
                        it.copy(
                            voskBusy = false,
                            voskProgress = null,
                            voskMessage = "Import failed: ${error.message}",
                        )
                    }
                },
            )
        }
    }

    fun deleteVoskModel() {
        if (_state.value.voskBusy) return
        viewModelScope.launch {
            _state.update { it.copy(voskBusy = true, voskMessage = null) }
            val deleted = voskModelStore.delete()
            settingsStore.setWakeNameEnabled(false)
            _state.update {
                it.copy(
                    voskBusy = false,
                    voskModel = voskModelStore.status(),
                    voskMessage = if (deleted) {
                        "Wake-word model removed."
                    } else {
                        "Could not remove the wake-word model."
                    },
                )
            }
            restartWakeIfRunning()
        }
    }

    /** The wake service reads settings and model state once at startup. */
    private suspend fun restartWakeIfRunning() {
        if (!WakeForegroundService.isRunning) return
        WakeForegroundService.stop(app)
        delay(500)
        WakeForegroundService.start(app)
    }

    fun setControlEnabled(enabled: Boolean) {
        viewModelScope.launch { settingsStore.setControlEnabled(enabled) }
    }

    fun setRequireUnlock(required: Boolean) {
        viewModelScope.launch { settingsStore.setControlRequireUnlock(required) }
    }

    fun setPhoneRemoteEnabled(enabled: Boolean) {
        viewModelScope.launch {
            settingsStore.setPhoneRemoteEnabled(enabled)
            if (enabled) {
                val accessibility = MayaAccessibilityService.instance
                // Foreground service is only startable while accessibility is bound
                // (its exemption is what allows the background start on Android 12+).
                if (accessibility != null) {
                    PhoneRemoteForegroundService.start(app)
                    // Start HTTP server if the accessibility service is connected
                    PhoneRemoteHttpServer.start(app, accessibility, ScreenCaptureService.getInstance())
                }
            } else {
                PhoneRemoteHttpServer.stop()
                PhoneRemoteForegroundService.stop(app)
            }
        }
    }

    /**
     * Starts MediaProjection capture after the user accepted the system consent dialog.
     * The consent result must be consumed promptly, so the foreground service is started
     * first (Android 14+ requires a mediaProjection FGS before getMediaProjection()).
     */
    fun startScreenShare(resultCode: Int, data: Intent) {
        viewModelScope.launch {
            val manager = app.getSystemService(MediaProjectionManager::class.java) ?: return@launch
            // Android 14+ requires a mediaProjection-type foreground service to be
            // running before getMediaProjection().
            PhoneRemoteForegroundService.start(app)
            delay(500)
            val projection = runCatching { manager.getMediaProjection(resultCode, data) }.getOrNull() ?: return@launch
            val metrics = app.resources.displayMetrics
            ScreenCaptureService.start(
                app, projection, metrics.widthPixels, metrics.heightPixels, metrics.densityDpi,
            )
        }
    }

    fun stopScreenShare() { ScreenCaptureService.stop() }

    fun exportData(uri: Uri) {
        viewModelScope.launch {
            try {
                val conversations = db.conversationDao().observeAll().first()
                val audit = db.auditDao().observeRecent(10000).first()
                val notifications = db.notificationDao().observeRecent(10000).first()
                val json = buildJsonObject {
                    put("exported_at", SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).format(Date()))
                    put("app", "Maya AI")
                    put("version", com.devaraj.maya.BuildConfig.VERSION_NAME)
                    put("conversations", buildJsonArray {
                        conversations.forEach { c ->
                            val msgs = runCatching { db.messageDao().lastN(c.id, 1000) }.getOrDefault(emptyList())
                            add(buildJsonObject {
                                put("id", c.id)
                                put("title", c.title)
                                put("created_at", c.createdAt)
                                put("updated_at", c.updatedAt)
                                put("messages", buildJsonArray {
                                    msgs.forEach { m ->
                                        add(buildJsonObject {
                                            put("role", m.role)
                                            put("content", m.content.take(2000))
                                            put("created_at", m.createdAt)
                                        })
                                    }
                                })
                            })
                        }
                    })
                    put("audit", buildJsonArray {
                        audit.forEach { a ->
                            add(buildJsonObject {
                                put("action", a.action)
                                put("detail", a.detail)
                                put("allowed", a.allowed)
                                put("created_at", a.createdAt)
                            })
                        }
                    })
                    put("notifications", buildJsonArray {
                        notifications.forEach { n ->
                            add(buildJsonObject {
                                put("package", n.packageName)
                                put("title", n.title)
                                put("body", n.body)
                                put("posted_at", n.postedAt)
                            })
                        }
                    })
                }.toString()
                app.contentResolver.openOutputStream(uri)?.use { out ->
                    out.write(json.toByteArray())
                }
                _state.update { it.copy(exportStatus = "Exported ${conversations.size} chats, ${audit.size} audit rows") }
            } catch (e: Exception) {
                _state.update { it.copy(exportStatus = "Export failed: ${e.message}") }
            }
        }
    }

    fun deleteAllData() {
        viewModelScope.launch {
            try {
                db.conversationDao().deleteAll()
                db.messageDao().deleteAll()
                db.deviceDao().deleteAll()
                db.auditDao().deleteAll()
                db.notificationDao().deleteAll()
                db.pcCommandDao().deleteAll()
                settingsStore.setOnboardingDone(false)
                tokenVault.deleteAll()
                _state.update { it.copy(deleteStatus = "All local data deleted") }
            } catch (e: Exception) {
                _state.update { it.copy(deleteStatus = "Delete failed: ${e.message}") }
            }
        }
    }

    fun importModel(uri: Uri) {
        if (_state.value.modelBusy) return
        viewModelScope.launch {
            _state.update {
                it.copy(modelBusy = true, modelProgress = 0, modelMessage = null)
            }
            val result = modelManager.importModel(uri) { copied, total ->
                val progress = if (total > 0) {
                    ((copied * 100) / total).toInt().coerceIn(0, 100)
                } else {
                    null
                }
                _state.update { it.copy(modelProgress = progress) }
            }
            result.fold(
                onSuccess = { status ->
                    _state.update {
                        it.copy(
                            modelBusy = false,
                            modelProgress = null,
                            modelMessage = "Phone model installed (${status.sizeText}).",
                        )
                    }
                },
                onFailure = { error ->
                    _state.update {
                        it.copy(
                            modelBusy = false,
                            modelProgress = null,
                            modelMessage = "Import failed: ${error.message}",
                        )
                    }
                },
            )
        }
    }

    fun deleteModel() {
        if (_state.value.modelBusy) return
        viewModelScope.launch {
            _state.update { it.copy(modelBusy = true, modelMessage = null) }
            val deleted = withContext(Dispatchers.IO) { modelManager.delete() }
            _state.update {
                it.copy(
                    modelBusy = false,
                    modelMessage = if (deleted) {
                        "Phone model deleted."
                    } else {
                        "Could not delete the model while it is generating. Stop the reply and try again."
                    },
                )
            }
        }
    }

    fun unloadModel() {
        if (_state.value.modelBusy) return
        viewModelScope.launch {
            _state.update { it.copy(modelBusy = true, modelMessage = null) }
            val unloaded = withContext(Dispatchers.IO) { modelManager.unload() }
            _state.update {
                it.copy(
                    modelBusy = false,
                    modelMessage = if (unloaded) {
                        "Phone model unloaded from memory."
                    } else {
                        "Could not unload while the phone model is generating."
                    },
                )
            }
        }
    }

    fun consumeExportStatus() { _state.update { it.copy(exportStatus = null) } }
    fun consumeDeleteStatus() { _state.update { it.copy(deleteStatus = null) } }

    suspend fun setGeminiApiKey(key: String) {
        settingsStore.setGeminiApiKey(key)
    }

    suspend fun setTtsEngine(engine: String) {
        settingsStore.setTtsEngine(engine)
    }

    suspend fun setTtsSpeed(speed: Float) {
        settingsStore.setTtsSpeed(speed)
    }

    fun setSttLanguage(mode: String) {
        viewModelScope.launch { settingsStore.setSttLanguage(mode) }
    }

    class Factory(
        private val app: Application,
        private val settingsStore: SettingsStore,
        private val db: MayaDatabase,
        private val tokenVault: TokenVault,
        private val modelManager: OnDeviceModelManager,
        private val voskModelStore: VoskModelStore,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(SettingsViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return SettingsViewModel(app, settingsStore, db, tokenVault, modelManager, voskModelStore) as T
        }
    }
}

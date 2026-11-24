package com.devaraj.maya.ui.laptop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.local.entity.PcCommandEntity
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.ErrorMapper
import com.devaraj.maya.data.remote.PcCancelRequest
import com.devaraj.maya.data.remote.PcCommandRequest
import com.devaraj.maya.data.remote.PcCommandResponse
import com.devaraj.maya.data.remote.PcConfirmRequest
import com.devaraj.maya.data.remote.apiCall
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

data class PcLogEntry(
    val timeMs: Long = System.currentTimeMillis(),
    val action: String,
    val status: String,
    val message: String,
)

data class LaptopControlUiState(
    val appName: String = "notepad",
    val volumeLevel: Int = 50,
    val clipboardText: String = "",
    val busy: Boolean = false,
    val pendingToken: String? = null,
    val pendingDescription: String? = null,
    val pendingExpiresAtMs: Long? = null,
    val log: List<PcLogEntry> = emptyList(),
    val error: String? = null,
)

class LaptopControlViewModel(
    private val connectionRepository: ConnectionRepository,
    private val apiClient: ApiClient,
    private val db: MayaDatabase,
) : ViewModel() {

    private val _state = MutableStateFlow(LaptopControlUiState())
    val state: StateFlow<LaptopControlUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            db.pcCommandDao().observeRecent(50).collect { entities ->
                val mapped = entities.map { e ->
                    PcLogEntry(
                        timeMs = e.createdAt,
                        action = e.action,
                        status = e.status,
                        message = e.result ?: e.action,
                    )
                }
                _state.update { it.copy(log = mapped) }
            }
        }
    }

    fun setAppName(value: String) {
        _state.update { it.copy(appName = value) }
    }

    fun setVolumeLevel(value: Int) {
        _state.update { it.copy(volumeLevel = value.coerceIn(0, 100)) }
    }

    fun setClipboardText(value: String) {
        _state.update { it.copy(clipboardText = value) }
    }

    fun requestOpenApp() {
        val name = _state.value.appName.trim().ifBlank { "notepad" }
        sendCommand(
            action = "app.open",
            params = mapOf("name" to JsonPrimitive(name)),
            label = "app.open($name)",
        )
    }

    fun requestLock() = sendCommand("system.lock", emptyMap(), "system.lock")
    fun requestSleep() = sendCommand("system.sleep", emptyMap(), "system.sleep")
    fun requestMute() = sendCommand("system.mute", mapOf("mute" to JsonPrimitive(true)), "system.mute")
    fun requestUnmute() = sendCommand("system.mute", mapOf("mute" to JsonPrimitive(false)), "system.unmute")
    fun requestVolume() = sendCommand(
        "system.volume",
        mapOf("level" to JsonPrimitive(_state.value.volumeLevel)),
        "system.volume(${_state.value.volumeLevel})",
    )
    fun requestScreenshot() = sendCommand("system.screenshot", emptyMap(), "system.screenshot")
    fun requestMediaPlay() = sendCommand("media.play", emptyMap(), "media.play")
    fun requestMediaPause() = sendCommand("media.pause", emptyMap(), "media.pause")
    fun requestMediaNext() = sendCommand("media.next", emptyMap(), "media.next")
    fun requestMediaPrev() = sendCommand("media.prev", emptyMap(), "media.prev")
    fun requestNotify() = sendCommand(
        "notify",
        mapOf("title" to JsonPrimitive("Maya"), "body" to JsonPrimitive("Hello from phone")),
        "notify",
    )

    fun requestClipboardSet() {
        val text = _state.value.clipboardText.trim()
        if (text.isBlank()) {
            _state.update { it.copy(error = "Clipboard text is empty") }
            return
        }
        sendCommand("clipboard.set", mapOf("text" to JsonPrimitive(text)), "clipboard.set")
    }

    private fun sendCommand(
        action: String,
        params: Map<String, kotlinx.serialization.json.JsonElement>,
        label: String,
    ) {
        val conn = connectionRepository.state.value
        if (conn !is ConnectionState.Connected) {
            _state.update { it.copy(error = "Not connected to laptop") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val res = apiCall {
                apiClient.api(conn.device.host, conn.device.port)
                    .pcCommand(PcCommandRequest(action = action, params = params))
            }
            res.fold(
                onSuccess = { response -> handleResponse(label, action, params, response) },
                onFailure = { error ->
                    val ex = ErrorMapper.toApiException(error)
                    appendLog(label, "error", ex.message ?: "Request failed")
                    _state.update { it.copy(busy = false, error = ex.message ?: "Request failed") }
                },
            )
        }
    }

    fun confirmPending() {
        val token = _state.value.pendingToken ?: return
        val conn = connectionRepository.state.value
        if (conn !is ConnectionState.Connected) return
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val res = apiCall {
                apiClient.api(conn.device.host, conn.device.port)
                    .pcConfirm(PcConfirmRequest(token))
            }
            res.fold(
                onSuccess = { response ->
                    _state.update { it.copy(pendingToken = null, pendingDescription = null, pendingExpiresAtMs = null) }
                    handleResponse("confirm", "confirm", emptyMap(), response)
                },
                onFailure = { error ->
                    val ex = ErrorMapper.toApiException(error)
                    if (ex.reason == com.devaraj.maya.data.remote.MayaErrorReason.PERMISSION_DENIED ||
                        ex.reason == com.devaraj.maya.data.remote.MayaErrorReason.TOKEN_EXPIRED ||
                        ex.reason == com.devaraj.maya.data.remote.MayaErrorReason.EXPIRED
                    ) {
                        _state.update { it.copy(pendingToken = null, pendingDescription = null, pendingExpiresAtMs = null) }
                    }
                    appendLog("confirm", "error", ex.message ?: "Confirm failed")
                    _state.update { it.copy(busy = false, error = ex.message ?: "Confirm failed") }
                },
            )
        }
    }

    fun cancelPending() {
        val token = _state.value.pendingToken ?: return
        val conn = connectionRepository.state.value
        if (conn !is ConnectionState.Connected) {
            _state.update { it.copy(pendingToken = null, pendingDescription = null, pendingExpiresAtMs = null) }
            return
        }
        viewModelScope.launch {
            try {
                apiClient.api(conn.device.host, conn.device.port).pcCancel(PcCancelRequest(token))
            } catch (_: Exception) {
            }
            _state.update { it.copy(pendingToken = null, pendingDescription = null, pendingExpiresAtMs = null, busy = false) }
            appendLog("cancel", "cancelled", "Action cancelled")
        }
    }

    private fun handleResponse(
        label: String,
        action: String,
        params: Map<String, kotlinx.serialization.json.JsonElement>,
        res: PcCommandResponse,
    ) {
        when (res.status) {
            "needs_confirmation" -> {
                appendLog(label, "needs_confirmation", res.description ?: "Confirmation required")
                _state.update {
                    it.copy(
                        busy = false,
                        pendingToken = res.confirmToken,
                        pendingDescription = res.description ?: "Confirm action?",
                        pendingExpiresAtMs = res.expiresIn?.let { s -> System.currentTimeMillis() + s * 1000L },
                        error = null,
                    )
                }
            }
            "done" -> {
                val msg = res.result?.jsonObject?.get("message")?.jsonPrimitive?.contentOrNull
                    ?: res.result?.toString()
                    ?: "Done"
                appendLog(label, "done", msg)
                _state.update { it.copy(busy = false, error = null) }
                recordPcCommand(action, params, "done", msg)
            }
            "denied" -> {
                appendLog(label, "denied", res.reason ?: "Denied")
                _state.update { it.copy(busy = false, error = res.reason ?: "Denied") }
                recordPcCommand(action, params, "denied", res.reason)
            }
            "cancelled" -> {
                appendLog(label, "cancelled", "Cancelled")
                _state.update { it.copy(busy = false) }
                recordPcCommand(action, params, "cancelled", "Cancelled")
            }
            else -> {
                appendLog(label, res.status, res.reason ?: res.result?.toString() ?: "")
                _state.update { it.copy(busy = false) }
                recordPcCommand(action, params, res.status, res.reason ?: res.result?.toString())
            }
        }
    }

    private fun recordPcCommand(
        action: String,
        params: Map<String, kotlinx.serialization.json.JsonElement>,
        status: String,
        result: String?,
    ) {
        viewModelScope.launch {
            try {
                db.pcCommandDao().insert(
                    PcCommandEntity(
                        id = java.util.UUID.randomUUID().toString(),
                        action = action,
                        paramsJson = params.toString(),
                        status = status,
                        result = result?.take(500),
                        createdAt = System.currentTimeMillis(),
                    ),
                )
            } catch (_: Exception) {
            }
        }
    }

    private fun appendLog(action: String, status: String, message: String) {
        _state.update {
            it.copy(log = (listOf(PcLogEntry(action = action, status = status, message = message)) + it.log).take(50))
        }
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    fun clearPending() {
        _state.update { it.copy(pendingToken = null, pendingDescription = null, pendingExpiresAtMs = null) }
    }

    class Factory(
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
        private val db: MayaDatabase,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(LaptopControlViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return LaptopControlViewModel(connectionRepository, apiClient, db) as T
        }
    }
}

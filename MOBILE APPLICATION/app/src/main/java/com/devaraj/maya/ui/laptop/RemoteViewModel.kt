package com.devaraj.maya.ui.laptop

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.ErrorMapper
import com.devaraj.maya.data.remote.FileEntryDto
import com.devaraj.maya.data.remote.FileListDto
import com.devaraj.maya.data.remote.FileRootsDto
import com.devaraj.maya.data.remote.FileUploadDto
import com.devaraj.maya.data.remote.HybridStatusDto
import com.devaraj.maya.data.remote.InputEventDto
import com.devaraj.maya.data.remote.InputRequest
import com.devaraj.maya.data.remote.InputResponse
import com.devaraj.maya.data.remote.RemoteConfirmRequest
import com.devaraj.maya.data.remote.RemoteSessionDto
import com.devaraj.maya.data.remote.RemoteStartResponse
import com.devaraj.maya.data.remote.RemoteStatusDto
import com.devaraj.maya.data.remote.apiCall
import com.devaraj.maya.domain.model.OperatingMode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

data class RemoteUiState(
    val sessionActive: Boolean = false,
    val sessionToken: String? = null,
    val sessionExpiresIn: Int = 0,
    val busy: Boolean = false,
    val error: String? = null,
    val confirmToken: String? = null,
    val confirmDescription: String? = null,
    val confirmExpiresIn: Int? = null,
    val screenBitmap: Bitmap? = null,
    val screenError: String? = null,
    val screenLoading: Boolean = false,
    val selectedTab: Int = 0,
    val fileRoots: List<String> = emptyList(),
    val filePath: String? = null,
    val fileEntries: List<FileEntryDto> = emptyList(),
    val fileBusy: Boolean = false,
    val fileMessage: String? = null,
    val hybrid: HybridStatusDto? = null,
    val hybridBusy: Boolean = false,
)

class RemoteViewModel(
    private val connectionRepository: ConnectionRepository,
    private val apiClient: ApiClient,
    private val context: Context,
) : ViewModel() {

    private val _state = MutableStateFlow(RemoteUiState())
    val state: StateFlow<RemoteUiState> = _state.asStateFlow()

    private var screenJob: Job? = null
    private var hybridJob: Job? = null
    private var lastMoveSent = 0L
    private var pendingMove: Pair<Float, Float>? = null
    private var moveJob: Job? = null

    init {
        startHybridPolling()
    }

    private fun api() = run {
        val conn = connectionRepository.state.value
        if (conn is ConnectionState.Connected) apiClient.api(conn.device.host, conn.device.port) else null
    }

    private fun connected(): ConnectionState.Connected? =
        connectionRepository.state.value as? ConnectionState.Connected

    fun setOperatingMode(mode: OperatingMode) {
        // kept for future; mode is owned by settings
    }

    fun selectTab(index: Int) {
        _state.update { it.copy(selectedTab = index) }
        if (index == 0 && _state.value.sessionActive) startScreenPolling()
        else if (index != 0) stopScreenPolling()
    }

    fun startSession() {
        val conn = connected() ?: run { _state.update { it.copy(error = "Not connected to laptop") }; return }
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val res = apiCall { apiClient.api(conn.device.host, conn.device.port).remoteStart(com.devaraj.maya.data.remote.RemoteConfirmRequest()) }
            res.fold(
                onSuccess = { r: RemoteStartResponse ->
                    if (r.status == "needs_confirmation") {
                        _state.update {
                            it.copy(
                                busy = false,
                                confirmToken = r.confirmToken,
                                confirmDescription = r.description,
                                confirmExpiresIn = r.expiresIn,
                            )
                        }
                    } else if (r.status == "done" && r.sessionToken != null) {
                        _state.update {
                            it.copy(
                                busy = false,
                                sessionActive = true,
                                sessionToken = r.sessionToken,
                                sessionExpiresIn = r.expiresIn ?: 300,
                                confirmToken = null,
                                confirmDescription = null,
                                confirmExpiresIn = null,
                                error = null,
                            )
                        }
                        startScreenPolling()
                        loadRoots()
                        viewModelScope.launch {
                            runCatching { apiClient.api(conn.device.host, conn.device.port).hybridTakeover() }
                                .onSuccess { h -> _state.update { it.copy(hybrid = h) } }
                        }
                    } else {
                        _state.update { it.copy(busy = false, error = "Unexpected response") }
                    }
                },
                onFailure = { e ->
                    val ex = ErrorMapper.toApiException(e)
                    _state.update { it.copy(busy = false, error = ex.message ?: "Start failed") }
                },
            )
        }
    }

    fun confirmSession() {
        val token = _state.value.confirmToken ?: return
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val res = apiCall {
                apiClient.api(conn.device.host, conn.device.port)
                    .remoteStart(com.devaraj.maya.data.remote.RemoteConfirmRequest(token))
            }
            res.fold(
                onSuccess = { r: RemoteStartResponse ->
                    if (r.status == "done" && r.sessionToken != null) {
                        _state.update {
                            it.copy(
                                busy = false,
                                sessionActive = true,
                                sessionToken = r.sessionToken,
                                sessionExpiresIn = r.expiresIn ?: 300,
                                confirmToken = null,
                                confirmDescription = null,
                                confirmExpiresIn = null,
                            )
                        }
                        startScreenPolling()
                        loadRoots()
                        viewModelScope.launch {
                            runCatching { apiClient.api(conn.device.host, conn.device.port).hybridTakeover() }
                                .onSuccess { h -> _state.update { it.copy(hybrid = h) } }
                        }
                    } else {
                        _state.update { it.copy(busy = false, error = r.description ?: "Confirmation failed") }
                    }
                },
                onFailure = { e ->
                    val ex = ErrorMapper.toApiException(e)
                    _state.update { it.copy(busy = false, error = ex.message ?: "Confirmation failed", confirmToken = null) }
                },
            )
        }
    }

    fun cancelConfirm() {
        _state.update { it.copy(confirmToken = null, confirmDescription = null, confirmExpiresIn = null) }
    }

    fun stopSession() {
        val token = _state.value.sessionToken ?: run { clearSession(); return }
        val conn = connected()
        stopScreenPolling()
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            if (conn != null) {
                runCatching { apiClient.api(conn.device.host, conn.device.port).remoteStop(com.devaraj.maya.data.remote.RemoteStopRequest(token)) }
                runCatching { apiClient.api(conn.device.host, conn.device.port).hybridRelease() }
            }
            clearSession()
            _state.update { it.copy(busy = false) }
        }
    }

    private fun clearSession() {
        _state.update {
            it.copy(
                sessionActive = false,
                sessionToken = null,
                sessionExpiresIn = 0,
                screenBitmap = null,
                screenError = null,
                filePath = null,
                fileEntries = emptyList(),
                fileRoots = emptyList(),
                fileMessage = null,
            )
        }
    }

    // ---- screen polling ----

    fun startScreenPolling() {
        stopScreenPolling()
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        screenJob = viewModelScope.launch {
            var errors = 0
            while (isActive && _state.value.sessionActive && _state.value.selectedTab == 0) {
                val res = apiCall { apiClient.api(conn.device.host, conn.device.port).screen(token, 1280, 60) }
                res.fold(
                    onSuccess = { body ->
                        errors = 0
                        try {
                            val bmp = withContext(Dispatchers.IO) {
                                body.use { b ->
                                    val bytes = b.bytes()
                                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                                }
                            }
                            _state.update { it.copy(screenBitmap = bmp, screenError = null, screenLoading = false, sessionExpiresIn = it.sessionExpiresIn) }
                        } catch (io: IOException) {
                            _state.update { it.copy(screenError = io.message) }
                        }
                    },
                    onFailure = { e ->
                        errors++
                        val ex = ErrorMapper.toApiException(e)
                        _state.update { it.copy(screenError = ex.message) }
                    },
                )
                val delayMs = if (errors == 0) 800L else (800L * (1L shl errors.coerceAtMost(3))).coerceAtMost(5000L)
                delay(delayMs)
            }
        }
    }

    fun stopScreenPolling() {
        screenJob?.cancel()
        screenJob = null
    }

    // ---- input ----

    private fun sendInput(events: List<InputEventDto>) {
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        viewModelScope.launch {
            runCatching {
                apiClient.api(conn.device.host, conn.device.port)
                    .input(com.devaraj.maya.data.remote.InputRequest(token, events))
            }
        }
    }

    fun sendMove(nx: Float, ny: Float) {
        val now = System.currentTimeMillis()
        if (now - lastMoveSent >= 80) {
            lastMoveSent = now
            sendInput(listOf(InputEventDto(type = "move", x = nx, y = ny)))
        } else {
            pendingMove = nx to ny
            if (moveJob == null) {
                moveJob = viewModelScope.launch {
                    delay(80)
                    val p = pendingMove
                    pendingMove = null
                    moveJob = null
                    if (p != null) {
                        lastMoveSent = System.currentTimeMillis()
                        sendInput(listOf(InputEventDto(type = "move", x = p.first, y = p.second)))
                    }
                }
            }
        }
    }

    fun click(button: String = "left") {
        sendInput(listOf(InputEventDto(type = "click", button = button)))
    }

    fun scroll(dy: Int) {
        sendInput(listOf(InputEventDto(type = "scroll", dy = dy)))
    }

    fun sendKey(key: String) {
        sendInput(listOf(InputEventDto(type = "key", key = key)))
    }

    fun sendText(text: String) {
        if (text.isBlank()) return
        sendInput(listOf(InputEventDto(type = "text", text = text)))
    }

    // ---- files ----

    fun loadRoots() {
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(fileBusy = true, fileMessage = null) }
            val res = apiCall { apiClient.api(conn.device.host, conn.device.port).fileRoots(token) }
            res.fold(
                onSuccess = { r: FileRootsDto ->
                    val first = r.roots.firstOrNull()
                    _state.update { it.copy(fileRoots = r.roots, filePath = first, fileBusy = false) }
                    if (first != null) listPath(first)
                },
                onFailure = { e ->
                    val ex = ErrorMapper.toApiException(e)
                    _state.update { it.copy(fileBusy = false, fileMessage = ex.message ?: "Could not load roots") }
                },
            )
        }
    }

    fun listPath(path: String) {
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(fileBusy = true, fileMessage = null) }
            val res = apiCall { apiClient.api(conn.device.host, conn.device.port).fileList(token, path) }
            res.fold(
                onSuccess = { r: FileListDto ->
                    _state.update { it.copy(filePath = r.path, fileEntries = r.entries, fileBusy = false) }
                },
                onFailure = { e ->
                    val ex = ErrorMapper.toApiException(e)
                    _state.update { it.copy(fileBusy = false, fileMessage = ex.message ?: "Could not list folder") }
                },
            )
        }
    }

    fun goUp() {
        val current = _state.value.filePath ?: return
        val parent = current.trimEnd('\\', '/').substringBeforeLast('\\').substringBeforeLast('/')
        if (parent.isNotBlank() && parent != current) listPath(parent)
    }

    fun download(path: String, destination: android.net.Uri) {
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(fileBusy = true, fileMessage = null) }
            val res = apiCall { apiClient.api(conn.device.host, conn.device.port).fileDownload(token, path) }
            res.fold(
                onSuccess = { body ->
                    try {
                        withContext(Dispatchers.IO) {
                            context.contentResolver.openOutputStream(destination)?.use { out ->
                                body.byteStream().use { input -> input.copyTo(out) }
                            }
                        }
                        _state.update { it.copy(fileBusy = false, fileMessage = "Downloaded") }
                    } catch (io: IOException) {
                        _state.update { it.copy(fileBusy = false, fileMessage = io.message ?: "Download failed") }
                    }
                },
                onFailure = { e ->
                    val ex = ErrorMapper.toApiException(e)
                    _state.update { it.copy(fileBusy = false, fileMessage = ex.message ?: "Download failed") }
                },
            )
        }
    }

    fun upload(source: android.net.Uri, targetName: String? = null) {
        val token = _state.value.sessionToken ?: return
        val conn = connected() ?: return
        val folder = _state.value.filePath ?: return
        viewModelScope.launch {
            _state.update { it.copy(fileBusy = true, fileMessage = null) }
            try {
                val bytes = context.contentResolver.openInputStream(source)?.use { it.readBytes() }
                    ?: throw IOException("Cannot read file")
                if (bytes.size > 25 * 1024 * 1024) {
                    _state.update { it.copy(fileBusy = false, fileMessage = "File too large (25 MB max)") }
                    return@launch
                }
                val name = targetName ?: (source.lastPathSegment?.substringAfterLast('/') ?: "upload.bin")
                val target = "$folder\\$name".replace('/', '\\')
                val res = apiCall {
                    apiClient.api(conn.device.host, conn.device.port)
                        .fileUpload(token, target, bytes.toRequestBody("application/octet-stream".toMediaTypeOrNull()))
                }
                res.fold(
                    onSuccess = { r: FileUploadDto ->
                        _state.update { it.copy(fileBusy = false, fileMessage = "Uploaded ${r.size} bytes") }
                        listPath(folder)
                    },
                    onFailure = { e ->
                        val ex = ErrorMapper.toApiException(e)
                        _state.update { it.copy(fileBusy = false, fileMessage = ex.message ?: "Upload failed") }
                    },
                )
            } catch (io: IOException) {
                _state.update { it.copy(fileBusy = false, fileMessage = io.message ?: "Upload failed") }
            }
        }
    }

    // ---- hybrid ----

    private fun startHybridPolling() {
        hybridJob?.cancel()
        hybridJob = viewModelScope.launch {
            while (isActive) {
                val conn = connected()
                if (conn != null) {
                    runCatching { apiClient.api(conn.device.host, conn.device.port).hybridStatus() }
                        .onSuccess { h -> _state.update { it.copy(hybrid = h) } }
                }
                delay(5000)
            }
        }
    }

    fun hybridTakeover() {
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(hybridBusy = true) }
            runCatching { apiClient.api(conn.device.host, conn.device.port).hybridTakeover() }
                .onSuccess { h -> _state.update { it.copy(hybrid = h, hybridBusy = false) } }
                .onFailure { _state.update { it.copy(hybridBusy = false) } }
        }
    }

    fun hybridRelease() {
        val conn = connected() ?: return
        viewModelScope.launch {
            _state.update { it.copy(hybridBusy = true) }
            runCatching { apiClient.api(conn.device.host, conn.device.port).hybridRelease() }
                .onSuccess { h -> _state.update { it.copy(hybrid = h, hybridBusy = false) } }
                .onFailure { _state.update { it.copy(hybridBusy = false) } }
        }
    }

    fun clearError() {
        _state.update { it.copy(error = null, fileMessage = null, screenError = null) }
    }

    override fun onCleared() {
        super.onCleared()
        stopScreenPolling()
        hybridJob?.cancel()
        moveJob?.cancel()
    }

    class Factory(
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
        private val context: Context,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(RemoteViewModel::class.java))
            return RemoteViewModel(connectionRepository, apiClient, context) as T
        }
    }
}

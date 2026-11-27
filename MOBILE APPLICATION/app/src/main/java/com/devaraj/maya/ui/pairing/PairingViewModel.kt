package com.devaraj.maya.ui.pairing

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.discovery.DiscoveredLaptop
import com.devaraj.maya.data.discovery.LaptopDiscovery
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.MayaApiException
import com.devaraj.maya.data.remote.MayaErrorReason
import com.devaraj.maya.data.remote.PairingRepository
import com.devaraj.maya.data.remote.QrPayload
import com.devaraj.maya.data.secure.DeviceIdentity
import com.devaraj.maya.domain.model.Device
import com.devaraj.maya.p2p.P2pManager
import com.devaraj.maya.p2p.P2pState
import com.devaraj.maya.p2p.P2pTurn
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json

enum class PairingStep { FIND, PIN, CLAIMING, SUCCESS }

data class PairingUiState(
    val step: PairingStep = PairingStep.FIND,
    val host: String = "",
    val port: String = "8420",
    val pin: String = "",
    val laptops: List<DiscoveredLaptop> = emptyList(),
    val discovering: Boolean = true,
    val errorReason: MayaErrorReason? = null,
    val errorMessage: String? = null,
    val paired: Device? = null,
    val p2pState: P2pState = P2pState.NEW,
    val p2pPayload: String = "",
    val p2pError: String? = null,
    val p2pTurnHost: String = "",
    val p2pTurnUsername: String = "",
    val p2pTurnCredential: String = "",
) {
    val p2pTurnConfigured: Boolean
        get() = p2pTurnHost.isNotBlank() &&
            p2pTurnUsername.isNotBlank() &&
            p2pTurnCredential.isNotBlank()

    val p2pTurnEditable: Boolean
        get() = p2pState == P2pState.NEW || p2pState == P2pState.CLOSED
}

class PairingViewModel(
    private val pairingRepository: PairingRepository,
    private val connectionRepository: ConnectionRepository,
    private val deviceIdentity: DeviceIdentity,
    private val discovery: LaptopDiscovery,
    private val settingsStore: SettingsStore,
    private val context: Context,
) : ViewModel() {

    private val _state = MutableStateFlow(PairingUiState())
    val state: StateFlow<PairingUiState> = _state.asStateFlow()

    private val json = Json { ignoreUnknownKeys = true }
    private var discoveryJob: Job? = null
    private var p2pManager: P2pManager? = null
    private var p2pStateJob: Job? = null
    private var p2pMessagesJob: Job? = null
    private var p2pActionJob: Job? = null

    init {
        viewModelScope.launch {
            val settings = settingsStore.settings.first()
            val preferredHost = if (settings.connectionMode == "usb") {
                "127.0.0.1"
            } else {
                settings.laptopHost
            }
            _state.update { current ->
                if (current.host.isBlank() && preferredHost.isNotBlank()) {
                    current.copy(host = preferredHost, port = settings.laptopPort.toString())
                } else {
                    current
                }
            }
        }
    }

    fun startDiscovery() {
        discoveryJob?.cancel()
        _state.update { it.copy(discovering = true) }
        discoveryJob = viewModelScope.launch {
            discovery.discover()
                .catch { _state.update { it.copy(discovering = false) } }
                .collect { laptop ->
                    _state.update { current ->
                        if (current.laptops.any { it.host == laptop.host && it.port == laptop.port }) {
                            current
                        } else {
                            current.copy(laptops = current.laptops + laptop, discovering = false)
                        }
                    }
                }
        }
    }

    fun onHostChange(host: String) {
        _state.update { it.copy(host = host.trim(), errorReason = null, errorMessage = null) }
    }

    fun onPortChange(port: String) {
        if (port.all(Char::isDigit) && port.length <= 5) {
            _state.update { it.copy(port = port, errorReason = null, errorMessage = null) }
        }
    }

    fun selectLaptop(laptop: DiscoveredLaptop) {
        _state.update {
            it.copy(
                host = laptop.host,
                port = laptop.port.toString(),
                step = PairingStep.PIN,
                errorReason = null,
                errorMessage = null,
            )
        }
    }

    fun continueWithManualHost() {
        val current = _state.value
        if (current.host.isBlank()) {
            _state.update { it.copy(errorMessage = "Enter the laptop IP address") }
            return
        }
        _state.update { it.copy(step = PairingStep.PIN, errorReason = null, errorMessage = null) }
    }

    fun onPinChange(pin: String) {
        val digits = pin.filter(Char::isDigit).take(PIN_LENGTH)
        _state.update {
            it.copy(
                pin = digits,
                errorReason = null,
                errorMessage = null,
            )
        }
    }

    fun submitPin() {
        val current = _state.value
        if (current.step != PairingStep.PIN || current.pin.length != PIN_LENGTH) return
        val port = current.port.toIntOrNull() ?: return
        if (current.host.isBlank()) return

        viewModelScope.launch {
            _state.update { it.copy(step = PairingStep.CLAIMING) }
            val deviceId = deviceIdentity.deviceId()
            val result = pairingRepository.claimPin(
                host = current.host,
                port = port,
                pin = current.pin,
                deviceId = deviceId,
                deviceName = deviceIdentity.deviceName(),
            )
            handleClaim(result)
        }
    }

    fun claimQr(raw: String) {
        val payload = try {
            json.decodeFromString(QrPayload.serializer(), raw)
        } catch (_: Exception) {
            _state.update { it.copy(errorMessage = "Invalid QR code") }
            return
        }
        if (payload.v != 1 || payload.h.isBlank() || payload.t.isBlank()) {
            _state.update { it.copy(errorMessage = "Unsupported QR code") }
            return
        }

        viewModelScope.launch {
            _state.update {
                it.copy(
                    step = PairingStep.CLAIMING,
                    host = payload.h,
                    port = payload.p.toString(),
                    errorReason = null,
                    errorMessage = null,
                )
            }
            val deviceId = deviceIdentity.deviceId()
            val result = pairingRepository.claimQr(
                payload = payload,
                deviceId = deviceId,
                deviceName = deviceIdentity.deviceName(),
            )
            handleClaim(result)
        }
    }

    private suspend fun handleClaim(result: Result<Device>) {
        result.fold(
            onSuccess = { device ->
                discoveryJob?.cancel()
                val mode = settingsStore.settings.first().connectionMode
                if (mode != "usb") {
                    settingsStore.setLaptop(device.host, device.port)
                }
                _state.update {
                    it.copy(
                        step = PairingStep.SUCCESS,
                        paired = device,
                        discovering = false,
                        errorReason = null,
                        errorMessage = null,
                    )
                }
                // Health check is best-effort; the Laptop tab exposes retry.
                connectionRepository.connect(
                    device,
                    hostOverride = if (mode == "usb") "127.0.0.1" else null,
                )
            },
            onFailure = { error ->
                val mapped = error as? MayaApiException
                _state.update {
                    it.copy(
                        step = PairingStep.PIN,
                        pin = "",
                        errorReason = mapped?.reason ?: MayaErrorReason.UNKNOWN,
                        errorMessage = mapped?.message ?: "Pairing failed",
                    )
                }
            },
        )
    }

    fun backToFind() {
        _state.update {
            it.copy(
                step = PairingStep.FIND,
                pin = "",
                errorReason = null,
                errorMessage = null,
            )
        }
    }

    fun clearError() {
        _state.update { it.copy(errorReason = null, errorMessage = null) }
    }

    fun createP2pOffer() {
        launchP2pAction { manager ->
            _state.update { it.copy(p2pPayload = manager.createOffer()) }
        }
    }

    fun acceptP2pOffer(text: String) {
        val offer = text.trim()
        if (offer.isEmpty()) {
            _state.update { it.copy(p2pError = "Paste an offer first") }
            return
        }
        launchP2pAction { manager ->
            _state.update { it.copy(p2pPayload = manager.acceptOffer(offer)) }
        }
    }

    fun acceptP2pAnswer(text: String) {
        val answer = text.trim()
        if (answer.isEmpty()) {
            _state.update { it.copy(p2pError = "Paste an answer first") }
            return
        }
        launchP2pAction { manager ->
            manager.acceptAnswer(answer)
            _state.update { it.copy(p2pPayload = "") }
        }
    }

    fun closeP2p() {
        val closeError = disposeP2p()
        _state.update {
            it.copy(
                p2pState = P2pState.CLOSED,
                p2pPayload = "",
                p2pError = closeError,
            )
        }
    }

    fun onP2pTurnHostChange(value: String) {
        _state.update { it.copy(p2pTurnHost = value, p2pError = null) }
    }

    fun onP2pTurnUsernameChange(value: String) {
        _state.update { it.copy(p2pTurnUsername = value, p2pError = null) }
    }

    fun onP2pTurnCredentialChange(value: String) {
        _state.update { it.copy(p2pTurnCredential = value, p2pError = null) }
    }

    private fun launchP2pAction(action: suspend (P2pManager) -> Unit) {
        val manager = ensureP2pManager() ?: return
        p2pActionJob?.cancel()
        p2pActionJob = viewModelScope.launch {
            _state.update { it.copy(p2pError = null, p2pPayload = "") }
            try {
                action(manager)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                _state.update {
                    it.copy(p2pError = error.message ?: "P2P operation failed")
                }
            }
        }
    }

    private fun ensureP2pManager(): P2pManager? {
        p2pManager?.let { return it }
        val current = _state.value
        // No relay is configured unless the user supplies all TURN fields.
        val turn = if (current.p2pTurnConfigured) {
            P2pTurn(
                host = current.p2pTurnHost.trim(),
                username = current.p2pTurnUsername.trim(),
                credential = current.p2pTurnCredential,
            )
        } else {
            null
        }

        val manager = try {
            P2pManager(context = context.applicationContext, stunServers = STUN_SERVERS, turn = turn)
        } catch (error: Exception) {
            _state.update { it.copy(p2pError = error.message ?: "P2P is unavailable") }
            return null
        }
        p2pManager = manager

        p2pStateJob = viewModelScope.launch {
            manager.state
                .catch { error ->
                    _state.update { it.copy(p2pError = error.message ?: "P2P state error") }
                }
                .collect { p2pState ->
                    _state.update { currentState ->
                        currentState.copy(
                            p2pState = p2pState,
                            p2pError = when (p2pState) {
                                P2pState.FAILED -> currentState.p2pError ?: "P2P connection failed"
                                P2pState.NEW, P2pState.CLOSED -> null
                                else -> currentState.p2pError
                            },
                        )
                    }
                }
        }
        p2pMessagesJob = viewModelScope.launch {
            manager.messages
                .catch { error ->
                    _state.update { it.copy(p2pError = error.message ?: "P2P message error") }
                }
                .collect { message ->
                    // Display only: no received payload is ever treated as a command.
                    _state.update { it.copy(p2pPayload = message.payload) }
                }
        }
        return manager
    }

    /** Returns a close error message, if any. Never throws while tearing down. */
    private fun disposeP2p(): String? {
        p2pActionJob?.cancel()
        p2pStateJob?.cancel()
        p2pMessagesJob?.cancel()
        p2pActionJob = null
        p2pStateJob = null
        p2pMessagesJob = null
        val manager = p2pManager
        p2pManager = null
        return manager?.let { runCatching { it.close() }.exceptionOrNull()?.message }
    }

    fun stopDiscovery() {
        discoveryJob?.cancel()
        discoveryJob = null
        _state.update { it.copy(discovering = false) }
    }

    /** Called when leaving the pairing flow so the next visit starts clean. */
    fun reset() {
        stopDiscovery()
        closeP2p()
        _state.value = PairingUiState(discovering = false)
    }

    override fun onCleared() {
        discoveryJob?.cancel()
        disposeP2p()
        super.onCleared()
    }

    class Factory(
        private val pairingRepository: PairingRepository,
        private val connectionRepository: ConnectionRepository,
        private val deviceIdentity: DeviceIdentity,
        private val discovery: LaptopDiscovery,
        private val settingsStore: SettingsStore,
        private val context: Context,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(PairingViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return PairingViewModel(
                pairingRepository,
                connectionRepository,
                deviceIdentity,
                discovery,
                settingsStore,
                context,
            ) as T
        }
    }

    companion object {
        const val PIN_LENGTH = 6

        private val STUN_SERVERS = listOf(
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302",
        )
    }
}

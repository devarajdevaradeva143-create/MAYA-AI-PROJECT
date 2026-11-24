package com.devaraj.maya.ui.pairing

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
)

class PairingViewModel(
    private val pairingRepository: PairingRepository,
    private val connectionRepository: ConnectionRepository,
    private val deviceIdentity: DeviceIdentity,
    private val discovery: LaptopDiscovery,
    private val settingsStore: SettingsStore,
) : ViewModel() {

    private val _state = MutableStateFlow(PairingUiState())
    val state: StateFlow<PairingUiState> = _state.asStateFlow()

    private val json = Json { ignoreUnknownKeys = true }
    private var discoveryJob: Job? = null

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

    fun stopDiscovery() {
        discoveryJob?.cancel()
        discoveryJob = null
        _state.update { it.copy(discovering = false) }
    }

    /** Called when leaving the pairing flow so the next visit starts clean. */
    fun reset() {
        stopDiscovery()
        _state.value = PairingUiState(discovering = false)
    }

    override fun onCleared() {
        discoveryJob?.cancel()
        super.onCleared()
    }

    class Factory(
        private val pairingRepository: PairingRepository,
        private val connectionRepository: ConnectionRepository,
        private val deviceIdentity: DeviceIdentity,
        private val discovery: LaptopDiscovery,
        private val settingsStore: SettingsStore,
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
            ) as T
        }
    }

    companion object {
        const val PIN_LENGTH = 6
    }
}

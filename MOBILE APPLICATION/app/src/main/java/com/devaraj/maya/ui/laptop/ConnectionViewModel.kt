package com.devaraj.maya.ui.laptop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.PairingRepository
import com.devaraj.maya.domain.model.Device
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Laptop tab state + app-start auto-connect (plan §14.2). Auto-connect only
 * runs when the user enabled it on the saved device. The active connection
 * mode decides the host: USB always uses 127.0.0.1 (adb reverse).
 */
class ConnectionViewModel(
    private val connectionRepository: ConnectionRepository,
    private val pairingRepository: PairingRepository,
    private val settingsStore: SettingsStore,
) : ViewModel() {

    val connection: StateFlow<ConnectionState> = connectionRepository.state

    val devices: StateFlow<List<Device>> = connectionRepository.observeDevices()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        viewModelScope.launch {
            val last = connectionRepository.lastDevice()
            if (last?.autoConnect == true) {
                connectionRepository.connectWithRetry(last, hostFor(last))
            }
        }
    }

    fun connect() {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice() ?: return@launch
            connectionRepository.connect(device, hostFor(device))
        }
    }

    fun forgetLaptop() {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice()
            if (device != null) pairingRepository.forgetLocal(device.id)
            connectionRepository.clearSession()
        }
    }

    /**
     * USB mode: `adb reverse tcp:8420 tcp:8420` exposes the laptop on the
     * phone's loopback. In Wi-Fi/Bluetooth mode a device paired over USB
     * (host 127.0.0.1) falls back to the saved LAN address.
     */
    private suspend fun hostFor(device: Device): String? {
        val settings = settingsStore.settings.first()
        return when {
            settings.connectionMode == "usb" -> "127.0.0.1"
            device.host == "127.0.0.1" && settings.laptopHost.isNotBlank() -> settings.laptopHost
            else -> null
        }
    }

    fun setAutoConnect(enabled: Boolean) {
        viewModelScope.launch {
            val device = devices.value.firstOrNull() ?: connectionRepository.lastDevice() ?: return@launch
            connectionRepository.setAutoConnect(device.id, enabled)
        }
    }

    class Factory(
        private val connectionRepository: ConnectionRepository,
        private val pairingRepository: PairingRepository,
        private val settingsStore: SettingsStore,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(ConnectionViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return ConnectionViewModel(connectionRepository, pairingRepository, settingsStore) as T
        }
    }
}

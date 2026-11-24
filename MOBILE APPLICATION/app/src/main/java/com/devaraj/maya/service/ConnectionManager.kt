package com.devaraj.maya.service

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Connection Manager - handles all connection modes:
 * LAN (WiFi), USB (adb reverse), Bluetooth PAN, WAN (relay)
 */
class ConnectionManager(
    private val context: Context
) {
    private val _currentMode = MutableStateFlow<ConnectionMode>(ConnectionMode.LAN)
    val currentMode = _currentMode.asStateFlow()

    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val connectionState = _connectionState.asStateFlow()

    private val bluetoothRemote = BluetoothRemoteService(context)
    private var wanRemote: WanRemoteClient? = null

    private val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    enum class ConnectionMode {
        LAN,       // WiFi / Ethernet
        USB,       // adb reverse
        BLUETOOTH, // Bluetooth PAN
        WAN        // Internet relay
    }

    sealed interface ConnectionState {
        data object Disconnected : ConnectionState
        data class Connecting(val mode: ConnectionMode) : ConnectionState
        data class Connected(val mode: ConnectionMode, val host: String, val port: Int) : ConnectionState
        data class Error(val mode: ConnectionMode, val message: String) : ConnectionState
    }

    init {
        observeNetwork()
    }

    /**
     * Switch connection mode
     */
    fun setMode(mode: ConnectionMode, config: ModeConfig? = null) {
        if (mode == _currentMode.value) return

        // Disconnect current
        disconnect()

        _currentMode.value = mode
        _connectionState.value = ConnectionState.Connecting(mode)

        CoroutineScope(Dispatchers.IO).launch {
            try {
                when (mode) {
                    ConnectionMode.LAN -> connectLan()
                    ConnectionMode.USB -> connectUsb()
                    ConnectionMode.BLUETOOTH -> connectBluetooth()
                    ConnectionMode.WAN -> connectWan(config as WanConfig)
                }
            } catch (e: Exception) {
                Log.e("ConnectionMgr", "Failed to connect $mode", e)
                _connectionState.value = ConnectionState.Error(mode, e.message ?: "Unknown error")
            }
        }
    }

    /**
     * LAN connection - uses existing pairing + phone server discovery
     */
    private fun connectLan() {
        // Handled by existing ConnectionRepository + NSD discovery
        // This just updates state
        _connectionState.value = ConnectionState.Connected(ConnectionMode.LAN, "auto", 8420)
    }

    /**
     * USB connection - adb reverse
     * Requires: adb reverse tcp:8420 tcp:8420 (laptop)
     * Phone connects to 127.0.0.1:8420
     */
    private fun connectUsb() {
        // Phone connects to localhost via adb reverse tunnel
        // Laptop runs: adb reverse tcp:8420 tcp:8420
        // This is manual setup, we just update state
        _connectionState.value = ConnectionState.Connected(ConnectionMode.USB, "127.0.0.1", 8420)
    }

    /**
     * Bluetooth PAN connection
     */
    private fun connectBluetooth() {
        if (!bluetoothRemote.isPanAvailable()) {
            throw IllegalStateException("Bluetooth PAN not available")
        }

        // Start PAN server (phone as PANU)
        bluetoothRemote.startPanServer()
        bluetoothRemote.startRfcommServer()

        // For laptop-initiated connection, laptop connects to phone PAN
        // Phone just needs to be discoverable and PAN server running
        _connectionState.value = ConnectionState.Connected(
            ConnectionMode.BLUETOOTH,
            "pan", // link-local IP assigned by PAN
            8421
        )
    }

    /**
     * WAN connection via relay server
     */
    private fun connectWan(config: WanConfig) {
        wanRemote = WanRemoteClient(
            context = context,
            relayUrl = config.relayUrl,
            certPinSha256 = config.certPinSha256,
            pairingToken = config.pairingToken
        )

        wanRemote?.connect()
    }

    /**
     * Disconnect current mode
     */
    fun disconnect() {
        when (_currentMode.value) {
            ConnectionMode.BLUETOOTH -> bluetoothRemote.stop()
            ConnectionMode.WAN -> wanRemote?.disconnect()
            else -> {}
        }
        _connectionState.value = ConnectionState.Disconnected
    }

    /**
     * Get current host/port for API calls
     */
    fun getCurrentEndpoint(): Pair<String, Int> {
        return when (_currentMode.value) {
            ConnectionMode.LAN -> Pair("auto", 8420) // Handled by NSD
            ConnectionMode.USB -> Pair("127.0.0.1", 8420)
            ConnectionMode.BLUETOOTH -> Pair("192.168.44.1", 8421) // PAN gateway
            ConnectionMode.WAN -> Pair("wan", 443) // Via relay
        }
    }

    /**
     * Observe network changes for auto-failover
     */
    private fun observeNetwork() {
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()

        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: android.net.Network) {
                // Network available - check if we should failover
            }

            override fun onLost(network: android.net.Network) {
                // Network lost - trigger WAN failover if enabled
                if (_currentMode.value == ConnectionMode.LAN) {
                    // TODO: Implement LAN→WAN handoff
                }
            }
        }

        connectivityManager.registerNetworkCallback(request, networkCallback!!)
    }

    fun shutdown() {
        networkCallback?.let { connectivityManager.unregisterNetworkCallback(it) }
        disconnect()
    }

    open class ModeConfig

    data class WanConfig(
        val relayUrl: String,
        val certPinSha256: String,
        val pairingToken: String,
    ) : ModeConfig()
}
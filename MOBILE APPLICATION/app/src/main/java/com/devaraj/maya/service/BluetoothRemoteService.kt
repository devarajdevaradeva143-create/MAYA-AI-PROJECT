package com.devaraj.maya.service

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Bluetooth PAN Remote Service
 * 
 * Phone acts as PANU (PAN User) - provides network via Bluetooth tethering
 * Laptop connects as NAP (Network Access Point)
 * Fallback: RFCOMM for legacy devices
 */
class BluetoothRemoteService(
    private val context: Context
) {
    private val _state = MutableStateFlow<BluetoothState>(BluetoothState.Disconnected)
    val state = _state.asStateFlow()

    private val bluetoothAdapter = BluetoothAdapter.getDefaultAdapter()
    private val bluetoothManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager

    private var panServerSocket: BluetoothServerSocket? = null
    private var rfcommServerSocket: BluetoothServerSocket? = null
    private var activeConnections = mutableMapOf<String, BluetoothConnection>()

    private val connectionEvents = Channel<BluetoothEvent>(100)

    // PAN UUIDs
    private val PAN_UUID: UUID = UUID.fromString("00001115-0000-1000-8000-00805f9b34fb") // PANU
    private val NAP_UUID: UUID = UUID.fromString("00001116-0000-1000-8000-00805f9b34fb") // NAP
    private val RFCOMM_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb") // SPP

    companion object {
        const val PAN_PORT = 8420
        const val RFCOMM_PORT = 8421
    }

    /**
     * Start Bluetooth PAN server (phone as PANU)
     */
    fun startPanServer() {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            _state.value = BluetoothState.Error("Bluetooth not available or disabled")
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Start PAN server socket (Android exposes PAN over RFCOMM only)
                @Suppress("DEPRECATION")
                panServerSocket = bluetoothAdapter
                    .listenUsingInsecureRfcommWithServiceRecord("Maya PAN", PAN_UUID)

                _state.value = BluetoothState.Listening("PAN")

                while (true) {
                    val socket = panServerSocket?.accept() ?: break
                    handleConnection(socket, "PAN")
                }
            } catch (e: Exception) {
                Log.e("BluetoothRemote", "PAN server error", e)
                _state.value = BluetoothState.Error(e.message ?: "PAN server failed")
            }
        }
    }

    /**
     * Start RFCOMM server (fallback for legacy devices)
     */
    fun startRfcommServer() {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            return
        }

        CoroutineScope(Dispatchers.IO).launch {
            try {
                @Suppress("DEPRECATION")
                rfcommServerSocket = bluetoothAdapter
                    .listenUsingInsecureRfcommWithServiceRecord("Maya RFCOMM", RFCOMM_UUID)

                while (true) {
                    val socket = rfcommServerSocket?.accept() ?: break
                    handleConnection(socket, "RFCOMM")
                }
            } catch (e: Exception) {
                Log.e("BluetoothRemote", "RFCOMM server error", e)
            }
        }
    }

    /**
     * Handle incoming connection
     */
    private fun handleConnection(socket: BluetoothSocket, type: String) {
        val connection = BluetoothConnection(socket, type)
        activeConnections[socket.remoteDevice.address] = connection

        CoroutineScope(Dispatchers.IO).launch {
            connectionEvents.send(BluetoothEvent.Connected(socket.remoteDevice))
            connection.readLoop { data ->
                connectionEvents.trySend(BluetoothEvent.Data(socket.remoteDevice, data))
            }
            connectionEvents.send(BluetoothEvent.Disconnected(socket.remoteDevice))
            activeConnections.remove(socket.remoteDevice.address)
        }
    }

    /**
     * Connect to laptop's PAN (phone as PANU, laptop as NAP)
     * This is for phone-initiated connection
     */
    fun connectToLaptop(device: BluetoothDevice) {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            _state.value = BluetoothState.Error("Bluetooth not available")
            return
        }

        _state.value = BluetoothState.Connecting(device.name ?: device.address)

        CoroutineScope(Dispatchers.IO).launch {
            try {
                @Suppress("DEPRECATION")
                val socket = device.createInsecureRfcommSocketToServiceRecord(PAN_UUID)

                socket.connect()
                val connection = BluetoothConnection(socket, "PAN")
                activeConnections[device.address] = connection

                _state.value = BluetoothState.Connected(device.name ?: device.address)

                connection.readLoop { data ->
                    connectionEvents.trySend(BluetoothEvent.Data(device, data))
                }
                connectionEvents.send(BluetoothEvent.Disconnected(device))
                activeConnections.remove(device.address)

            } catch (e: Exception) {
                Log.e("BluetoothRemote", "Connect failed", e)
                _state.value = BluetoothState.Error(e.message ?: "Connection failed")
            }
        }
    }

    /**
     * Send data to connected device
     */
    fun sendData(address: String, data: ByteArray) {
        activeConnections[address]?.send(data)
    }

    /**
     * Stop all connections
     */
    fun stop() {
        activeConnections.values.forEach { it.close() }
        activeConnections.clear()
        panServerSocket?.close()
        rfcommServerSocket?.close()
        _state.value = BluetoothState.Disconnected
    }

    /**
     * Get paired devices
     */
    fun getPairedDevices(): List<BluetoothDevice> {
        return bluetoothAdapter?.bondedDevices?.toList() ?: emptyList()
    }

    /**
     * Start discovery for new devices
     */
    fun startDiscovery() {
        bluetoothAdapter?.cancelDiscovery()
        bluetoothAdapter?.startDiscovery()
    }

    /**
     * Check if PAN is available
     */
    fun isPanAvailable(): Boolean {
        return bluetoothAdapter?.isEnabled == true &&
               bluetoothManager != null
    }
}

sealed interface BluetoothState {
    data object Disconnected : BluetoothState
    data class Listening(val mode: String) : BluetoothState
    data class Connecting(val deviceName: String) : BluetoothState
    data class Connected(val deviceName: String) : BluetoothState
    data class Error(val message: String) : BluetoothState
}

sealed interface BluetoothEvent {
    data class Connected(val device: BluetoothDevice) : BluetoothEvent
    data class Disconnected(val device: BluetoothDevice) : BluetoothEvent
    data class Data(val device: BluetoothDevice, val data: ByteArray) : BluetoothEvent
}

class BluetoothConnection(
    private val socket: BluetoothSocket,
    private val type: String
) {
    private val inputStream = socket.inputStream
    private val outputStream = socket.outputStream

    fun send(data: ByteArray) {
        outputStream.write(data)
        outputStream.flush()
    }

    fun readLoop(onData: (ByteArray) -> Unit) {
        val buffer = ByteArray(4096)
        while (socket.isConnected) {
            val read = inputStream.read(buffer)
            if (read > 0) {
                onData(buffer.copyOf(read))
            } else {
                break
            }
        }
    }

    fun close() {
        try { socket.close() } catch (_: Exception) {}
    }
}
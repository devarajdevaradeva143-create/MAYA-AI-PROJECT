package com.devaraj.maya.ui.monitor

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.DeviceStatusRequest
import com.devaraj.maya.data.remote.EventsMessage
import com.devaraj.maya.data.remote.EventsSocket
import com.devaraj.maya.data.remote.PhoneStatsDto
import com.devaraj.maya.data.remote.PcStatusDto
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class PhoneStats(
    val batteryPercent: Int? = null,
    val storageUsedPercent: Int? = null,
    val ramUsedPercent: Int? = null,
    val uptimeHours: Long? = null,
)

data class MonitorUiState(
    val laptop: PcStatusDto? = null,
    val phone: PhoneStats = PhoneStats(),
    val laptopError: String? = null,
    val polling: Boolean = false,
    val cpuHistory: List<Float> = emptyList(),
    val ramHistory: List<Float> = emptyList(),
    val events: List<String> = emptyList(),
    val eventsConnected: Boolean = false,
)

class MonitorViewModel(
    private val appContext: Context,
    private val connectionRepository: ConnectionRepository,
    private val apiClient: ApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(MonitorUiState())
    val state: StateFlow<MonitorUiState> = _state.asStateFlow()

    private val eventsSocket = EventsSocket(apiClient, viewModelScope)
    private var pollJob: Job? = null
    private var eventsJob: Job? = null
    private var messagesJob: Job? = null

    fun start() {
        refreshPhone()
        viewModelScope.launch { sendDeviceStatus() }
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            _state.update { it.copy(polling = true) }
            while (isActive) {
                refreshPhone()
                fetchLaptop()
                sendDeviceStatus()
                delay(2000)
            }
        }
        eventsJob?.cancel()
        eventsJob = viewModelScope.launch {
            val conn = connectionRepository.state.value
            if (conn !is ConnectionState.Connected) return@launch
            eventsSocket.connect(conn.device.host, conn.device.port)
            eventsSocket.connected.collect { connected ->
                _state.update { it.copy(eventsConnected = connected) }
            }
        }
        messagesJob?.cancel()
        messagesJob = viewModelScope.launch {
            eventsSocket.messages.collect { msg ->
                when (msg) {
                    is EventsMessage.Status -> {
                        _state.update {
                            it.copy(
                                laptop = msg.data,
                                laptopError = null,
                                cpuHistory = (it.cpuHistory + (msg.data.cpu?.percent?.toFloat() ?: 0f)).takeLast(40),
                                ramHistory = (it.ramHistory + (msg.data.ram?.percent?.toFloat() ?: 0f)).takeLast(40),
                            )
                        }
                    }
                    is EventsMessage.Event -> {
                        _state.update { it.copy(events = (listOf(msg.text) + it.events).take(30)) }
                    }
                    is EventsMessage.Ping -> Unit
                    is EventsMessage.Closed -> {
                        _state.update { it.copy(eventsConnected = false) }
                    }
                }
            }
        }
    }

    fun stop() {
        pollJob?.cancel()
        pollJob = null
        eventsJob?.cancel()
        eventsJob = null
        messagesJob?.cancel()
        messagesJob = null
        eventsSocket.disconnect()
        _state.update { it.copy(polling = false, eventsConnected = false) }
    }

    private suspend fun fetchLaptop() {
        val conn = connectionRepository.state.value
        if (conn !is ConnectionState.Connected) {
            _state.update { it.copy(laptop = null, laptopError = "Laptop not connected") }
            return
        }
        try {
            val status = apiClient.api(conn.device.host, conn.device.port).pcStatus()
            _state.update {
                it.copy(
                    laptop = status,
                    laptopError = null,
                    cpuHistory = (it.cpuHistory + (status.cpu?.percent?.toFloat() ?: 0f)).takeLast(40),
                    ramHistory = (it.ramHistory + (status.ram?.percent?.toFloat() ?: 0f)).takeLast(40),
                )
            }
        } catch (e: Exception) {
            _state.update { it.copy(laptopError = e.message ?: "Failed to load laptop status") }
        }
    }

    private fun refreshPhone() {
        val battery = readBatteryPercent()
        val storage = readStoragePercent()
        val ram = readRamPercent()
        val uptimeHours = SystemClock.elapsedRealtime() / 3_600_000
        _state.update {
            it.copy(
                phone = PhoneStats(
                    batteryPercent = battery,
                    storageUsedPercent = storage,
                    ramUsedPercent = ram,
                    uptimeHours = uptimeHours,
                ),
            )
        }
    }

    private suspend fun sendDeviceStatus() {
        val conn = connectionRepository.state.value ?: return
        if (conn !is ConnectionState.Connected) return
        try {
            val battery = readBatteryPercent()
            val storage = readStoragePercent()
            val ram = readRamPercent()
            val uptimeHours = SystemClock.elapsedRealtime() / 3_600_000
            apiClient.api(conn.device.host, conn.device.port).deviceStatus(
                DeviceStatusRequest(
                    deviceId = conn.device.id,
                    stats = PhoneStatsDto(
                        batteryPercent = battery,
                        storageUsedPercent = storage,
                        ramUsedPercent = ram,
                        uptimeHours = uptimeHours.toInt(),
                    ),
                )
            )
        } catch (e: Exception) {
            // Best effort: laptop may not be running or might be offline
        }
    }

    private fun readBatteryPercent(): Int? {
        val intent = appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return null
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) return null
        return (level * 100 / scale).coerceIn(0, 100)
    }

    private fun readStoragePercent(): Int? {
        return try {
            val stat = StatFs(Environment.getDataDirectory().path)
            val total = stat.blockCountLong * stat.blockSizeLong
            val avail = stat.availableBlocksLong * stat.blockSizeLong
            if (total <= 0) null else (((total - avail) * 100) / total).toInt().coerceIn(0, 100)
        } catch (_: Exception) { null }
    }

    private fun readRamPercent(): Int? {
        return try {
            val am = appContext.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val info = ActivityManager.MemoryInfo()
            am.getMemoryInfo(info)
            if (info.totalMem <= 0) null else (((info.totalMem - info.availMem) * 100) / info.totalMem).toInt().coerceIn(0, 100)
        } catch (_: Exception) { null }
    }

    override fun onCleared() {
        stop()
        super.onCleared()
    }

    class Factory(
        private val appContext: Context,
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(MonitorViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return MonitorViewModel(appContext, connectionRepository, apiClient) as T
        }
    }
}

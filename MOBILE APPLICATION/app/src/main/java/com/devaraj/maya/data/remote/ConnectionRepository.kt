package com.devaraj.maya.data.remote

import com.devaraj.maya.data.local.dao.DeviceDao
import com.devaraj.maya.data.local.toDomain
import com.devaraj.maya.data.secure.TokenStore
import com.devaraj.maya.domain.model.Device
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map

sealed interface ConnectionState {
    data object Offline : ConnectionState
    data object Checking : ConnectionState
    data class Connected(val device: Device, val health: HealthDto) : ConnectionState
    data object NeedsPairing : ConnectionState
    data class Failed(val reason: MayaErrorReason) : ConnectionState
}

/**
 * Active device + health state (plan §14.2). One health check per call; retry
 * policy lives in [connectWithRetry] so the caller controls UI feedback.
 */
class ConnectionRepository(
    private val apiFactory: (host: String, port: Int, quick: Boolean) -> MayaApi,
    private val tokenStore: TokenStore,
    private val deviceDao: DeviceDao,
    private val session: SessionState,
    private val now: () -> Long = System::currentTimeMillis,
) {

    private val _state = MutableStateFlow<ConnectionState>(ConnectionState.Offline)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    fun observeDevices(): Flow<List<Device>> =
        deviceDao.observeAll().map { list -> list.map { it.toDomain() } }

    suspend fun lastDevice(): Device? = deviceDao.mostRecent()?.toDomain()

    suspend fun setAutoConnect(deviceId: String, enabled: Boolean) {
        deviceDao.updateAutoConnect(deviceId, enabled)
    }

    /** Health check with the 2 s startup budget (plan §14.2). */
    suspend fun connect(device: Device, hostOverride: String? = null): ConnectionState {
        if (tokenStore.load(device.id).isNullOrBlank()) {
            _state.value = ConnectionState.NeedsPairing
            return ConnectionState.NeedsPairing
        }
        _state.value = ConnectionState.Checking
        val host = hostOverride?.takeIf { it.isNotBlank() } ?: device.host
        val result = try {
            val health = apiFactory(host, device.port, true).health()
            val touched = device.copy(host = host, lastSeen = now())
            deviceDao.touch(device.id, touched.lastSeen)
            session.activeDeviceId = device.id
            session.host = host
            session.port = device.port
            ConnectionState.Connected(touched, health)
        } catch (error: Exception) {
            val mapped = ErrorMapper.toApiException(error)
            when (mapped.reason) {
                MayaErrorReason.INVALID_TOKEN,
                MayaErrorReason.TOKEN_EXPIRED,
                MayaErrorReason.DEVICE_REVOKED,
                -> {
                    tokenStore.delete(device.id)
                    session.activeDeviceId = null
                    ConnectionState.NeedsPairing
                }
                else -> ConnectionState.Failed(mapped.reason)
            }
        }
        _state.value = result
        return result
    }

    /** Auto-connect: 3 tries with 2 s / 5 s / 10 s backoff (plan §14.2). */
    suspend fun connectWithRetry(
        device: Device,
        hostOverride: String? = null,
        delaysMillis: List<Long> = listOf(2_000, 5_000, 10_000),
    ): ConnectionState {
        var attempt = 0
        while (true) {
            val result = connect(device, hostOverride)
            val retryable = result is ConnectionState.Failed &&
                (result.reason == MayaErrorReason.NO_CONNECTION ||
                    result.reason == MayaErrorReason.TIMEOUT)
            if (!retryable || attempt >= delaysMillis.size) return result
            delay(delaysMillis[attempt])
            attempt++
        }
    }

    fun markOffline() {
        _state.value = ConnectionState.Offline
    }

    fun clearSession() {
        session.activeDeviceId = null
        _state.value = ConnectionState.Offline
    }
}

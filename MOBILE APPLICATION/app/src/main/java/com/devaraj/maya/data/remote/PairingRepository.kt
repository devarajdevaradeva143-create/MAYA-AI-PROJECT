package com.devaraj.maya.data.remote

import com.devaraj.maya.data.local.dao.DeviceDao
import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.data.local.toDomain
import com.devaraj.maya.data.secure.TokenStore
import com.devaraj.maya.domain.model.Device

/**
 * In-memory pointer to the active laptop. Not persisted (the devices table is
 * the source of truth) — it lets the OkHttp auth interceptor find the right
 * token cheaply on every request.
 */
class SessionState {
    @Volatile var activeDeviceId: String? = null
    @Volatile var host: String? = null
    @Volatile var port: Int = ApiClient.DEFAULT_PORT
}

/**
 * PIN / QR pairing, refresh and revoke (plan §12.3, API contract §6).
 * Tokens are stored through [TokenStore] only — never Room, never logs.
 */
class PairingRepository(
    private val apiFactory: (host: String, port: Int) -> MayaApi,
    private val tokenStore: TokenStore,
    private val deviceDao: DeviceDao,
    private val appVersion: String,
    private val session: SessionState = SessionState(),
    private val now: () -> Long = System::currentTimeMillis,
) {

    suspend fun claimPin(
        host: String,
        port: Int,
        pin: String,
        deviceId: String,
        deviceName: String,
    ): Result<Device> = apiCall {
        val response = apiFactory(host, port).pairClaim(
            PairClaimRequest(
                deviceId = deviceId,
                deviceName = deviceName,
                pin = pin,
                appVersion = appVersion,
            ),
        )
        storePairing(deviceId, response, fallbackHost = host, fallbackPort = port)
    }

    suspend fun claimQr(
        payload: QrPayload,
        deviceId: String,
        deviceName: String,
    ): Result<Device> = apiCall {
        val response = apiFactory(payload.h, payload.p).pairQrClaim(
            QrClaimRequest(
                qrToken = payload.t,
                deviceId = deviceId,
                deviceName = deviceName,
                appVersion = appVersion,
            ),
        )
        storePairing(deviceId, response, fallbackHost = payload.h, fallbackPort = payload.p)
    }

    /** Extends the token TTL; returns the new expiry (epoch seconds). */
    suspend fun refresh(device: Device): Result<Long> = apiCall {
        val response = apiFactory(device.host, device.port)
            .pairRefresh(RefreshRequest(device.id))
        tokenStore.save(device.id, response.token)
        response.expiresAt
    }

    suspend fun listDevices(device: Device): Result<List<DeviceDto>> = apiCall {
        apiFactory(device.host, device.port).listDevices().devices
    }

    /**
     * Revokes a paired device on the laptop. Revoking this phone also removes
     * the local token so the app returns to pairing.
     */
    suspend fun revoke(
        host: String,
        port: Int,
        targetDeviceId: String,
        currentDeviceId: String?,
    ): Result<Unit> = apiCall {
        val response = apiFactory(host, port).revokeDevice(targetDeviceId)
        if (response.revoked) {
            deviceDao.delete(targetDeviceId)
            tokenStore.delete(targetDeviceId)
            if (targetDeviceId == currentDeviceId) {
                session.activeDeviceId = null
            }
        }
        Unit
    }

    suspend fun forgetLocal(deviceId: String) {
        deviceDao.delete(deviceId)
        tokenStore.delete(deviceId)
        if (session.activeDeviceId == deviceId) session.activeDeviceId = null
    }

    private suspend fun storePairing(
        deviceId: String,
        response: PairResponse,
        fallbackHost: String,
        fallbackPort: Int,
    ): Device {
        val host = response.host.ifBlank { fallbackHost }
        val port = if (response.port > 0) response.port else fallbackPort
        tokenStore.save(deviceId, response.token)

        val existing = deviceDao.findById(deviceId)
        val entity = DeviceEntity(
            id = deviceId,
            name = response.laptopName,
            host = host,
            port = port,
            lastSeen = now(),
            autoConnect = existing?.autoConnect ?: false,
        )
        deviceDao.upsert(entity)
        session.activeDeviceId = deviceId
        session.host = host
        session.port = port
        return entity.toDomain()
    }
}

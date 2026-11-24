package com.devaraj.maya.data.remote

import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.domain.model.Device
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingRepositoryTest {

    private val tokenStore = FakeTokenStore()
    private val deviceDao = FakeDeviceDao()
    private val session = SessionState()

    private fun repo(api: MayaApi, onHostPort: ((String, Int) -> Unit)? = null) = PairingRepository(
        apiFactory = { host, port ->
            onHostPort?.invoke(host, port)
            api
        },
        tokenStore = tokenStore,
        deviceDao = deviceDao,
        appVersion = "0.1.0",
        session = session,
        now = { 1_000L },
    )

    @Test
    fun `PIN claim stores the token and laptop`() = runBlocking {
        val api = object : FakeMayaApi() {
            override suspend fun pairClaim(body: PairClaimRequest) = PairResponse(
                token = "maya_abc",
                expiresAt = 1_767_000_000,
                laptopName = "Devaraj-Laptop",
                api = 1,
                host = "192.168.1.5",
                port = 8420,
            )
        }

        val device = repo(api)
            .claimPin("192.168.1.5", 8420, "482913", "dev_1", "Devaraj Phone")
            .getOrThrow()

        assertEquals("dev_1", device.id)
        assertEquals("Devaraj-Laptop", device.name)
        assertEquals("192.168.1.5", device.host)
        assertEquals(8420, device.port)
        assertEquals(1_000L, device.lastSeen)
        assertEquals("maya_abc", tokenStore.load("dev_1"))
        assertEquals("dev_1", deviceDao.findById("dev_1")?.id)
        assertEquals("dev_1", session.activeDeviceId)
        assertEquals("192.168.1.5", session.host)
    }

    @Test
    fun `QR claim uses the host and port from the QR payload`() = runBlocking {
        var requested: Pair<String, Int>? = null
        val api = object : FakeMayaApi() {
            override suspend fun pairQrClaim(body: QrClaimRequest) = PairResponse(
                token = "maya_qr",
                expiresAt = 1_767_000_000,
                laptopName = "Laptop-QR",
                api = 1,
                host = "10.0.0.7",
                port = 8420,
            )
        }

        val device = repo(api) { host, port -> requested = host to port }
            .claimQr(QrPayload(1, "10.0.0.7", 8420, "qr_tok"), "dev_2", "Phone")
            .getOrThrow()

        assertEquals("10.0.0.7" to 8420, requested)
        assertEquals("Laptop-QR", device.name)
        assertEquals("maya_qr", tokenStore.load("dev_2"))
    }

    @Test
    fun `wrong PIN returns a mapped failure and stores nothing`() = runBlocking {
        val api = object : FakeMayaApi() {
            override suspend fun pairClaim(body: PairClaimRequest): PairResponse =
                throw MayaApiException(1003, MayaErrorReason.WRONG_PIN, "Invalid PIN")
        }

        val result = repo(api)
            .claimPin("192.168.1.5", 8420, "000000", "dev_1", "Phone")

        val error = result.exceptionOrNull() as MayaApiException
        assertEquals(1003, error.code)
        assertEquals(MayaErrorReason.WRONG_PIN, error.reason)
        assertNull(tokenStore.load("dev_1"))
        assertNull(deviceDao.findById("dev_1"))
    }

    @Test
    fun `refresh replaces the stored token`() = runBlocking {
        tokenStore.save("dev_1", "old")
        val device = Device("dev_1", "Laptop", "192.168.1.5", 8420, 1_000L)
        val api = object : FakeMayaApi() {
            override suspend fun pairRefresh(body: RefreshRequest) =
                RefreshResponse("maya_new", 1_800_000_000)
        }

        val expiresAt = repo(api).refresh(device).getOrThrow()

        assertEquals(1_800_000_000L, expiresAt)
        assertEquals("maya_new", tokenStore.load("dev_1"))
    }

    @Test
    fun `revoking this phone clears token, device and session`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        deviceDao.upsert(DeviceEntity("dev_1", "Laptop", "192.168.1.5", 8420, 1_000L))
        session.activeDeviceId = "dev_1"

        val api = object : FakeMayaApi() {
            override suspend fun revokeDevice(deviceId: String) = RevokeDto(revoked = true)
        }

        val result = repo(api).revoke("192.168.1.5", 8420, "dev_1", "dev_1")

        assertTrue(result.isSuccess)
        assertNull(tokenStore.load("dev_1"))
        assertNull(deviceDao.findById("dev_1"))
        assertNull(session.activeDeviceId)
    }

    @Test
    fun `revoking another device keeps this phone paired`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        deviceDao.upsert(DeviceEntity("dev_2", "Old Phone", "192.168.1.6", 8420, 1_000L))
        session.activeDeviceId = "dev_1"

        val api = object : FakeMayaApi() {
            override suspend fun revokeDevice(deviceId: String) = RevokeDto(revoked = true)
        }

        repo(api).revoke("192.168.1.5", 8420, "dev_2", "dev_1").getOrThrow()

        assertEquals("maya_abc", tokenStore.load("dev_1"))
        assertNull(deviceDao.findById("dev_2"))
        assertEquals("dev_1", session.activeDeviceId)
    }
}

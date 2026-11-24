package com.devaraj.maya.data.remote

import com.devaraj.maya.domain.model.Device
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ConnectionRepositoryTest {

    private val tokenStore = FakeTokenStore()
    private val deviceDao = FakeDeviceDao()
    private val session = SessionState()
    private val device = Device("dev_1", "Devaraj-Laptop", "192.168.1.5", 8420, 500L)

    private fun repo(api: MayaApi, quickCalls: MutableList<Boolean>? = null) = ConnectionRepository(
        apiFactory = { _, _, quick ->
            quickCalls?.add(quick)
            api
        },
        tokenStore = tokenStore,
        deviceDao = deviceDao,
        session = session,
        now = { 2_000L },
    )

    private fun sampleHealth(): HealthDto = HealthDto(
        status = "ok",
        app = "maya-laptop",
        version = "0.1.0",
        api = 1,
        platform = "windows",
        model = "qwen3-3b",
        engine = "lemonade",
        capabilities = listOf("chat"),
    )

    @Test
    fun `health success becomes Connected and updates last seen`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        val quickCalls = mutableListOf<Boolean>()
        val api = object : FakeMayaApi() {
            override suspend fun health(): HealthDto = sampleHealth()
        }

        val result = repo(api, quickCalls).connect(device)

        assertTrue(result is ConnectionState.Connected)
        val connected = result as ConnectionState.Connected
        assertEquals("qwen3-3b", connected.health.model)
        assertEquals(2_000L, connected.device.lastSeen)
        assertEquals(listOf(true), quickCalls)
        assertEquals(listOf("dev_1" to 2_000L), deviceDao.touchCalls)
        assertEquals("dev_1", session.activeDeviceId)
        assertEquals("192.168.1.5", session.host)
    }

    @Test
    fun `missing token goes straight to pairing without a network call`() = runBlocking {
        var calls = 0
        val api = object : FakeMayaApi() {
            override suspend fun health(): HealthDto {
                calls++
                return sampleHealth()
            }
        }

        val result = repo(api).connect(device)

        assertEquals(ConnectionState.NeedsPairing, result)
        assertEquals(0, calls)
    }

    @Test
    fun `revoked device deletes the token and asks for pairing`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        session.activeDeviceId = "dev_1"
        val api = object : FakeMayaApi() {
            override suspend fun health(): HealthDto =
                throw MayaApiException(1007, MayaErrorReason.DEVICE_REVOKED, "Device revoked")
        }

        val result = repo(api).connect(device)

        assertEquals(ConnectionState.NeedsPairing, result)
        assertNull(tokenStore.load("dev_1"))
        assertNull(session.activeDeviceId)
    }

    @Test
    fun `engine down keeps the token and reports a reason`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        val api = object : FakeMayaApi() {
            override suspend fun health(): HealthDto =
                throw MayaApiException(3001, MayaErrorReason.ENGINE_UNAVAILABLE, "Engine unavailable")
        }

        val result = repo(api).connect(device)

        assertEquals(ConnectionState.Failed(MayaErrorReason.ENGINE_UNAVAILABLE), result)
        assertEquals("maya_abc", tokenStore.load("dev_1"))
    }

    @Test
    fun `retry stops immediately when the network is offline`() = runBlocking {
        tokenStore.save("dev_1", "maya_abc")
        var tries = 0
        val api = object : FakeMayaApi() {
            override suspend fun health(): HealthDto {
                tries++
                throw MayaApiException(null, MayaErrorReason.NO_CONNECTION, "No connection")
            }
        }

        val result = repo(api).connectWithRetry(device, delaysMillis = emptyList())

        assertEquals(ConnectionState.Failed(MayaErrorReason.NO_CONNECTION), result)
        assertEquals(1, tries)
    }

    @Test
    fun `auto connect flag is persisted on the device row`() = runBlocking {
        deviceDao.upsert(
            com.devaraj.maya.data.local.entity.DeviceEntity(
                id = "dev_1",
                name = "Laptop",
                host = "192.168.1.5",
                port = 8420,
                lastSeen = 1L,
            ),
        )

        repo(FakeMayaApi()).setAutoConnect("dev_1", true)

        assertEquals(true, deviceDao.findById("dev_1")?.autoConnect)
    }
}

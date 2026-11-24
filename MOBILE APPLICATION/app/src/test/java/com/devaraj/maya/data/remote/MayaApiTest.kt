package com.devaraj.maya.data.remote

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class MayaApiTest {

    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun api(token: String? = "maya_test"): MayaApi =
        ApiClient(tokenProvider = { token }, debug = false).api(server.hostName, server.port)

    private fun json(body: String): MockResponse = MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody(body)

    @Test
    fun `health parses and sends the auth header`() = runBlocking {
        server.enqueue(
            json(
                """
                {"status":"ok","app":"maya-laptop","version":"0.1.0","api":1,
                 "platform":"windows","model":"qwen3-3b","engine":"lemonade",
                 "capabilities":["chat","monitor"],"paired_devices":1,"uptime_s":360}
                """.trimIndent(),
            ),
        )

        val health = api().health()

        assertEquals("ok", health.status)
        assertEquals("maya-laptop", health.app)
        assertEquals(1, health.api)
        assertEquals("qwen3-3b", health.model)
        assertEquals(listOf("chat", "monitor"), health.capabilities)
        assertEquals(360, health.uptimeSeconds)

        val request = server.takeRequest()
        assertEquals("/api/v1/health", request.path)
        assertEquals("Bearer maya_test", request.getHeader("Authorization"))
    }

    @Test
    fun `pair claim uses snake_case fields and parses response`() = runBlocking {
        server.enqueue(
            json(
                """
                {"token":"maya_abc","expires_at":1767000000,
                 "laptop_name":"Devaraj-Laptop","api":1,
                 "host":"192.168.1.5","port":8420}
                """.trimIndent(),
            ),
        )

        val response = api().pairClaim(
            PairClaimRequest(
                deviceId = "dev_1",
                deviceName = "Devaraj Phone",
                pin = "482913",
                appVersion = "0.1.0",
            ),
        )

        assertEquals("maya_abc", response.token)
        assertEquals(1767000000, response.expiresAt)
        assertEquals("Devaraj-Laptop", response.laptopName)
        assertEquals("192.168.1.5", response.host)
        assertEquals(8420, response.port)

        val request = server.takeRequest()
        assertEquals("/api/v1/pair/claim", request.path)
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("dev_1", body["device_id"]!!.jsonPrimitive.content)
        assertEquals("482913", body["pin"]!!.jsonPrimitive.content)
        assertEquals("0.1.0", body["app_version"]!!.jsonPrimitive.content)
        assertEquals(1, body["api"]!!.jsonPrimitive.content.toInt())
        assertTrue(!body.containsKey("deviceId"))
    }

    @Test
    fun `401 error envelope maps to the contract reason`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(401)
                .addHeader("Content-Type", "application/json")
                .setBody("""{"error":{"code":1003,"message":"Invalid PIN","details":null}}"""),
        )

        val result = apiCall {
            api().pairClaim(
                PairClaimRequest("dev_1", "Devaraj Phone", "000000", "0.1.0"),
            )
        }

        val error = result.exceptionOrNull() as MayaApiException
        assertEquals(1003, error.code)
        assertEquals(MayaErrorReason.WRONG_PIN, error.reason)
        assertEquals("Invalid PIN", error.message)
    }

    @Test
    fun `device list and revoke hit the contract paths`() = runBlocking {
        server.enqueue(
            json(
                """
                {"devices":[{"device_id":"dev_1","name":"Devaraj Phone",
                 "paired_at":1760000000,"last_seen":1760100000,"current":true}]}
                """.trimIndent(),
            ),
        )
        server.enqueue(json("""{"revoked":true}"""))

        val devices = api().listDevices().devices
        val revoked = api().revokeDevice("dev_1")

        assertEquals(1, devices.size)
        assertTrue(devices.single().current)
        assertTrue(revoked.revoked)

        assertEquals("/api/v1/pair/devices", server.takeRequest().path)
        val delete = server.takeRequest()
        assertEquals("DELETE", delete.method)
        assertEquals("/api/v1/pair/devices/dev_1", delete.path)
    }

    @Test
    fun `QR payload decodes from scan JSON`() {
        val payload = Json.decodeFromString<QrPayload>(
            """{"v":1,"h":"192.168.1.5","p":8420,"t":"a1b2","n":"Devaraj-Laptop"}""",
        )

        assertEquals(1, payload.v)
        assertEquals("192.168.1.5", payload.h)
        assertEquals(8420, payload.p)
        assertEquals("a1b2", payload.t)
        assertEquals("Devaraj-Laptop", payload.n)
    }

    @Test
    fun `base urls follow the contract`() {
        assertEquals("http://192.168.1.5:8420/api/v1/", ApiClient.baseUrl("192.168.1.5", 8420))
        assertEquals(
            "ws://192.168.1.5:8420/api/v1/ws/chat",
            ApiClient.wsUrl("192.168.1.5", 8420, "ws/chat"),
        )
    }
}

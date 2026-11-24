package com.devaraj.maya.data.remote

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ChatSocketTest {

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

    private fun apiClient() = ApiClient(tokenProvider = { "maya_test" }, debug = false)

    private fun upgraded(listener: WebSocketListener): MockResponse =
        MockResponse().withWebSocketUpgrade(listener)

    @Test
    fun `streams start token done and sends the contract payload`() = runBlocking {
        var clientPayload: String? = null
        server.enqueue(
            upgraded(
                object : WebSocketListener() {
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        clientPayload = text
                        webSocket.send(
                            """{"type":"start","conversation_id":"c_1","model":"qwen3-3b"}""",
                        )
                        webSocket.send("""{"type":"token","text":"Van"}""")
                        webSocket.send("""{"type":"token","text":"akkam"}""")
                        webSocket.send(
                            """{"type":"done","elapsed_ms":12,"tokens":2,"pending_action":null}""",
                        )
                    }
                },
            ),
        )

        val socket = ChatSocket(apiClient(), this as CoroutineScope)
        val events = async {
            withTimeout(5_000) { socket.events.take(4).toList() }
        }

        socket.connect(server.hostName, server.port)
        withTimeout(3_000) { socket.connected.first { it } }
        socket.sendMessage("c_1", "maya", listOf(ChatMessageDto("user", "Hi")))

        val received = events.await()

        val start = received[0] as ChatEvent.Start
        assertEquals("c_1", start.conversationId)
        assertEquals("qwen3-3b", start.model)
        assertEquals("Van", (received[1] as ChatEvent.Token).text)
        assertEquals("akkam", (received[2] as ChatEvent.Token).text)
        assertEquals(12L, (received[3] as ChatEvent.Done).elapsedMs)

        val payload = requireNotNull(clientPayload)
        assertTrue(payload.contains("\"conversation_id\":\"c_1\""))
        assertTrue(payload.contains("\"persona\":\"maya\""))
        assertTrue(payload.contains("\"role\":\"user\""))
        assertTrue(payload.contains("\"content\":\"Hi\""))

        val request = server.takeRequest()
        assertEquals("Bearer maya_test", request.getHeader("Authorization"))
        assertTrue(request.path!!.startsWith("/api/v1/ws/chat"))

        socket.close()
    }

    @Test
    fun `server error event becomes a typed error`() = runBlocking {
        server.enqueue(
            upgraded(
                object : WebSocketListener() {
                    override fun onMessage(webSocket: WebSocket, text: String) {
                        webSocket.send(
                            """{"type":"error","code":3001,"message":"Engine unavailable"}""",
                        )
                    }
                },
            ),
        )

        val socket = ChatSocket(apiClient(), this as CoroutineScope)
        val event = async { withTimeout(5_000) { socket.events.first() } }

        socket.connect(server.hostName, server.port)
        withTimeout(3_000) { socket.connected.first { it } }
        socket.sendMessage("c_1", "maya", listOf(ChatMessageDto("user", "Hi")))

        val error = event.await() as ChatEvent.Error
        assertEquals(3001, error.code)
        assertEquals("Engine unavailable", error.message)

        socket.close()
    }

    @Test
    fun `send without a connection reports no connection`() = runBlocking {
        val socket = ChatSocket(apiClient(), this as CoroutineScope)
        val event = async { withTimeout(2_000) { socket.events.first() } }
        kotlinx.coroutines.delay(100)

        socket.sendMessage("c_1", "maya", listOf(ChatMessageDto("user", "Hi")))

        val failed = event.await() as ChatEvent.Failed
        assertEquals(MayaErrorReason.NO_CONNECTION, failed.reason)
        socket.close()
    }

    @Test
    fun `ping is answered with pong`() = runBlocking {
        var pong: String? = null
        server.enqueue(
            upgraded(
                object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        webSocket.send("""{"type":"ping","ts":1760100000}""")
                    }

                    override fun onMessage(webSocket: WebSocket, text: String) {
                        pong = text
                    }
                },
            ),
        )

        val socket = ChatSocket(apiClient(), this as CoroutineScope)
        socket.connect(server.hostName, server.port)
        withTimeout(3_000) { socket.connected.first { it } }

        kotlinx.coroutines.delay(200)
        assertEquals("""{"type":"pong"}""", pong)
        socket.close()
    }
}

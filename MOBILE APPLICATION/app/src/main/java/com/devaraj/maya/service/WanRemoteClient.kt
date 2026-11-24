package com.devaraj.maya.service

import android.content.Context
import android.util.Log
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import java.security.KeyStore
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/**
 * WAN Remote Client - connects to relay server via WebSocket Secure (WSS)
 *
 * Phone → Relay Server (WSS) → Laptop
 * TLS 1.3 with certificate pinning
 */
class WanRemoteClient(
    private val context: Context,
    private val relayUrl: String,
    private val certPinSha256: String,
    private val pairingToken: String,
) {
    private val _state = MutableStateFlow<WanState>(WanState.Disconnected)
    val state = _state.asStateFlow()

    private var webSocket: WebSocket? = null
    private var client: OkHttpClient? = null
    private val events = Channel<WanEvent>(100)

    private val deviceId: String = context.filesDir.absolutePath.hashCode().toString(16)

    init {
        buildClient()
    }

    /**
     * Build OkHttpClient with TLS cert pinning
     */
    private fun buildClient() {
        try {
            // Load embedded CA cert for pinning
            val inputStream = context.assets.open("certs/relay_ca.pem")
            val certFactory = CertificateFactory.getInstance("X.509")
            val caCert = certFactory.generateCertificate(inputStream) as X509Certificate
            inputStream.close()

            val keyStore = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null, null) }
            keyStore.setCertificateEntry("relay_ca", caCert)

            val trustManagerFactory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
            trustManagerFactory.init(keyStore)

            val trustManagers = trustManagerFactory.trustManagers
            val trustManager = trustManagers.firstOrNull { it is X509TrustManager } as X509TrustManager

            val sslContext = SSLContext.getInstance("TLS")
            sslContext.init(null, arrayOf(trustManager), null)

            client = OkHttpClient.Builder()
                .sslSocketFactory(sslContext.socketFactory, trustManager)
                .build()
        } catch (e: Exception) {
            Log.e("WanRemote", "Failed to build TLS client", e)
            _state.value = WanState.Error("TLS setup failed: ${e.message}")
        }
    }

    /**
     * Connect to relay server
     */
    fun connect() {
        val activeClient = client ?: return

        val url = "$relayUrl/wan/phone?token=$pairingToken&device_id=$deviceId"
        val request = Request.Builder().url(url).build()

        _state.value = WanState.Connecting

        activeClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                attach(webSocket)
                _state.value = WanState.Connected
                Log.d("WanRemote", "Connected to relay: $relayUrl")

                // Register with relay
                sendJson(
                    mapOf(
                        "type" to "register",
                        "device_id" to deviceId,
                        "capabilities" to listOf("phone_remote", "chat", "monitor"),
                    ),
                )
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                handleBinary(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, "Client closing")
                _state.value = WanState.Disconnected
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e("WanRemote", "WebSocket failure", t)
                _state.value = WanState.Error(t.message ?: "Connection failed")
            }
        })
    }

    /**
     * Disconnect from relay
     */
    fun disconnect() {
        webSocket?.close(1000, "Client disconnect")
        webSocket = null
        _state.value = WanState.Disconnected
    }

    /** Send JSON message */
    fun sendJson(data: Map<String, Any>) {
        webSocket?.send(toJsonObject(data).toString())
    }

    /** Send binary data (screen frames) */
    fun sendBinary(data: ByteArray) {
        webSocket?.send(data.toByteString())
    }

    /** Handle incoming JSON message */
    private fun handleMessage(text: String) {
        val obj = runCatching { Json.parseToJsonElement(text) as? JsonObject }.getOrNull() ?: return
        val type = obj["type"]?.jsonPrimitive?.contentOrNull ?: return

        when (type) {
            "registered" -> {
                val wanId = obj["wan_id"]?.jsonPrimitive?.contentOrNull
                if (wanId != null) {
                    _state.value = WanState.Connected
                    events.trySend(WanEvent.Registered(wanId))
                }
            }
            "input" -> {
                val list = obj["events"] as? JsonArray ?: return
                val mapped = list.mapNotNull { element ->
                    (element as? JsonObject)?.entries
                        ?.associate { (key, value) -> key to jsonValue(value) }
                }
                events.trySend(WanEvent.Input(mapped))
            }
            "screen_ack" -> {
                val seq = obj["seq"]?.jsonPrimitive?.longOrNull ?: 0L
                events.trySend(WanEvent.ScreenAck(seq))
            }
            "error" -> {
                val msg = obj["message"]?.jsonPrimitive?.contentOrNull ?: "Unknown error"
                events.trySend(WanEvent.Error(msg))
            }
            "pong" -> Unit // Keep-alive
        }
    }

    /** Handle incoming binary data */
    private fun handleBinary(data: ByteArray) {
        events.trySend(WanEvent.BinaryData(data))
    }

    /** Send screen frame */
    fun sendScreenFrame(frame: ByteArray, seq: Long) {
        sendJson(
            mapOf(
                "type" to "screen",
                "data" to android.util.Base64.encodeToString(frame, android.util.Base64.NO_WRAP),
                "seq" to seq,
            ),
        )
    }

    /** Send input events */
    fun sendInput(eventsList: List<Map<String, Any>>) {
        sendJson(
            mapOf(
                "type" to "input",
                "events" to eventsList,
            ),
        )
    }

    /** Send ping */
    fun sendPing() {
        sendJson(mapOf("type" to "ping"))
    }

    private fun attach(socket: WebSocket) {
        webSocket = socket
    }

    private fun toJsonObject(data: Map<String, Any>): JsonObject =
        JsonObject(data.entries.associate { (key, value) -> key to toJsonElement(value) })

    private fun toJsonElement(value: Any?): JsonElement = when (value) {
        null -> JsonNull
        is JsonElement -> value
        is String -> JsonPrimitive(value)
        is Boolean -> JsonPrimitive(value)
        is Number -> JsonPrimitive(value)
        is Map<*, *> -> JsonObject(
            value.entries.associate { (key, entry) -> key.toString() to toJsonElement(entry) },
        )
        is Iterable<*> -> JsonArray(value.map { toJsonElement(it) })
        else -> JsonPrimitive(value.toString())
    }

    private fun jsonValue(element: JsonElement): Any = when (element) {
        is JsonObject -> element.entries.associate { (key, value) -> key to jsonValue(value) }
        is JsonArray -> element.map { jsonValue(it) }
        is JsonNull -> ""
        is JsonPrimitive ->
            element.booleanOrNull ?: element.longOrNull ?: element.contentOrNull ?: ""
    }
}

sealed interface WanState {
    data object Disconnected : WanState
    data object Connecting : WanState
    data object Connected : WanState
    data class Error(val message: String) : WanState
}

sealed interface WanEvent {
    data class Registered(val wanId: String) : WanEvent
    data class Input(val events: List<Map<String, Any>>) : WanEvent
    data class ScreenAck(val seq: Long) : WanEvent
    data class BinaryData(val data: ByteArray) : WanEvent
    data class Error(val message: String) : WanEvent
}

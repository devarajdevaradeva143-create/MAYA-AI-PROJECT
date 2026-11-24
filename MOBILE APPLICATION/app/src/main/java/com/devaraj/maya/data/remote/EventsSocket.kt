package com.devaraj.maya.data.remote

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed interface EventsMessage {
    data class Status(val data: PcStatusDto) : EventsMessage
    data class Event(val text: String) : EventsMessage
    data class Ping(val ts: Long) : EventsMessage
    data object Closed : EventsMessage
}

/**
 * Lightweight client for `WS /ws/events`. Status updates arrive ~every 2s;
 * wake/notification events arrive as they happen. Polling remains the primary
 * path; this socket only enriches the monitor with an event log + live status.
 */
class EventsSocket(
    private val apiClient: ApiClient,
    private val scope: CoroutineScope,
    private val json: Json = Json { ignoreUnknownKeys = true },
) {
    private val _messages = MutableSharedFlow<EventsMessage>(extraBufferCapacity = 64)
    val messages: SharedFlow<EventsMessage> = _messages.asSharedFlow()

    private val _connected = MutableSharedFlow<Boolean>(replay = 1, extraBufferCapacity = 4)
    val connected: SharedFlow<Boolean> = _connected.asSharedFlow()

    private var socket: WebSocket? = null
    private var pingJob: Job? = null
    private var manualClose = false
    private var host: String? = null
    private var port: Int = ApiClient.DEFAULT_PORT

    fun connect(host: String, port: Int) {
        if (this.host == host && this.port == port && socket != null) return
        closeSocket(manual = true)
        this.host = host
        this.port = port
        manualClose = false
        socket = apiClient.newWebSocket(ApiClient.wsUrl(host, port, "ws/events"), listener)
    }

    fun disconnect() {
        closeSocket(manual = true)
    }

    private fun closeSocket(manual: Boolean) {
        manualClose = manual
        pingJob?.cancel()
        pingJob = null
        socket?.cancel()
        socket = null
        _connected.tryEmit(false)
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            _connected.tryEmit(true)
            pingJob?.cancel()
            pingJob = scope.launch {
                while (isActive) {
                    delay(20_000)
                    socket?.send("""{"type":"ping"}""")
                }
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            try {
                val obj = json.parseToJsonElement(text).jsonObject
                val type = obj["type"]?.toString()?.trim('"') ?: return
                when (type) {
                    "status" -> {
                        val data = obj["data"] ?: return
                        val status = json.decodeFromJsonElement(PcStatusDto.serializer(), data)
                        _messages.tryEmit(EventsMessage.Status(status))
                    }
                    "ping" -> {
                        val ts = (obj["ts"] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toLongOrNull() ?: 0L
                        _messages.tryEmit(EventsMessage.Ping(ts))
                    }
                    else -> {
                        _messages.tryEmit(EventsMessage.Event(text.take(300)))
                    }
                }
            } catch (_: Exception) {
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            _connected.tryEmit(false)
            pingJob?.cancel()
            socket = null
            if (!manualClose) _messages.tryEmit(EventsMessage.Closed)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            _connected.tryEmit(false)
            pingJob?.cancel()
            socket = null
            if (!manualClose) _messages.tryEmit(EventsMessage.Closed)
        }
    }
}

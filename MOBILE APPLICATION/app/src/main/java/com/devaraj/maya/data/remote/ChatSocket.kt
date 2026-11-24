package com.devaraj.maya.data.remote

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

sealed interface ChatEvent {
    data class Start(val conversationId: String?, val model: String?) : ChatEvent
    data class Token(val text: String) : ChatEvent
    data class Done(
        val elapsedMs: Long,
        val tokens: Int?,
        val pendingAction: PendingActionDto?,
    ) : ChatEvent
    data class Error(val code: Int?, val message: String) : ChatEvent
    data class Failed(val reason: MayaErrorReason) : ChatEvent
    data object Closed : ChatEvent
}

/**
 * `WS /ws/chat` client (contract §7). One generation per connection; cancel
 * closes the socket and the caller reconnects for the next message.
 */
class ChatSocket(
    private val apiClient: ApiClient,
    private val scope: CoroutineScope,
    private val json: Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    },
) {

    private val _events = MutableSharedFlow<ChatEvent>(extraBufferCapacity = 256)
    val events: SharedFlow<ChatEvent> = _events.asSharedFlow()

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected.asStateFlow()

    private var socket: WebSocket? = null
    private var pingJob: Job? = null
    private var manualClose = false
    private var host: String? = null
    private var port: Int = ApiClient.DEFAULT_PORT

    fun connect(host: String, port: Int) {
        if (this.host == host && this.port == port && _connected.value) return
        closeSocket(manual = true)
        this.host = host
        this.port = port
        manualClose = false
        socket = apiClient.newWebSocket(ApiClient.wsUrl(host, port, "ws/chat"), listener)
    }

    fun sendMessage(conversationId: String, persona: String, messages: List<ChatMessageDto>) {
        val current = socket
        if (current == null || !_connected.value) {
            _events.tryEmit(ChatEvent.Failed(MayaErrorReason.NO_CONNECTION))
            return
        }
        current.send(
            json.encodeToString(
                WsUserMessage.serializer(),
                WsUserMessage(conversationId = conversationId, persona = persona, messages = messages),
            ),
        )
    }

    /** User pressed Stop: close the generation, keep whatever streamed. */
    fun cancel() {
        closeSocket(manual = true)
    }

    /** Connection lost / screen left: no error event. */
    fun disconnect() {
        closeSocket(manual = true)
    }

    fun close() {
        closeSocket(manual = true)
    }

    private fun closeSocket(manual: Boolean) {
        manualClose = manual
        pingJob?.cancel()
        pingJob = null
        socket?.cancel()
        socket = null
        _connected.value = false
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            _connected.value = true
            pingJob?.cancel()
            pingJob = scope.launch {
                while (isActive) {
                    delay(PING_INTERVAL_MS)
                    socket?.send("""{"type":"ping"}""")
                }
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val incoming = try {
                json.decodeFromString(WsIncoming.serializer(), text)
            } catch (_: Exception) {
                return
            }
            when (incoming.type) {
                "start" -> _events.tryEmit(
                    ChatEvent.Start(incoming.conversationId, incoming.model),
                )
                "token" -> incoming.text?.let { _events.tryEmit(ChatEvent.Token(it)) }
                "done" -> _events.tryEmit(
                    ChatEvent.Done(
                        elapsedMs = incoming.elapsedMs,
                        tokens = incoming.tokens,
                        pendingAction = incoming.pendingAction,
                    ),
                )
                "error" -> _events.tryEmit(
                    ChatEvent.Error(
                        code = incoming.code,
                        message = incoming.message ?: "Chat failed",
                    ),
                )
                "ping" -> webSocket.send("""{"type":"pong"}""")
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            _connected.value = false
            pingJob?.cancel()
            socket = null
            if (!manualClose) {
                _events.tryEmit(ChatEvent.Failed(ErrorMapper.toApiException(t).reason))
            }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            _connected.value = false
            pingJob?.cancel()
            socket = null
            if (!manualClose) _events.tryEmit(ChatEvent.Closed)
        }
    }

    companion object {
        const val PING_INTERVAL_MS = 25_000L
    }
}

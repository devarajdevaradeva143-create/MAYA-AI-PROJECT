package com.devaraj.maya.ui.chat

import android.content.Intent
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.cloud.GeminiRepository
import com.devaraj.maya.data.model.OnDeviceModelManager
import com.devaraj.maya.data.persona.PersonaPrompts
import com.devaraj.maya.data.model.PromptBuilder
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ChatEvent
import com.devaraj.maya.data.remote.ChatMessageDto
import com.devaraj.maya.data.remote.ChatSocket
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.MayaErrorReason
import com.devaraj.maya.data.repo.ChatRepository
import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

data class ChatUiState(
    val conversationId: String? = null,
    val messages: List<Message> = emptyList(),
    val persona: String = PERSONA_MAYA,
    val connection: ConnectionState = ConnectionState.Offline,
    val streaming: Boolean = false,
    val errorReason: MayaErrorReason? = null,
    val errorMessage: String? = null,
    val phoneModelReady: Boolean = false,
    val cloudReady: Boolean = false,
    val localGenerating: Boolean = false,
) {
    val connected: Boolean get() = connection is ConnectionState.Connected

    /** Laptop online, phone model installed, or cloud key configured. */
    val canSend: Boolean get() = connected || phoneModelReady || cloudReady

    companion object {
        const val PERSONA_MAYA = "maya"
        const val PERSONA_TEACHER = "teacher"
    }
}

/**
 * Chat pipeline (plan §15): local persistence + streaming over `WS /ws/chat`.
 * Streaming text is written to Room every 250 ms, never per token.
 */
class ChatViewModel(
    private val chatRepository: ChatRepository,
    private val connectionRepository: ConnectionRepository,
    apiClient: ApiClient,
    private val modelManager: OnDeviceModelManager,
    private val geminiRepository: GeminiRepository,
    geminiApiKeyFlow: Flow<String>,
) : ViewModel() {

    private val socket = ChatSocket(apiClient, viewModelScope)

    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    private var messagesJob: Job? = null
    private var flushJob: Job? = null
    private var streamBuffer = StringBuffer()
    private var streamingMessageId: String? = null

    @Volatile
    private var localStopRequested = false

    init {
        viewModelScope.launch {
            val conversation = chatRepository.latestConversation()
                ?: chatRepository.ensureConversation()
            openConversation(conversation.id)
        }
        viewModelScope.launch {
            connectionRepository.state.collect { connection ->
                _state.update { it.copy(connection = connection) }
                if (connection is ConnectionState.Connected && !socket.connected.value) {
                    socket.connect(connection.device.host, connection.device.port)
                }
            }
        }
        viewModelScope.launch {
            modelManager.status.collect { status ->
                _state.update { it.copy(phoneModelReady = status.valid) }
            }
        }
        viewModelScope.launch {
            socket.events.collect { event -> handleEvent(event) }
        }
        viewModelScope.launch {
            // Cloud readiness follows Settings live: entering a key must
            // enable Send without recreating the ViewModel.
            geminiApiKeyFlow.collect { key ->
                _state.update { it.copy(cloudReady = key.isNotBlank()) }
            }
        }
    }

    private fun openConversation(id: String) {
        messagesJob?.cancel()
        _state.update { it.copy(conversationId = id, messages = emptyList()) }
        messagesJob = viewModelScope.launch {
            // A process kill mid-reply can leave a row stuck in STREAMING.
            chatRepository.markStreamingAsStopped(id)
            chatRepository.observeMessages(id).collect { messages ->
                _state.update { it.copy(messages = messages) }
            }
        }
    }

    fun send(text: String) {
        val trimmed = text.trim()
        val conversationId = _state.value.conversationId ?: return
        if (trimmed.isEmpty() || _state.value.streaming) return

        if (!_state.value.canSend) {
            _state.update {
                it.copy(
                    errorReason = MayaErrorReason.NO_CONNECTION,
                    errorMessage = "No AI source: connect to the laptop, download the " +
                        "phone model, or add a Gemini API key in Settings.",
                )
            }
            return
        }

        viewModelScope.launch {
            chatRepository.addUserMessage(conversationId, trimmed)
            when {
                _state.value.connected -> beginStream(conversationId)
                _state.value.phoneModelReady -> beginLocalReply(conversationId)
                _state.value.cloudReady -> beginCloudReply(conversationId)
                else -> _state.update {
                    it.copy(
                        errorReason = MayaErrorReason.NO_CONNECTION,
                        errorMessage = "No AI source available (laptop offline, no phone model, no Gemini key)",
                    )
                }
            }
        }
    }

    private suspend fun beginStream(conversationId: String) {
        val current = _state.value.connection
        if (current is ConnectionState.Connected && !socket.connected.value) {
            socket.connect(current.device.host, current.device.port)
        }
        val ready = socket.connected.value ||
            withTimeoutOrNull(SOCKET_WAIT_MS) { socket.connected.first { it } } == true
        if (!ready) {
            // Laptop went away between the state check and the socket connect.
            if (_state.value.phoneModelReady) {
                beginLocalReply(conversationId)
                return
            }
            val failed = chatRepository.startStreamingReply(conversationId)
            chatRepository.updateMessage(
                messageId = failed.id,
                content = "",
                status = MessageStatus.FAILED,
                error = MayaErrorReason.NO_CONNECTION.name,
            )
            _state.update { it.copy(errorReason = MayaErrorReason.NO_CONNECTION) }
            return
        }

        val history = chatRepository.historyForRequest(conversationId)
        if (history.isEmpty()) return

        val requestMessages = history.mapNotNull { message ->
            when (message.role) {
                MessageRole.USER -> ChatMessageDto("user", message.content)
                MessageRole.MAYA, MessageRole.ASSISTANT -> if (message.content.isNotBlank()) {
                    ChatMessageDto("assistant", message.content)
                } else {
                    null
                }
                MessageRole.SYSTEM -> null
            }
        }
        if (requestMessages.isEmpty()) return

        val reply = chatRepository.startStreamingReply(conversationId)
        streamingMessageId = reply.id
        streamBuffer = StringBuffer()
        _state.update { it.copy(streaming = true, errorReason = null, errorMessage = null) }
        startFlush(reply.id)

        socket.sendMessage(
            conversationId = conversationId,
            persona = _state.value.persona,
            messages = requestMessages,
        )
    }

    /**
     * Offline fallback (plan §17.4): generate on the phone with llama.cpp.
     * The native call blocks on an IO thread; tokens are flushed to Room every
     * 250 ms by the same job used for socket streaming.
     */
    private suspend fun beginLocalReply(conversationId: String) {
        if (!_state.value.phoneModelReady) {
            _state.update { it.copy(errorReason = MayaErrorReason.NO_CONNECTION) }
            return
        }

        localStopRequested = false
        val history = chatRepository.historyForRequest(conversationId)
        val prompt = PromptBuilder.build(_state.value.persona, history)
        if (prompt.isBlank()) {
            val failed = chatRepository.startStreamingReply(
                conversationId,
                source = AiSource.PHONE,
                model = LOCAL_MODEL_NAME,
            )
            chatRepository.updateMessage(
                messageId = failed.id,
                content = "",
                status = MessageStatus.FAILED,
                error = "Could not build a prompt",
            )
            _state.update {
                it.copy(
                    errorReason = MayaErrorReason.UNKNOWN,
                    errorMessage = "Could not build a prompt for the phone model",
                )
            }
            return
        }

        val reply = chatRepository.startStreamingReply(
            conversationId,
            source = AiSource.PHONE,
            model = LOCAL_MODEL_NAME,
        )
        streamingMessageId = reply.id
        streamBuffer = StringBuffer()
        _state.update {
            it.copy(
                streaming = true,
                localGenerating = true,
                errorReason = null,
                errorMessage = null,
            )
        }
        startFlush(reply.id)

        val result = withContext(Dispatchers.IO) {
            modelManager.generate(prompt, PromptBuilder.MAX_NEW_TOKENS) { piece ->
                streamBuffer.append(piece)
            }
        }

        if (localStopRequested) {
            localStopRequested = false
            finishStream(MessageStatus.STOPPED)
            return
        }

        result.fold(
            onSuccess = { text ->
                // Native returns the complete reply; use it as the final
                // source of truth so no split UTF-8 character survives.
                streamBuffer = StringBuffer(text)
                finishStream(MessageStatus.SENT)
            },
            onFailure = { error ->
                // Phone model failed -> try cloud if key is configured
                if (_state.value.cloudReady) {
                    beginCloudReply(conversationId)
                } else {
                    failStream(
                        reason = MayaErrorReason.UNKNOWN,
                        message = "Phone model: ${error.message ?: "generation failed"}",
                    )
                }
            },
        )
    }

    /**
     * Cloud fallback (Gemini): send history to Google Gemini.
     * Only used when laptop is offline AND phone model is not ready.
     * Requires an API key in Settings.
     */
    private suspend fun beginCloudReply(conversationId: String) {
        if (!_state.value.cloudReady) {
            failStream(reason = MayaErrorReason.NO_CONNECTION, message = "No Gemini API key")
            return
        }

        val history = chatRepository.historyForRequest(conversationId)
        if (history.isEmpty()) return

        val messages = history.mapNotNull { msg ->
            when (msg.role) {
                MessageRole.USER -> GeminiRepository.GeminiMessage("user", msg.content)
                MessageRole.MAYA, MessageRole.ASSISTANT -> if (msg.content.isNotBlank()) {
                    GeminiRepository.GeminiMessage("assistant", msg.content)
                } else null
                MessageRole.SYSTEM -> null
            }
        }
        if (messages.isEmpty()) return

        val reply = chatRepository.startStreamingReply(
            conversationId,
            source = AiSource.CLOUD,
            model = "gemini-3.5-flash-lite",
        )
        streamingMessageId = reply.id
        streamBuffer = StringBuffer()
        _state.update {
            it.copy(
                streaming = true,
                localGenerating = true,
                errorReason = null,
                errorMessage = null,
            )
        }
        startFlush(reply.id)

        val result = withContext(Dispatchers.IO) {
            runCatching {
                geminiRepository.chat(
                    messages = messages,
                    systemPrompt = PersonaPrompts.forPersona(_state.value.persona),
                    maxTokens = 1024,
                )
            }
        }

        if (localStopRequested) {
            localStopRequested = false
            finishStream(MessageStatus.STOPPED)
            return
        }

        result.fold(
            onSuccess = { reply ->
                streamBuffer = StringBuffer(reply.text)
                finishStream(MessageStatus.SENT)
            },
            onFailure = {
                failStream(
                    reason = MayaErrorReason.UNKNOWN,
                    message = "Gemini konjam busy-a irukku. Konjam neram kazhichu Retry pannunga.",
                )
            },
        )
    }

    private fun startFlush(messageId: String) {
        flushJob?.cancel()
        flushJob = viewModelScope.launch {
            while (isActive) {
                delay(FLUSH_INTERVAL_MS)
                chatRepository.updateMessage(
                    messageId = messageId,
                    content = streamBuffer.toString(),
                    status = MessageStatus.STREAMING,
                )
            }
        }
    }

    private fun handleEvent(event: ChatEvent) {
        when (event) {
            is ChatEvent.Start -> _state.update { it.copy(streaming = true) }
            is ChatEvent.Token -> streamBuffer.append(event.text)
            is ChatEvent.Done -> finishStream(MessageStatus.SENT)
            is ChatEvent.Error -> failStream(
                reason = MayaErrorReason.fromCode(event.code),
                message = event.message,
            )
            is ChatEvent.Failed -> failStream(reason = event.reason, message = null)
            is ChatEvent.Closed -> {
                if (_state.value.streaming) finishStream(MessageStatus.STOPPED)
            }
        }
    }

    private fun finishStream(status: MessageStatus) {
        flushJob?.cancel()
        flushJob = null
        val messageId = streamingMessageId ?: return
        val content = streamBuffer.toString()
        streamingMessageId = null
        streamBuffer = StringBuffer()
        localStopRequested = false
        _state.update { it.copy(streaming = false, localGenerating = false) }
        viewModelScope.launch {
            chatRepository.updateMessage(
                messageId = messageId,
                content = content,
                status = status,
                error = if (content.isBlank()) "Empty reply" else null,
            )
        }
    }

    private fun failStream(reason: MayaErrorReason, message: String?) {
        flushJob?.cancel()
        flushJob = null
        val messageId = streamingMessageId
        val content = streamBuffer.toString()
        streamingMessageId = null
        streamBuffer = StringBuffer()
        localStopRequested = false
        _state.update {
            it.copy(
                streaming = false,
                localGenerating = false,
                errorReason = reason,
                errorMessage = message,
            )
        }
        if (messageId != null) {
            viewModelScope.launch {
                chatRepository.updateMessage(
                    messageId = messageId,
                    content = content,
                    status = MessageStatus.FAILED,
                    error = message ?: reason.name,
                )
            }
        }
    }

    fun stopStreaming() {
        if (_state.value.localGenerating) {
            // llama.cpp checks this flag between tokens; the IO coroutine will
            // finish shortly and mark the partial reply as STOPPED.
            localStopRequested = true
            modelManager.cancel()
            return
        }
        socket.cancel()
        finishStream(MessageStatus.STOPPED)
        val current = _state.value.connection
        if (current is ConnectionState.Connected) {
            socket.connect(current.device.host, current.device.port)
        }
    }

    fun retry() {
        val conversationId = _state.value.conversationId ?: return
        if (_state.value.streaming) return
        val failed = _state.value.messages.lastOrNull {
            (it.role == MessageRole.MAYA || it.role == MessageRole.ASSISTANT) && it.status == MessageStatus.FAILED
        } ?: return
        viewModelScope.launch {
            chatRepository.deleteMessage(failed.id)
            _state.update { it.copy(errorReason = null, errorMessage = null) }
            when {
                _state.value.connected -> beginStream(conversationId)
                _state.value.phoneModelReady -> beginLocalReply(conversationId)
                _state.value.cloudReady -> beginCloudReply(conversationId)
                else -> _state.update { it.copy(errorReason = MayaErrorReason.NO_CONNECTION) }
            }
        }
    }

    fun newChat() {
        if (_state.value.streaming) return
        viewModelScope.launch {
            val conversation = chatRepository.ensureConversation()
            openConversation(conversation.id)
            _state.update { it.copy(errorReason = null, errorMessage = null) }
        }
    }

    fun deleteChat() {
        if (_state.value.streaming) return
        val conversationId = _state.value.conversationId ?: return
        viewModelScope.launch {
            chatRepository.deleteConversation(conversationId)
            val conversation = chatRepository.ensureConversation()
            openConversation(conversation.id)
            _state.update { it.copy(errorReason = null, errorMessage = null) }
        }
    }

    fun setPersona(persona: String) {
        if (persona != ChatUiState.PERSONA_MAYA && persona != ChatUiState.PERSONA_TEACHER) return
        _state.update { it.copy(persona = persona) }
    }

    fun clearError() {
        _state.update { it.copy(errorReason = null, errorMessage = null) }
    }

    /**
     * Creates a WhatsApp share URL for the given message text.
     * Returns the wa.me URL with properly URL-encoded text. The user still
     * chooses the contact and presses Send (no auto-send).
     * Handles special characters, newlines, and emojis.
     */
    fun sendToWhatsApp(message: String): String = Companion.sendToWhatsApp(message)

    override fun onCleared() {
        if (_state.value.localGenerating) modelManager.cancel()
        socket.close()
        flushJob?.cancel()
        super.onCleared()
    }

    class Factory(
        private val chatRepository: ChatRepository,
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
        private val modelManager: OnDeviceModelManager,
        private val geminiRepository: GeminiRepository,
        private val geminiApiKeyFlow: Flow<String>,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(ChatViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return ChatViewModel(
                chatRepository, connectionRepository, apiClient,
                modelManager, geminiRepository, geminiApiKeyFlow,
            ) as T
        }
    }

    companion object {
        private const val FLUSH_INTERVAL_MS = 250L
        private const val SOCKET_WAIT_MS = 3_000L
        private const val LOCAL_MODEL_NAME = OnDeviceModelManager.MODEL_DISPLAY_NAME

        /**
         * Pure helper: builds the wa.me URL with properly URL-encoded text.
         * Handles special characters, newlines, and emojis.
         */
        fun sendToWhatsApp(message: String): String {
            val encoded = URLEncoder.encode(message, StandardCharsets.UTF_8.toString())
            return "https://wa.me/?text=$encoded"
        }
    }
}

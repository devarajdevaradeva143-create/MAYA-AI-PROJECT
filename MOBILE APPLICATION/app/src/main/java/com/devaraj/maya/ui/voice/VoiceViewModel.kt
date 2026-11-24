package com.devaraj.maya.ui.voice

import android.app.Application
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ChatMessageDto
import com.devaraj.maya.data.remote.ChatRequest
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.repo.ChatRepository
import com.devaraj.maya.domain.model.MessageRole
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class VoicePhase {
    Idle,
    Listening,
    Transcribing,
    Thinking,
    Speaking,
    Error,
}

data class VoiceUiState(
    val phase: VoicePhase = VoicePhase.Idle,
    val transcript: String = "",
    val reply: String = "",
    val recent: List<String> = emptyList(),
    val errorResId: Int? = null,
    val recognizerAvailable: Boolean = true,
)

class VoiceViewModel(
    private val app: Application,
    private val chatRepository: ChatRepository,
    private val connectionRepository: ConnectionRepository,
    private val apiClient: ApiClient,
) : ViewModel() {

    private val _state = MutableStateFlow(VoiceUiState())
    val state: StateFlow<VoiceUiState> = _state.asStateFlow()

    private var speechRecognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var activeConversationId: String? = null
    private var pendingSpeak: String? = null

    init {
        _state.update { it.copy(recognizerAvailable = SpeechRecognizer.isRecognitionAvailable(app)) }
        initTts()
        viewModelScope.launch {
            val conversation = chatRepository.latestConversation() ?: chatRepository.ensureConversation()
            activeConversationId = conversation.id
        }
    }

    private fun initTts() {
        tts = TextToSpeech(app) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            if (ttsReady) {
                tts?.language = Locale.US
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) {
                        _state.update { s ->
                            if (s.phase == VoicePhase.Speaking) s.copy(phase = VoicePhase.Idle) else s
                        }
                    }

                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) {
                        _state.update { s ->
                            if (s.phase == VoicePhase.Speaking) s.copy(phase = VoicePhase.Idle) else s
                        }
                    }

                    override fun onError(utteranceId: String?, errorCode: Int) {
                        _state.update { s ->
                            if (s.phase == VoicePhase.Speaking) s.copy(phase = VoicePhase.Idle) else s
                        }
                    }
                })
                pendingSpeak?.let { speak(it); pendingSpeak = null }
            }
        }
    }

    fun startListening() {
        if (_state.value.phase == VoicePhase.Listening) return
        stopSpeakingInternal()
        if (!SpeechRecognizer.isRecognitionAvailable(app)) {
            _state.update {
                it.copy(
                    phase = VoicePhase.Error,
                    errorResId = com.devaraj.maya.R.string.voice_error_stt_unavailable,
                    recognizerAvailable = false,
                )
            }
            return
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        try {
            speechRecognizer?.destroy()
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(app).apply {
                setRecognitionListener(listener)
                startListening(intent)
            }
            _state.update {
                it.copy(phase = VoicePhase.Listening, transcript = "", reply = "", errorResId = null)
            }
        } catch (_: Exception) {
            _state.update {
                it.copy(phase = VoicePhase.Error, errorResId = com.devaraj.maya.R.string.voice_error_stt_unavailable)
            }
        }
    }

    fun stop() {
        try { speechRecognizer?.stopListening() } catch (_: Exception) {}
        try { speechRecognizer?.cancel() } catch (_: Exception) {}
        stopSpeakingInternal()
        _state.update { s ->
            if (s.phase == VoicePhase.Speaking || s.phase == VoicePhase.Listening || s.phase == VoicePhase.Thinking) {
                s.copy(phase = VoicePhase.Idle)
            } else s
        }
    }

    fun stopSpeaking() {
        stopSpeakingInternal()
        _state.update { s -> if (s.phase == VoicePhase.Speaking) s.copy(phase = VoicePhase.Idle) else s }
    }

    private fun stopSpeakingInternal() {
        try { tts?.stop() } catch (_: Exception) {}
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            _state.update { it.copy(phase = VoicePhase.Listening, errorResId = null) }
        }

        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {
            _state.update { it.copy(phase = VoicePhase.Transcribing) }
        }

        override fun onError(error: Int) {
            val res = when (error) {
                SpeechRecognizer.ERROR_NO_MATCH,
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> com.devaraj.maya.R.string.voice_error_no_match
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> com.devaraj.maya.R.string.voice_mic_permission_body
                else -> com.devaraj.maya.R.string.voice_error_generic
            }
            _state.update { it.copy(phase = VoicePhase.Error, errorResId = res) }
        }

        override fun onResults(results: Bundle?) {
            val text = results
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            if (text.isBlank()) {
                _state.update {
                    it.copy(phase = VoicePhase.Error, errorResId = com.devaraj.maya.R.string.voice_error_no_match)
                }
                return
            }
            onTranscriptFinal(text)
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val text = partialResults
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            if (text.isNotBlank()) {
                _state.update { it.copy(transcript = text) }
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    private fun onTranscriptFinal(text: String) {
        _state.update {
            it.copy(
                transcript = text,
                phase = VoicePhase.Thinking,
                errorResId = null,
                recent = (listOf(text) + it.recent).distinct().take(10),
            )
        }
        sendToMaya(text)
    }

    private fun sendToMaya(text: String) {
        val connection = connectionRepository.state.value
        if (connection !is ConnectionState.Connected) {
            _state.update {
                it.copy(phase = VoicePhase.Error, errorResId = com.devaraj.maya.R.string.voice_error_no_connection)
            }
            return
        }
        viewModelScope.launch {
            try {
                val conversationId = activeConversationId ?: chatRepository.ensureConversation().id.also {
                    activeConversationId = it
                }
                chatRepository.addUserMessage(conversationId, text)
                val history = chatRepository.historyForRequest(conversationId).mapNotNull { msg ->
                    when (msg.role) {
                        MessageRole.USER -> ChatMessageDto("user", msg.content)
                        MessageRole.MAYA -> ChatMessageDto("assistant", msg.content)
                        MessageRole.ASSISTANT -> ChatMessageDto("assistant", msg.content)
                        else -> null
                    }
                }
                val response = withContext(Dispatchers.IO) {
                    apiClient.api(connection.device.host, connection.device.port).chat(
                        ChatRequest(
                            conversationId = conversationId,
                            persona = "maya",
                            messages = history,
                        ),
                    )
                }
                val replyText = response.reply.trim()
                chatRepository.addMayaMessage(
                    conversationId = conversationId,
                    text = replyText,
                    model = response.model,
                )
                _state.update { it.copy(reply = replyText) }
                speak(replyText)
            } catch (_: Exception) {
                _state.update {
                    it.copy(phase = VoicePhase.Error, errorResId = com.devaraj.maya.R.string.voice_error_generic)
                }
            }
        }
    }

    private fun speak(text: String) {
        val clean = text.trim()
        if (clean.isBlank()) {
            _state.update { it.copy(phase = VoicePhase.Idle) }
            return
        }
        if (!ttsReady) {
            pendingSpeak = clean
            _state.update { it.copy(phase = VoicePhase.Speaking) }
            return
        }
        _state.update { it.copy(phase = VoicePhase.Speaking, errorResId = null) }
        tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "maya-voice-reply")
    }

    fun clearError() {
        _state.update { if (it.phase == VoicePhase.Error) it.copy(phase = VoicePhase.Idle, errorResId = null) else it.copy(errorResId = null) }
    }

    override fun onCleared() {
        try { speechRecognizer?.destroy() } catch (_: Exception) {}
        try { tts?.stop() } catch (_: Exception) {}
        try { tts?.shutdown() } catch (_: Exception) {}
        super.onCleared()
    }

    class Factory(
        private val app: Application,
        private val chatRepository: ChatRepository,
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(VoiceViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return VoiceViewModel(app, chatRepository, connectionRepository, apiClient) as T
        }
    }
}

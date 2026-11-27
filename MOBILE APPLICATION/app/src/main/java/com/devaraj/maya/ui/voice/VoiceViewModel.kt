package com.devaraj.maya.ui.voice

import android.app.Application
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.cloud.GeminiRepository
import com.devaraj.maya.data.cloud.GeminiTtsRepository
import com.devaraj.maya.data.model.OnDeviceModelManager
import com.devaraj.maya.data.persona.PersonaPrompts
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ChatMessageDto
import com.devaraj.maya.data.remote.ChatRequest
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.repo.ChatRepository
import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.service.WakeForegroundService
import com.devaraj.maya.voice.GeminiVoicePlayer
import com.devaraj.maya.voice.PiperTts
import com.devaraj.maya.voice.SpeechText
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.text.isNotBlank

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
    /** "auto", "en" or "ta". */
    val sttLanguage: String = "auto",
)

class VoiceViewModel(
    private val app: Application,
    private val chatRepository: ChatRepository,
    private val connectionRepository: ConnectionRepository,
    private val apiClient: ApiClient,
    private val settingsStore: SettingsStore,
    private val piperTts: PiperTts?,
    private val geminiRepository: GeminiRepository?,
    private val onDeviceModel: OnDeviceModelManager?,
    private val geminiTts: GeminiTtsRepository?,
    private val geminiVoicePlayer: GeminiVoicePlayer?,
) : ViewModel() {

    private val _state = MutableStateFlow(VoiceUiState())
    val state: StateFlow<VoiceUiState> = _state.asStateFlow()

    private var speechRecognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var ttsInitFailed = false
    private var activeConversationId: String? = null
    private var pendingSpeak: String? = null
    private var currentTtsEngine: String = "system"
    private var currentTtsSpeed: Float = 1.0f
    private var currentGeminiKey: String = ""
    private var currentSttLanguage: String = "auto"
    private var resumeWakeMicAfterListening = false
    private var listenGeneration = 0
    private var rmsLogTick = 0

    private fun log(message: String) {
        Log.d("MayaVoice", message)
    }

    init {
        _state.update { it.copy(recognizerAvailable = SpeechRecognizer.isRecognitionAvailable(app)) }
        initTts()
        viewModelScope.launch {
            settingsStore.settings.collect { s ->
                currentTtsEngine = s.ttsEngine
                currentTtsSpeed = s.ttsSpeed
                currentGeminiKey = s.geminiApiKey
                currentSttLanguage = s.sttLanguage
                _state.update { it.copy(sttLanguage = s.sttLanguage) }
            }
        }
        viewModelScope.launch {
            val conversation = chatRepository.latestConversation() ?: chatRepository.ensureConversation()
            activeConversationId = conversation.id
        }
    }

    private fun initTts() {
        tts = TextToSpeech(app) { status ->
            ttsReady = status == TextToSpeech.SUCCESS
            ttsInitFailed = !ttsReady
            if (!ttsReady) {
                // Never leave the orb stuck on "Speaking..." when the engine
                // could not start (disabled engine, missing voice data, ...).
                pendingSpeak = null
                _state.update { s ->
                    if (s.phase == VoicePhase.Speaking) {
                        s.copy(
                            phase = VoicePhase.Idle,
                            errorResId = com.devaraj.maya.R.string.voice_error_tts_unavailable,
                        )
                    } else {
                        s
                    }
                }
            } else {
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
        val intent = buildSttIntent()

        // The background wake listener keeps the mic open. Pause it so the
        // recognizer hears the user instead of silence.
        val wakeWasRunning = WakeForegroundService.isRunning
        if (wakeWasRunning) {
            resumeWakeMicAfterListening = true
            WakeForegroundService.pauseMic()
        }

        val generation = ++listenGeneration
        log("start mode=$currentSttLanguage lang=${intent.getStringExtra(RecognizerIntent.EXTRA_LANGUAGE)} wake=$wakeWasRunning")
        _state.update {
            it.copy(phase = VoicePhase.Listening, transcript = "", reply = "", errorResId = null)
        }
        viewModelScope.launch {
            if (wakeWasRunning) delay(300) // let AudioRecord release the mic
            if (generation != listenGeneration) return@launch
            try {
                speechRecognizer?.destroy()
                speechRecognizer = SpeechRecognizer.createSpeechRecognizer(app).apply {
                    setRecognitionListener(listener)
                    startListening(intent)
                }
            } catch (e: Exception) {
                log("recognizer create failed: ${e.message}")
                resumeWakeMic()
                _state.update {
                    it.copy(
                        phase = VoicePhase.Error,
                        errorResId = com.devaraj.maya.R.string.voice_error_stt_unavailable,
                    )
                }
            }
        }
    }

    /** Give the mic back to the wake listener after the voice session. */
    private fun resumeWakeMic() {
        if (!resumeWakeMicAfterListening) return
        resumeWakeMicAfterListening = false
        WakeForegroundService.resumeMic()
    }

    fun setSttLanguage(mode: String) {
        if (mode != "auto" && mode != "en" && mode != "ta") return
        currentSttLanguage = mode
        _state.update { it.copy(sttLanguage = mode) }
        viewModelScope.launch { settingsStore.setSttLanguage(mode) }
    }

    /**
     * Build the recognizer request for the selected language.
     *
     * Auto keeps the phone language as the base and asks the recognizer to
     * detect/switch to Tamil or Indian English. Tamil mode pins `ta-IN`
     * directly, which is the reliable path when the phone locale is English.
     */
    private fun buildSttIntent(): Intent {
        val deviceTag = Locale.getDefault().toLanguageTag()
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            // Tamil usually needs the online model on phones that only have
            // the device language installed on-device.
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
        }
        when (currentSttLanguage) {
            "ta" -> intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ta-IN")
            "en" -> intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, deviceTag)
            else -> {
                val allowed = arrayListOf(deviceTag, "ta-IN", "en-IN")
                    .filter { it.isNotBlank() }
                    .distinct()
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, deviceTag)
                intent.putExtra(RecognizerIntent.EXTRA_ENABLE_LANGUAGE_DETECTION, true)
                intent.putExtra(
                    RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH,
                    RecognizerIntent.LANGUAGE_SWITCH_BALANCED,
                )
                intent.putStringArrayListExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_DETECTION_ALLOWED_LANGUAGES,
                    ArrayList(allowed),
                )
                intent.putStringArrayListExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES,
                    ArrayList(allowed),
                )
            }
        }
        return intent
    }

    fun stop() {
        listenGeneration++
        try { speechRecognizer?.stopListening() } catch (_: Exception) {}
        try { speechRecognizer?.cancel() } catch (_: Exception) {}
        resumeWakeMic()
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
        piperTts?.stop()
        geminiVoicePlayer?.stop()
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            log("ready")
            _state.update { it.copy(phase = VoicePhase.Listening, errorResId = null) }
        }

        override fun onBeginningOfSpeech() {
            log("speech start")
        }

        override fun onRmsChanged(rmsdB: Float) {
            if (rmsLogTick++ % 25 == 0) log("rms=$rmsdB")
        }

        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {
            log("speech end")
            _state.update { it.copy(phase = VoicePhase.Transcribing) }
        }

        override fun onError(error: Int) {
            log("error=$error")
            listenGeneration++
            resumeWakeMic()
            val res = when (error) {
                SpeechRecognizer.ERROR_NO_MATCH,
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> com.devaraj.maya.R.string.voice_error_no_match
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> com.devaraj.maya.R.string.voice_mic_permission_body
                SpeechRecognizer.ERROR_AUDIO -> com.devaraj.maya.R.string.voice_error_audio
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> com.devaraj.maya.R.string.voice_error_mic_busy
                SpeechRecognizer.ERROR_NETWORK,
                SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> com.devaraj.maya.R.string.voice_error_network
                SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED,
                SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> if (currentSttLanguage == "ta") {
                    com.devaraj.maya.R.string.voice_error_tamil_unavailable
                } else {
                    com.devaraj.maya.R.string.voice_error_language
                }
                else -> com.devaraj.maya.R.string.voice_error_generic
            }
            _state.update { it.copy(phase = VoicePhase.Error, errorResId = res) }
        }

        override fun onLanguageDetection(results: Bundle) {
            val language = results.getString(SpeechRecognizer.DETECTED_LANGUAGE)
            val confidence = results.getInt(
                SpeechRecognizer.LANGUAGE_DETECTION_CONFIDENCE_LEVEL,
                SpeechRecognizer.LANGUAGE_DETECTION_CONFIDENCE_LEVEL_UNKNOWN,
            )
            log("language detected=$language confidence=$confidence")
        }

        override fun onResults(results: Bundle?) {
            listenGeneration++
            resumeWakeMic()
            val text = results
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            log("results=${text.take(100)}")
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
                log("partial=${text.take(100)}")
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

                val connection = connectionRepository.state.value
                val modelReady = onDeviceModel?.status?.value?.valid == true
                val geminiReady = geminiRepository != null && currentGeminiKey.isNotBlank()
                log("send connected=${connection is ConnectionState.Connected} model=$modelReady gemini=$geminiReady")

                val reply = withContext(Dispatchers.IO) {
                    when {
                        connection is ConnectionState.Connected -> {
                            val response = apiClient.api(connection.device.host, connection.device.port).chat(
                                ChatRequest(
                                    conversationId = conversationId,
                                    persona = "maya",
                                    messages = history,
                                ),
                            )
                            chatRepository.addMayaMessage(
                                conversationId = conversationId,
                                text = response.reply.trim(),
                                model = response.model,
                                source = AiSource.LAPTOP,
                            )
                            response.reply.trim() to AiSource.LAPTOP
                        }
                        modelReady -> {
                            val prompt = buildVoicePrompt(history)
                            val result = onDeviceModel!!.generate(prompt, 1024)
                            val reply = result.getOrDefault("").trim()
                            if (reply.isNotBlank()) {
                                chatRepository.addMayaMessage(
                                    conversationId = conversationId,
                                    text = reply,
                                    source = AiSource.PHONE,
                                )
                            }
                            reply to AiSource.PHONE
                        }
                        geminiReady -> {
                            val messages = history.mapNotNull { msg ->
                                when (msg.role) {
                                    "user" -> GeminiRepository.GeminiMessage("user", msg.content)
                                    "assistant" -> if (msg.content.isNotBlank()) {
                                        GeminiRepository.GeminiMessage("assistant", msg.content)
                                    } else null
                                    else -> null
                                }
                            }
                            if (messages.isEmpty()) "" to AiSource.NONE else {
                                val reply = geminiRepository!!.chat(
                                    messages = messages,
                                    systemPrompt = PersonaPrompts.forVoice(),
                                    maxTokens = 1024,
                                )
                                chatRepository.addMayaMessage(
                                    conversationId = conversationId,
                                    text = reply.text,
                                    model = reply.model,
                                    source = AiSource.CLOUD,
                                )
                                reply.text.trim() to AiSource.CLOUD
                            }
                        }
                        else -> "" to AiSource.NONE
                    }
                }

                val (replyText, replySource) = reply
                log("reply source=$replySource len=${replyText.length}")
                if (replyText.isBlank()) {
                    _state.update {
                        it.copy(
                            phase = VoicePhase.Error,
                            errorResId = if (!geminiReady && connection !is ConnectionState.Connected && !modelReady) {
                                com.devaraj.maya.R.string.voice_error_no_connection
                            } else {
                                com.devaraj.maya.R.string.voice_error_generic
                            },
                        )
                    }
                    return@launch
                }
                _state.update { it.copy(reply = replyText) }
                speak(replyText, replySource)
            } catch (e: Exception) {
                log("send failed: ${e.message}")
                _state.update {
                    it.copy(phase = VoicePhase.Error, errorResId = com.devaraj.maya.R.string.voice_error_generic)
                }
            }
        }
    }

    private fun buildVoicePrompt(history: List<ChatMessageDto>): String {
        val sb = StringBuilder()
        sb.append("You are Maya, a helpful personal AI assistant. Reply concisely in the same language as the user.\n\n")
        for (msg in history) {
            val role = if (msg.role == "user") "User" else "Maya"
            sb.append("$role: ${msg.content}\n")
        }
        sb.append("Maya: ")
        return sb.toString()
    }

    private fun speak(text: String, source: AiSource = AiSource.NONE) {
        val clean = SpeechText.strip(text)
        log("speak source=$source len=${clean.length}")
        if (clean.isBlank()) {
            _state.update { it.copy(phase = VoicePhase.Idle) }
            return
        }

        // Gemini voice is used ONLY for Gemini (cloud) replies.
        // Laptop and on-device replies keep the system TTS.
        if (source == AiSource.CLOUD && geminiTts != null && geminiVoicePlayer != null) {
            speakGemini(clean)
            return
        }

        val usePiper = currentTtsEngine == "piper" && piperTts?.isLoaded == true

        if (usePiper) {
            _state.update { it.copy(phase = VoicePhase.Speaking, errorResId = null) }
            val ok = piperTts?.speak(clean, currentTtsSpeed) ?: false
            if (!ok) {
                speakSystem(clean)
            }
            return
        }

        speakSystem(clean)
    }

    /**
     * Speak a Gemini reply with the Gemini TTS voice. Any failure (offline,
     * rate limit, missing key) falls back to the on-device system voice.
     */
    private fun speakGemini(text: String) {
        _state.update { it.copy(phase = VoicePhase.Speaking, errorResId = null) }
        viewModelScope.launch {
            try {
                val wav = geminiTts!!.synthesize(text)
                val started = geminiVoicePlayer!!.play(
                    wav = wav,
                    onDone = {
                        _state.update { s ->
                            if (s.phase == VoicePhase.Speaking) s.copy(phase = VoicePhase.Idle) else s
                        }
                    },
                    onError = {
                        viewModelScope.launch { speakSystem(text) }
                    },
                )
                if (!started) speakSystem(text)
            } catch (_: Exception) {
                speakSystem(text)
            }
        }
    }

    /**
     * Pick a TTS language that matches the reply. Tamil script needs `ta-IN`;
     * everything else uses the phone's current locale. If the engine lacks the
     * requested language we fall back to the default locale instead of
     * silently producing no audio.
     */
    private fun applyTtsLanguage(text: String): Boolean {
        val engine = tts ?: return false
        val desired = if (text.any { it.code in 0x0B80..0x0BFF }) {
            Locale.forLanguageTag("ta-IN")
        } else {
            Locale.getDefault()
        }
        val result = try {
            engine.setLanguage(desired)
        } catch (_: Exception) {
            TextToSpeech.LANG_NOT_SUPPORTED
        }
        if (result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED) {
            return true
        }
        val fallback = try {
            engine.setLanguage(Locale.getDefault())
        } catch (_: Exception) {
            TextToSpeech.LANG_NOT_SUPPORTED
        }
        return fallback != TextToSpeech.LANG_MISSING_DATA && fallback != TextToSpeech.LANG_NOT_SUPPORTED
    }

    private fun speakSystem(text: String) {
        val engine = tts
        if (!ttsReady || engine == null) {
            if (ttsInitFailed || engine == null) {
                pendingSpeak = null
                _state.update {
                    it.copy(
                        phase = VoicePhase.Idle,
                        errorResId = com.devaraj.maya.R.string.voice_error_tts_unavailable,
                    )
                }
                return
            }
            // TTS is still initialising; queue the first reply.
            pendingSpeak = text
            _state.update { it.copy(phase = VoicePhase.Speaking) }
            return
        }
        if (!applyTtsLanguage(text)) {
            _state.update {
                it.copy(
                    phase = VoicePhase.Idle,
                    errorResId = com.devaraj.maya.R.string.voice_error_tts_unavailable,
                )
            }
            return
        }
        _state.update { it.copy(phase = VoicePhase.Speaking, errorResId = null) }
        val result = try {
            engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "maya-voice-reply")
        } catch (_: Exception) {
            TextToSpeech.ERROR
        }
        if (result == TextToSpeech.ERROR) {
            _state.update {
                it.copy(
                    phase = VoicePhase.Idle,
                    errorResId = com.devaraj.maya.R.string.voice_error_tts_unavailable,
                )
            }
        }
    }

    fun clearError() {
        _state.update { if (it.phase == VoicePhase.Error) it.copy(phase = VoicePhase.Idle, errorResId = null) else it.copy(errorResId = null) }
    }

    override fun onCleared() {
        resumeWakeMic()
        try { speechRecognizer?.destroy() } catch (_: Exception) {}
        try { tts?.stop() } catch (_: Exception) {}
        try { tts?.shutdown() } catch (_: Exception) {}
        piperTts?.shutdown()
        geminiVoicePlayer?.release()
        super.onCleared()
    }

    class Factory(
        private val app: Application,
        private val chatRepository: ChatRepository,
        private val connectionRepository: ConnectionRepository,
        private val apiClient: ApiClient,
        private val settingsStore: SettingsStore,
        private val piperTts: PiperTts?,
        private val geminiRepository: GeminiRepository?,
        private val onDeviceModel: OnDeviceModelManager?,
        private val geminiTts: GeminiTtsRepository?,
        private val geminiVoicePlayer: GeminiVoicePlayer?,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(VoiceViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return VoiceViewModel(
                app, chatRepository, connectionRepository, apiClient,
                settingsStore, piperTts, geminiRepository, onDeviceModel,
                geminiTts, geminiVoicePlayer,
            ) as T
        }
    }
}

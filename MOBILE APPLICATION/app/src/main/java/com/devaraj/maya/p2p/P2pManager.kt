package com.devaraj.maya.p2p

import android.content.Context
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONException
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import java.nio.ByteBuffer
import java.security.SecureRandom
import java.util.Base64
import java.util.Collections
import java.util.LinkedHashSet

/**
 * One manually signaled, data-channel-only WebRTC session.
 *
 * ICE servers come only from [stunServers] plus the optional [turn]. There is no auto-connect,
 * no cloud relay and no private key in any signaling payload. All candidates are carried inline
 * in the SDP (non-trickle), with `a=candidate:` lines added via `addIceCandidate`.
 */
class P2pManager(
    context: Context,
    private val stunServers: List<String>,
    private val turn: P2pTurn? = null
) {
    private val appContext: Context = context.applicationContext

    private val _state = MutableStateFlow(P2pState.NEW)
    val state: StateFlow<P2pState> = _state.asStateFlow()

    private val _messages = MutableSharedFlow<P2pMessage>(extraBufferCapacity = 128)
    val messages: Flow<P2pMessage> = _messages.asSharedFlow()

    private val channelLock = Any()
    private val frameLock = Any()
    private val channels = LinkedHashMap<String, DataChannel>()
    private val frameBuffers = LinkedHashMap<String, ByteArray>()
    private val pending = Collections.synchronizedSet(LinkedHashSet<CompletableDeferred<*>>())

    private var factory: PeerConnectionFactory? = null
    private var peer: PeerConnection? = null
    private var observer: PcObserver? = null
    private var activeSid: String? = null

    private val fingerprint: String = run {
        val bytes = ByteArray(16)
        SecureRandom().nextBytes(bytes)
        buildString {
            bytes.forEach { b -> append((b.toInt() and 0xff).toString(16).padStart(2, '0')) }
        }
    }

    suspend fun createOffer(): String = withContext(Dispatchers.Default) {
        val connection = newPeerConnection()
        val offerCb = newSdpCallback()
        connection.createOffer(offerCb, MediaConstraints())
        val sdp = offerCb.result.await()

        val localCb = newSdpCallback()
        connection.setLocalDescription(localCb, SessionDescription(SessionDescription.Type.OFFER, sdp))
        localCb.result.await()

        val localSdp = waitForIce(connection)
        val sid = randomSid()
        activeSid = sid
        P2pSignal.encodeOffer(localSdp, fingerprint, sid, System.currentTimeMillis() / 1000L + SIGNAL_TTL_SECONDS)
    }

    suspend fun acceptOffer(offerText: String): String = withContext(Dispatchers.Default) {
        // Decode before touching the current session so bad payloads are non-destructive.
        val offer = P2pSignal.decodeOffer(offerText)
        val connection = newPeerConnection()

        val remoteCb = newSdpCallback()
        connection.setRemoteDescription(remoteCb, SessionDescription(SessionDescription.Type.OFFER, offer.sdp))
        remoteCb.result.await()
        addRemoteCandidates(connection, offer.sdp)

        val answerCb = newSdpCallback()
        connection.createAnswer(answerCb, MediaConstraints())
        val answerSdp = answerCb.result.await()

        val localCb = newSdpCallback()
        connection.setLocalDescription(localCb, SessionDescription(SessionDescription.Type.ANSWER, answerSdp))
        localCb.result.await()

        val localSdp = waitForIce(connection)
        activeSid = offer.sid
        P2pSignal.encodeAnswer(localSdp, fingerprint, offer.sid, System.currentTimeMillis() / 1000L + SIGNAL_TTL_SECONDS)
    }

    suspend fun acceptAnswer(answerText: String) = withContext(Dispatchers.Default) {
        val answer = P2pSignal.decodeAnswer(answerText)
        val connection = peer ?: throw IllegalStateException("No offer was created")
        val expectedSid = activeSid
        if (expectedSid != null && answer.sid != expectedSid) {
            throw IllegalArgumentException("Answer session id does not match the offer")
        }

        val remoteCb = newSdpCallback()
        connection.setRemoteDescription(remoteCb, SessionDescription(SessionDescription.Type.ANSWER, answer.sdp))
        remoteCb.result.await()
        addRemoteCandidates(connection, answer.sdp)
        updateState(P2pState.CONNECTED)
    }

    fun send(channel: String, payload: String) {
        require(channel in CHANNELS) { "Unknown channel: $channel" }
        val target = synchronized(channelLock) { channels[channel] }
            ?: throw IllegalStateException("Channel $channel is not available")
        if (target.state() != DataChannel.State.OPEN) {
            throw IllegalStateException("Channel $channel is not open")
        }

        val payloadObject = try {
            JSONObject(payload)
        } catch (_: JSONException) {
            JSONObject().put("text", payload)
        }
        val body = JSONObject()
            .put("channel", channel)
            .put("payload", payloadObject)
            .toString()
            .toByteArray(Charsets.UTF_8)
        if (body.isEmpty() || body.size > MAX_FRAME_BYTES) {
            throw IllegalArgumentException("Frame size is invalid")
        }
        val framed = ByteBuffer.allocate(4 + body.size).putInt(body.size).put(body).array()
        val sent = target.send(DataChannel.Buffer(ByteBuffer.wrap(framed), true))
        if (!sent) throw IllegalStateException("Failed to send on channel $channel")
    }

    fun close() {
        pending.toList().forEach { it.cancel(CancellationException("P2P session closed")) }
        pending.clear()
        releasePeer()
        activeSid = null
        updateState(P2pState.CLOSED)
    }

    private fun newPeerConnection(): PeerConnection {
        releasePeer()
        ensureInitialized(appContext)

        val newFactory = PeerConnectionFactory.builder()
            .setOptions(PeerConnectionFactory.Options())
            .createPeerConnectionFactory()
        factory = newFactory

        val pcObserver = PcObserver()
        observer = pcObserver
        val connection = newFactory.createPeerConnection(
            PeerConnection.RTCConfiguration(iceServers()),
            MediaConstraints(),
            pcObserver
        ) ?: throw IllegalStateException("Unable to create PeerConnection")
        peer = connection

        synchronized(channelLock) {
            CHANNELS.forEach { name ->
                val dataChannel = connection.createDataChannel(name, DataChannel.Init())
                bindChannel(dataChannel, name)
                channels[name] = dataChannel
            }
        }
        updateState(P2pState.CONNECTING)
        return connection
    }

    private fun releasePeer() {
        synchronized(channelLock) {
            channels.values.forEach { dc ->
                runCatching {
                    dc.unregisterObserver()
                    dc.close()
                    dc.dispose()
                }
            }
            channels.clear()
        }
        synchronized(frameLock) { frameBuffers.clear() }
        peer?.dispose()
        peer = null
        observer = null
        factory?.dispose()
        factory = null
    }

    private fun iceServers(): List<PeerConnection.IceServer> {
        val servers = ArrayList<PeerConnection.IceServer>()
        stunServers.forEach { raw ->
            val url = raw.trim()
            if (url.isNotEmpty()) {
                servers.add(PeerConnection.IceServer.builder(url).createIceServer())
            }
        }
        turn?.let { relay ->
            val host = relay.host.trim()
            if (host.isNotEmpty()) {
                val url = if (host.startsWith("turn:") || host.startsWith("turns:")) host else "turn:$host"
                servers.add(
                    PeerConnection.IceServer.builder(url)
                        .setUsername(relay.username)
                        .setPassword(relay.credential)
                        .createIceServer()
                )
            }
        }
        return servers
    }

    /** Non-trickle: parse `a=candidate:` lines from the remote SDP and feed them to WebRTC. */
    private fun addRemoteCandidates(connection: PeerConnection, sdp: String) {
        var mid = ""
        var lineIndex = -1
        sdp.lineSequence().forEach { raw ->
            val line = raw.trim()
            when {
                line.startsWith("m=") -> {
                    lineIndex++
                    mid = ""
                }
                line.startsWith("a=mid:") -> mid = line.removePrefix("a=mid:").trim()
                line.startsWith("a=candidate:") -> {
                    runCatching {
                        connection.addIceCandidate(IceCandidate(mid, lineIndex, line.removePrefix("a=")))
                    }
                }
            }
        }
    }

    private suspend fun waitForIce(connection: PeerConnection): String {
        val done = observer?.iceDone ?: CompletableDeferred<Unit>()
        if (connection.iceGatheringState() == PeerConnection.IceGatheringState.COMPLETE) {
            done.complete(Unit)
        }
        try {
            withTimeout(ICE_WAIT_MS) { done.await() }
        } catch (_: TimeoutCancellationException) {
            // Match the Python core: proceed with whatever was gathered before the deadline.
        }
        return connection.localDescription?.description
            ?: throw IllegalStateException("No local session description")
    }

    private inner class SdpCallback : SdpObserver {
        val result = CompletableDeferred<String>()

        override fun onCreateSuccess(sdp: SessionDescription) {
            result.complete(sdp.description)
        }

        override fun onCreateFailure(error: String) {
            result.completeExceptionally(IllegalStateException("SDP creation failed: $error"))
        }

        override fun onSetSuccess() {
            result.complete("")
        }

        override fun onSetFailure(error: String) {
            result.completeExceptionally(IllegalStateException("SDP set failed: $error"))
        }
    }

    private fun newSdpCallback(): SdpCallback {
        val callback = SdpCallback()
        pending.add(callback.result)
        callback.result.invokeOnCompletion { pending.remove(callback.result) }
        return callback
    }

    private inner class PcObserver : PeerConnection.Observer {
        @Volatile var iceDone = CompletableDeferred<Unit>()

        override fun onSignalingChange(newState: PeerConnection.SignalingState) = Unit

        override fun onIceConnectionChange(newState: PeerConnection.IceConnectionState) {
            when (newState) {
                PeerConnection.IceConnectionState.CONNECTED,
                PeerConnection.IceConnectionState.COMPLETED -> updateState(P2pState.CONNECTED)
                PeerConnection.IceConnectionState.FAILED,
                PeerConnection.IceConnectionState.DISCONNECTED -> updateState(P2pState.FAILED)
                PeerConnection.IceConnectionState.CLOSED -> updateState(P2pState.CLOSED)
                else -> Unit
            }
        }

        override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit

        override fun onIceGatheringChange(newState: PeerConnection.IceGatheringState) {
            if (newState == PeerConnection.IceGatheringState.COMPLETE) iceDone.complete(Unit)
        }

        override fun onIceCandidate(candidate: IceCandidate) = Unit // non-trickle

        override fun onIceCandidatesRemoved(candidates: Array<IceCandidate>) = Unit

        override fun onAddStream(stream: MediaStream) = Unit

        override fun onRemoveStream(stream: MediaStream) = Unit

        override fun onDataChannel(dataChannel: DataChannel) {
            val label = dataChannel.label()
            synchronized(channelLock) {
                channels[label]?.let { old ->
                    runCatching {
                        old.unregisterObserver()
                        old.close()
                        old.dispose()
                    }
                }
                channels[label] = dataChannel
            }
            bindChannel(dataChannel, label)
        }

        override fun onRenegotiationNeeded() = Unit

        override fun onConnectionChange(newState: PeerConnection.PeerConnectionState) {
            when (newState) {
                PeerConnection.PeerConnectionState.CONNECTING -> updateState(P2pState.CONNECTING)
                PeerConnection.PeerConnectionState.CONNECTED -> updateState(P2pState.CONNECTED)
                PeerConnection.PeerConnectionState.FAILED,
                PeerConnection.PeerConnectionState.DISCONNECTED -> updateState(P2pState.FAILED)
                PeerConnection.PeerConnectionState.CLOSED -> updateState(P2pState.CLOSED)
                PeerConnection.PeerConnectionState.NEW -> Unit
            }
        }
    }

    private fun bindChannel(dataChannel: DataChannel, label: String) {
        dataChannel.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previousAmount: Long) = Unit

            override fun onStateChange() = Unit

            override fun onMessage(buffer: DataChannel.Buffer) {
                val bytes = ByteArray(buffer.data.remaining())
                buffer.data.get(bytes)
                handleFrame(label, bytes)
            }
        })
    }

    /** Reassemble the Python core's 4-byte big-endian length-prefixed JSON frames. */
    private fun handleFrame(label: String, bytes: ByteArray) {
        synchronized(frameLock) {
            val previous = frameBuffers[label] ?: ByteArray(0)
            frameBuffers[label] = previous + bytes
            while (true) {
                val buffer = frameBuffers[label] ?: break
                if (buffer.size < 4) break
                val size = ByteBuffer.wrap(buffer, 0, 4).int
                if (size <= 0 || size > MAX_FRAME_BYTES) {
                    frameBuffers.remove(label)
                    break
                }
                if (buffer.size < 4 + size) break

                val body = String(buffer, 4, size, Charsets.UTF_8)
                frameBuffers[label] = buffer.copyOfRange(4 + size, buffer.size)
                try {
                    val frame = JSONObject(body)
                    val channel = frame.optString("channel")
                    val payload = frame.optJSONObject("payload") ?: continue
                    if (channel in CHANNELS) {
                        _messages.tryEmit(P2pMessage(channel, payload.toString()))
                    }
                } catch (_: JSONException) {
                    // Drop malformed frames; the data channel remains usable.
                }
            }
        }
    }

    private fun updateState(next: P2pState) {
        if (_state.value != P2pState.CLOSED) _state.value = next
    }

    private fun randomSid(): String {
        val bytes = ByteArray(12)
        SecureRandom().nextBytes(bytes)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }

    companion object {
        private val CHANNELS = arrayOf("control", "chat", "files", "screen")
        private const val MAX_FRAME_BYTES = 16 * 1024 * 1024
        private const val ICE_WAIT_MS = 12_000L

        @Volatile private var webRtcInitialized = false
        private val initLock = Any()

        private fun ensureInitialized(context: Context) {
            if (webRtcInitialized) return
            synchronized(initLock) {
                if (!webRtcInitialized) {
                    PeerConnectionFactory.initialize(
                        PeerConnectionFactory.InitializationOptions
                            .builder(context.applicationContext)
                            .createInitializationOptions()
                    )
                    webRtcInitialized = true
                }
            }
        }
    }
}

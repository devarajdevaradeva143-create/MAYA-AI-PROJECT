package com.devaraj.maya.service

import android.content.Context
import android.net.Uri
import android.os.Build
import android.util.Log
import com.devaraj.maya.MayaApp
import com.devaraj.maya.data.remote.ApiError
import com.devaraj.maya.data.remote.ApiErrorEnvelope
import com.devaraj.maya.data.remote.FileEntryDto
import com.devaraj.maya.data.remote.FileListDto
import com.devaraj.maya.data.remote.FileRootsDto
import com.devaraj.maya.data.remote.FileUploadDto
import com.devaraj.maya.data.remote.InputEventDto
import com.devaraj.maya.data.remote.InputRequest
import com.devaraj.maya.data.remote.InputResponse
import com.devaraj.maya.data.remote.RemoteConfirmRequest
import com.devaraj.maya.data.remote.RemoteRequestStatusResponse
import com.devaraj.maya.data.remote.RemoteSessionDto
import com.devaraj.maya.data.remote.RemoteStartResponse
import com.devaraj.maya.data.remote.RemoteStopRequest
import com.devaraj.maya.data.remote.ScreenInfo
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.ByteArrayOutputStream
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.ResponseBody
import okio.ByteString
import java.io.File
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/**
 * Minimal HTTP/WebSocket server for phone remote control.
 * Runs on port 8421 (LAN only). Handles screen streaming, input injection, and file ops.
 */
class PhoneRemoteHttpServer private constructor(
    private val context: Context,
    private val accessibilityService: MayaAccessibilityService,
    private val screenCapture: ScreenCaptureService?,
) {

    companion object {
        private const val TAG = "PhoneRemoteHttpServer"
        const val PORT = 8421
        private const val SESSION_TTL_MS = 5 * 60 * 1000 // 5 minutes
        private const val MAX_UPLOAD_BYTES = 25L * 1024 * 1024
        private const val TOKEN_PREFIX = "maya_"
        private const val TOKEN_RANDOM_CHARS = 43
        private const val REQUEST_TTL_MS = 60_000L

        @Volatile
        private var instance: PhoneRemoteHttpServer? = null

        private val sessions = ConcurrentHashMap<String, RemoteSession>()
        private val pendingRequests = ConcurrentHashMap<String, PendingRequest>()

        enum class RequestStatus { PENDING, ALLOWED, DENIED, EXPIRED, CONSUMED }

        data class RemoteSession(
            val token: String,
            val createdAt: Long,
            var lastAccessed: Long,
            val clientIp: String,
            var webSocketJob: Job? = null,
        ) {
            fun isExpired(): Boolean = System.currentTimeMillis() - lastAccessed > SESSION_TTL_MS
            fun touch() { lastAccessed = System.currentTimeMillis() }
        }

        data class PendingRequest(
            val id: String,
            val createdAt: Long,
            val clientIp: String,
            val description: String,
            @Volatile var status: RequestStatus = RequestStatus.PENDING,
            @Volatile var sessionToken: String? = null,
        ) {
            fun isExpired(): Boolean = System.currentTimeMillis() - createdAt > REQUEST_TTL_MS
        }

        private val _pendingRequest = MutableStateFlow<PendingRequest?>(null)
        val pendingRequest: StateFlow<PendingRequest?> = _pendingRequest

        fun start(
            context: Context,
            accessibilityService: MayaAccessibilityService,
            screenCapture: ScreenCaptureService?,
        ): PhoneRemoteHttpServer? {
            if (instance != null) {
                instance?.stop()
            }
            instance = PhoneRemoteHttpServer(context, accessibilityService, screenCapture)
            instance?.startServer()
            return instance
        }

        fun getInstance(): PhoneRemoteHttpServer? = instance

        fun stop() {
            instance?.stop()
            instance = null
            sessions.values.forEach { it.webSocketJob?.cancel() }
            sessions.clear()
            pendingRequests.clear()
            _pendingRequest.value = null
        }

        fun isRunning(): Boolean = instance?.isRunning?.get() == true

        fun getActiveSessionCount(): Int = sessions.count { !it.value.isExpired() }

        fun cleanExpiredSessions() {
            val now = System.currentTimeMillis()
            sessions.entries.removeIf { (_, session) ->
                if (session.isExpired()) {
                    session.webSocketJob?.cancel()
                    true
                } else false
            }
            pendingRequests.entries.removeIf { (_, req) ->
                if (req.isExpired() && req.status == RequestStatus.PENDING) req.status = RequestStatus.EXPIRED
                req.isExpired() && req.status != RequestStatus.PENDING && req.status != RequestStatus.ALLOWED
            }
            val cur = _pendingRequest.value
            if (cur != null && (cur.status != RequestStatus.PENDING || cur.isExpired())) {
                _pendingRequest.value = null
            }
        }

        fun createSession(clientIp: String): RemoteSession {
            cleanExpiredSessions()
            sessions.values.removeIf { it.clientIp == clientIp && !it.isExpired() }
            val token = generateToken()
            val session = RemoteSession(token, System.currentTimeMillis(), System.currentTimeMillis(), clientIp)
            sessions[token] = session
            return session
        }

        fun createPendingRequest(clientIp: String, description: String): PendingRequest {
            cleanExpiredSessions()
            pendingRequests.values.removeIf { it.clientIp == clientIp && (it.isExpired() || it.status != RequestStatus.PENDING) }
            val request = PendingRequest(
                id = generateToken(),
                createdAt = System.currentTimeMillis(),
                clientIp = clientIp,
                description = description,
            )
            pendingRequests[request.id] = request
            _pendingRequest.value = request
            return request
        }

        fun getRequest(id: String): PendingRequest? {
            val req = pendingRequests[id] ?: return null
            if (req.isExpired() && req.status == RequestStatus.PENDING) {
                req.status = RequestStatus.EXPIRED
                if (_pendingRequest.value?.id == id) _pendingRequest.value = null
            }
            return req
        }

        fun approveRequest(id: String): PendingRequest? {
            val req = pendingRequests[id] ?: return null
            if (req.isExpired()) {
                req.status = RequestStatus.EXPIRED
                if (_pendingRequest.value?.id == id) _pendingRequest.value = null
                return null
            }
            if (req.status != RequestStatus.PENDING) return req
            val session = createSession(req.clientIp)
            req.sessionToken = session.token
            req.status = RequestStatus.ALLOWED
            if (_pendingRequest.value?.id == id) _pendingRequest.value = null
            return req
        }

        fun denyRequest(id: String): PendingRequest? {
            val req = pendingRequests[id] ?: return null
            if (req.status == RequestStatus.PENDING) req.status = RequestStatus.DENIED
            if (_pendingRequest.value?.id == id) _pendingRequest.value = null
            return req
        }

        fun consumeAllowedRequest(id: String): PendingRequest? {
            val req = pendingRequests[id] ?: return null
            if (req.status == RequestStatus.ALLOWED) {
                req.status = RequestStatus.CONSUMED
            }
            return req
        }

        fun validateSession(token: String, clientIp: String): RemoteSession? {
            val session = sessions[token] ?: return null
            if (session.clientIp != clientIp || session.isExpired()) {
                sessions.remove(token)
                return null
            }
            session.touch()
            return session
        }

        fun hasActiveSession(clientIp: String): Boolean =
            sessions.values.any { it.clientIp == clientIp && !it.isExpired() }

        private fun generateToken(): String {
            val random = SecureRandom()
            val bytes = ByteArray(TOKEN_RANDOM_CHARS * 3 / 4)
            random.nextBytes(bytes)
            return TOKEN_PREFIX + android.util.Base64.encodeToString(
                bytes, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP
            ).substring(0, TOKEN_RANDOM_CHARS)
        }

        fun getSession(token: String): RemoteSession? = sessions[token]
    }

    private val serverScope = CoroutineScope(Dispatchers.IO)
    private val serverThread = Thread({ runServer() }, "PhoneRemoteHttpServer")
    private val isRunning = AtomicBoolean(false)
    private val executor = Executors.newCachedThreadPool()
    private var serverSocket: ServerSocket? = null

    private val _state = MutableStateFlow(ServerState.STOPPED)
    val state: StateFlow<ServerState> = _state

    enum class ServerState { STOPPED, STARTING, RUNNING, STOPPING }

    private fun startServer() {
        if (isRunning.getAndSet(true)) return
        _state.value = ServerState.STARTING
        serverThread.start()
    }

    private fun runServer() {
        try {
            serverSocket = ServerSocket()
            serverSocket?.setReuseAddress(true)
            serverSocket?.bind(InetSocketAddress(PORT))
            _state.value = ServerState.RUNNING
            Log.i(TAG, "Phone remote server started on port $PORT")

            while (isRunning.get()) {
                try {
                    val socket = serverSocket?.accept() ?: break
                    executor.execute { handleClient(socket) }
                } catch (e: Exception) {
                    if (isRunning.get()) Log.w(TAG, "Accept error", e)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Server error", e)
        } finally {
            stopServer()
        }
    }

    private fun stopServer() {
        isRunning.set(false)
        _state.value = ServerState.STOPPING
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing server socket", e)
        }
        executor.shutdown()
        try {
            executor.awaitTermination(2, TimeUnit.SECONDS)
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        _state.value = ServerState.STOPPED
        Log.i(TAG, "Phone remote server stopped")
    }

    private fun handleClient(socket: Socket) {
        socket.use { s ->
            s.soTimeout = 10000
            val input = s.getInputStream()
            val output = s.getOutputStream()

            val requestLine = readLine(input) ?: return
            val parts = requestLine.split(' ')
            if (parts.size < 3) return

            val method = parts[0].uppercase()
            val path = parts[1]
            val headers = readHeaders(input)
            val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
            val isUpload = method == "POST" && path == "/phone/remote/files/upload"
            val body = if (!isUpload && contentLength > 0) readBody(input, contentLength) else ""
            val clientIp = s.inetAddress.hostAddress ?: "unknown"

            try {
                if (method == "OPTIONS") {
                    sendResponse(output, 204, "", "text/plain")
                    return
                }
                val sessionTokenCandidate = when {
                    method == "POST" && path == "/phone/remote/stop" -> extractSessionToken(body)
                    method == "POST" && path == "/phone/remote/input" -> extractSessionToken(body)
                    method == "POST" && path == "/phone/remote/files/list" -> extractSessionToken(body)
                    method == "GET" && path.startsWith("/phone/remote/files/download") -> Uri.parse("http://localhost$path").getQueryParameter("session_token")
                    else -> null
                }
                val isPublic = (method == "POST" && path == "/phone/remote/start") ||
                    (method == "GET" && path.startsWith("/phone/remote/request/")) ||
                    (method == "POST" && path == "/phone/remote/confirm") ||
                    (method == "POST" && path == "/phone/remote/files/upload") // upload handler validates session after multipart parse
                val sessionOk = !sessionTokenCandidate.isNullOrBlank() && validateSession(sessionTokenCandidate, clientIp) != null
                if (!isPublic && !sessionOk && !isAuthorized(headers, path)) {
                    sendResponse(output, 401, "Unauthorized", "text/plain")
                    return
                }
                when {
                    method == "POST" && path == "/phone/remote/start" -> handleStart(output, clientIp)
                    method == "GET" && path.startsWith("/phone/remote/request/") -> {
                        val id = path.removePrefix("/phone/remote/request/").substringBefore('?')
                        handleRequestStatus(output, id, clientIp, s.localAddress.hostAddress ?: "127.0.0.1")
                    }
                    method == "POST" && path == "/phone/remote/confirm" -> handleConfirm(output, body, clientIp, s.localAddress.hostAddress ?: "127.0.0.1")
                    method == "POST" && path == "/phone/remote/stop" -> handleStop(output, body, clientIp)
                    method == "POST" && path == "/phone/remote/input" -> handleInput(output, body, clientIp)
                    method == "POST" && path == "/phone/remote/files/list" -> handleFileList(output, body, clientIp)
                    method == "GET" && path.startsWith("/phone/remote/files/download") -> handleFileDownload(output, path, clientIp)
                    method == "POST" && path == "/phone/remote/files/upload" -> handleFileUpload(output, headers, input, clientIp)
                    path.startsWith("/phone/remote/ws") -> handleWebSocket(s, path, clientIp, headers)
                    else -> sendResponse(output, 404, "Not Found", "text/plain")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Request failed: $method $path", e)
                try { sendResponse(output, 500, "Internal error", "text/plain") } catch (_: Exception) {}
            }
        }
    }

    private fun isAuthorized(headers: Map<String, String>, path: String = ""): Boolean {
        // WS can carry token in query; HTTP uses Bearer.
        val auth = headers["authorization"]?.trim().orEmpty()
        val bearer = if (auth.startsWith("Bearer ", ignoreCase = true)) auth.substringAfter(' ').trim() else ""
        val queryToken = Uri.parse("http://localhost$path").getQueryParameter("token").orEmpty()
        val token = bearer.ifBlank { queryToken }
        if (token.isBlank()) return false
        // Allow active session token for remote endpoints
        if (sessions.containsKey(token)) return true
        val app = context.applicationContext as? MayaApp ?: return false
        val container = app.container
        container.session.activeDeviceId?.let { id ->
            container.tokenVault.load(id)?.let { if (constantTimeEquals(token, it)) return true }
        }
        val ids = runBlocking { container.database.deviceDao().getAll().map { it.id } }
        for (id in ids) {
            val expected = container.tokenVault.load(id) ?: continue
            if (constantTimeEquals(token, expected)) return true
        }
        return false
    }

    private fun extractSessionToken(body: String): String? = try {
        Json { ignoreUnknownKeys = true }.parseToJsonElement(body).jsonObject["session_token"]?.jsonPrimitive?.content
    } catch (_: Exception) { null }

    private fun constantTimeEquals(a: String, b: String): Boolean {
        val aa = a.toByteArray(StandardCharsets.UTF_8)
        val bb = b.toByteArray(StandardCharsets.UTF_8)
        if (aa.size != bb.size) return false
        var r = 0
        for (i in aa.indices) r = r or (aa[i].toInt() xor bb[i].toInt())
        return r == 0
    }

    private fun readLine(input: java.io.InputStream): String? {
        val buffer = StringBuilder()
        var c = input.read()
        while (c != -1 && c != 10) { // \n
            if (c != 13) buffer.append(c.toChar()) // skip \r
            c = input.read()
        }
        return if (buffer.isNotEmpty()) buffer.toString() else null
    }

    private fun readHeaders(input: java.io.InputStream): Map<String, String> {
        val headers = mutableMapOf<String, String>()
        while (true) {
            val line = readLine(input) ?: break
            if (line.isBlank()) break
            val idx = line.indexOf(':')
            if (idx > 0) {
                headers[line.substring(0, idx).lowercase().trim()] = line.substring(idx + 1).trim()
            }
        }
        return headers
    }

    private fun readBody(input: java.io.InputStream, length: Int): String {
        val buffer = ByteArray(length)
        var read = 0
        while (read < length) {
            val r = input.read(buffer, read, length - read)
            if (r == -1) break
            read += r
        }
        return String(buffer, 0, read, StandardCharsets.UTF_8)
    }

    private fun sendResponse(output: java.io.OutputStream, status: Int, body: String, contentType: String) {
        val bytes = body.toByteArray(StandardCharsets.UTF_8)
        val response = "HTTP/1.1 $status ${getStatusText(status)}\r\n" +
            "Content-Type: $contentType\r\n" +
            "Content-Length: ${bytes.size}\r\n" +
            "Connection: close\r\n\r\n"
        output.write(response.toByteArray(StandardCharsets.UTF_8))
        output.write(bytes)
        output.flush()
    }

    private inline fun <reified T> sendJson(output: java.io.OutputStream, status: Int, obj: T) {
        val json = Json.encodeToString(obj)
        sendResponse(output, status, json, "application/json")
    }

    private fun getStatusText(status: Int): String = when (status) {
        200 -> "OK"
        201 -> "Created"
        400 -> "Bad Request"
        401 -> "Unauthorized"
        403 -> "Forbidden"
        404 -> "Not Found"
        500 -> "Internal Server Error"
        else -> "Unknown"
    }

    private fun handleStart(output: java.io.OutputStream, clientIp: String) {
        if (!MayaAccessibilityService.isEnabled(context)) {
            sendJson(output, 403, RemoteStartResponse(status = "error", description = "Accessibility service not enabled"))
            return
        }
        val capture = ScreenCaptureService.getInstance()
        if (capture == null || !capture.isCapturingValue) {
            sendJson(output, 409, RemoteStartResponse(status = "needs_screen_share", description = "Start screen share on phone first"))
            return
        }
        val pending = createPendingRequest(clientIp, "Allow laptop to control this phone?")
        // Surface phone-side consent prompt via foreground notification tap target; UI observes pendingRequest.
        PhoneRemoteForegroundService.start(context)
        sendJson(output, 200, RemoteStartResponse(
            status = "pending",
            requestId = pending.id,
            description = pending.description,
            expiresIn = (REQUEST_TTL_MS / 1000).toInt(),
        ))
    }

    private fun handleRequestStatus(output: java.io.OutputStream, requestId: String, clientIp: String, localIp: String) {
        val req = getRequest(requestId)
        if (req == null || req.clientIp != clientIp) {
            sendJson(output, 404, RemoteRequestStatusResponse(status = "not_found", requestId = requestId))
            return
        }
        when (req.status) {
            RequestStatus.PENDING -> {
                if (req.isExpired()) {
                    req.status = RequestStatus.EXPIRED
                    sendJson(output, 200, RemoteRequestStatusResponse(status = "expired", requestId = requestId))
                } else {
                    sendJson(output, 200, RemoteRequestStatusResponse(status = "pending", requestId = requestId, expiresIn = ((REQUEST_TTL_MS - (System.currentTimeMillis() - req.createdAt)) / 1000).toInt().coerceAtLeast(0)))
                }
            }
            RequestStatus.DENIED -> sendJson(output, 200, RemoteRequestStatusResponse(status = "denied", requestId = requestId))
            RequestStatus.EXPIRED -> sendJson(output, 200, RemoteRequestStatusResponse(status = "expired", requestId = requestId))
            RequestStatus.CONSUMED -> sendJson(output, 200, RemoteRequestStatusResponse(status = "consumed", requestId = requestId))
            RequestStatus.ALLOWED -> {
                val token = req.sessionToken
                val session = token?.let { sessions[it] }
                if (token == null || session == null || session.isExpired()) {
                    req.status = RequestStatus.EXPIRED
                    sendJson(output, 200, RemoteRequestStatusResponse(status = "expired", requestId = requestId))
                } else {
                    consumeAllowedRequest(requestId)
                    val metrics = context.resources.displayMetrics
                    sendJson(output, 200, RemoteRequestStatusResponse(
                        status = "started",
                        requestId = requestId,
                        sessionToken = token,
                        wsUrl = "ws://$localIp:$PORT/phone/remote/ws?token=$token",
                        expiresIn = (SESSION_TTL_MS / 1000).toInt(),
                        screen = ScreenInfo(metrics.widthPixels, metrics.heightPixels, metrics.densityDpi),
                    ))
                }
            }
        }
    }

    private fun handleConfirm(output: java.io.OutputStream, body: String, clientIp: String, localIp: String) {
        // Back-compat: treat confirm_token as request_id for older clients.
        val request = try { Json { ignoreUnknownKeys = true }.decodeFromString<RemoteConfirmRequest>(body) } catch (_: Exception) { null }
        val id = request?.confirmToken
        if (id.isNullOrBlank()) {
            sendJson(output, 400, RemoteStartResponse(status = "error", description = "Missing confirm token"))
            return
        }
        handleRequestStatus(output, id, clientIp, localIp)
    }

    private fun handleStop(output: java.io.OutputStream, body: String, clientIp: String) {
        val request = try {
            Json { ignoreUnknownKeys = true }.decodeFromString<RemoteStopRequest>(body)
        } catch (_: Exception) {
            sendJson(output, 400, RemoteStartResponse(status = "error", description = "Invalid request"))
            return
        }
        val session = validateSession(request.sessionToken, clientIp)
        if (session == null) {
            sendJson(output, 401, RemoteStartResponse(status = "error", description = "Invalid or expired session"))
            return
        }
        stopSession(request.sessionToken)
        sendJson(output, 200, RemoteStartResponse(status = "done"))
    }

    private fun stopSession(token: String) {
        val session = sessions.remove(token) ?: return
        session.webSocketJob?.cancel()
        if (getActiveSessionCount() == 0) {
            PhoneRemoteForegroundService.stop(context)
        }
    }

    fun stopAllSessions() {
        sessions.values.forEach { it.webSocketJob?.cancel() }
        sessions.clear()
        pendingRequests.clear()
        _pendingRequest.value = null
    }

    private fun handleInput(output: java.io.OutputStream, body: String, clientIp: String) {
        val request = try {
            Json { ignoreUnknownKeys = true }.decodeFromString<InputRequest>(body)
        } catch (e: Exception) {
            sendJson(output, 400, InputResponse(status = "error", applied = 0))
            return
        }

        val session = PhoneRemoteHttpServer.validateSession(request.sessionToken, clientIp)
        if (session == null) {
            sendJson(output, 401, InputResponse(status = "error", applied = 0))
            return
        }

        var applied = 0
        for (event in request.events) {
            if (accessibilityService.injectInput(event)) {
                applied++
            }
        }
        sendJson(output, 200, InputResponse(status = "done", applied = applied))
    }

    private fun handleFileList(output: java.io.OutputStream, body: String, clientIp: String) {
        // Parse request: { "session_token": "...", "path": "..." }
        val json = Json { ignoreUnknownKeys = true }
        val map = try {
            json.decodeFromString<Map<String, String>>(body)
        } catch (e: Exception) {
            sendJson(output, 400, FileListDto(path = "", entries = emptyList()))
            return
        }

        val session = PhoneRemoteHttpServer.validateSession(map["session_token"] ?: "", clientIp)
        if (session == null) {
            sendJson(output, 401, FileListDto(path = "", entries = emptyList()))
            return
        }

        val path = map["path"] ?: "/"
        val entries = listFilesSaf(path)
        sendJson(output, 200, FileListDto(path = path, entries = entries))
    }

    private fun handleFileDownload(output: java.io.OutputStream, path: String, clientIp: String) {
        // Parse query params: /phone/remote/files/download?session_token=...&path=...
        val uri = Uri.parse("http://localhost$path")
        val sessionToken = uri.getQueryParameter("session_token")
        val filePath = uri.getQueryParameter("path")

        if (sessionToken.isNullOrBlank() || filePath.isNullOrBlank()) {
            sendResponse(output, 400, "Missing parameters", "text/plain")
            return
        }

        val session = PhoneRemoteHttpServer.validateSession(sessionToken, clientIp)
        if (session == null) {
            sendResponse(output, 401, "Invalid or expired session", "text/plain")
            return
        }

        try {
            val file = File(filePath)
            if (!file.exists() || !file.isFile) {
                sendResponse(output, 404, "File not found", "text/plain")
                return
            }

            // Check if path is within allowed SAF roots (simplified check)
            if (!isPathAllowed(filePath)) {
                sendResponse(output, 403, "Access denied", "text/plain")
                return
            }

            val response = "HTTP/1.1 200 OK\r\n" +
                "Content-Type: application/octet-stream\r\n" +
                "Content-Length: ${file.length()}\r\n" +
                "Content-Disposition: attachment; filename=\"${file.name}\"\r\n" +
                "Connection: close\r\n\r\n"
            output.write(response.toByteArray(StandardCharsets.UTF_8))

            file.inputStream().use { input ->
                input.copyTo(output)
            }
            output.flush()
        } catch (e: Exception) {
            Log.e(TAG, "Download error", e)
            sendResponse(output, 500, "Download failed", "text/plain")
        }
    }

    private fun handleFileUpload(
        output: java.io.OutputStream,
        headers: Map<String, String>,
        input: java.io.InputStream,
        clientIp: String,
    ) {
        val contentType = headers["content-type"] ?: ""
        if (!contentType.startsWith("multipart/form-data")) {
            sendJson(output, 400, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        val boundary = contentType.substringAfter("boundary=", "").trim().trim('"')
        if (boundary.isBlank()) {
            sendJson(output, 400, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        val contentLength = headers["content-length"]?.toLongOrNull() ?: -1L
        if (contentLength <= 0) {
            sendJson(output, 411, FileUploadDto(status = "error", path = "", size = 0))
            return
        }
        if (contentLength > MAX_UPLOAD_BYTES) {
            sendJson(output, 413, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        val body = readExactBytes(input, contentLength.toInt())
        if (body == null) {
            sendJson(output, 400, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        var sessionToken: String? = null
        var requestedPath: String? = null
        var fileBytes: ByteArray? = null
        var fileName: String? = null
        for (part in parseMultipart(body, boundary)) {
            when (part.name) {
                "session_token" -> sessionToken = String(part.data, StandardCharsets.UTF_8).trim()
                "path" -> requestedPath = String(part.data, StandardCharsets.UTF_8).trim()
                "file" -> {
                    fileBytes = part.data
                    fileName = part.fileName
                }
            }
        }

        if (validateSession(sessionToken.orEmpty(), clientIp) == null) {
            sendJson(output, 401, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        val bytes = fileBytes
        val safeName = (fileName ?: "").substringAfterLast('/').substringAfterLast('\\')
        if (bytes == null || safeName.isBlank() || safeName.contains("..")) {
            sendJson(output, 400, FileUploadDto(status = "error", path = "", size = 0))
            return
        }

        val directory = File(requestedPath?.takeIf { it.isNotBlank() } ?: context.filesDir.absolutePath)
        val target = if (directory.isDirectory || !directory.exists()) File(directory, safeName) else directory

        if (!isPathAllowed(target.absolutePath)) {
            sendJson(output, 403, FileUploadDto(status = "error", path = target.absolutePath, size = 0))
            return
        }

        try {
            target.parentFile?.takeIf { !it.exists() }?.mkdirs()
            target.writeBytes(bytes)
            sendJson(output, 200, FileUploadDto(status = "done", path = target.absolutePath, size = bytes.size))
        } catch (e: Exception) {
            Log.e(TAG, "Upload failed", e)
            sendJson(output, 500, FileUploadDto(status = "error", path = target.absolutePath, size = 0))
        }
    }

    private data class MultipartPart(val name: String?, val fileName: String?, val data: ByteArray)

    /** Parses a multipart/form-data body into its named parts. */
    private fun parseMultipart(body: ByteArray, boundary: String): List<MultipartPart> {
        val delimiter = "--$boundary".toByteArray(StandardCharsets.ISO_8859_1)
        val crlf = "\r\n".toByteArray(StandardCharsets.ISO_8859_1)
        val parts = mutableListOf<MultipartPart>()
        var index = indexOfBytes(body, delimiter, 0)
        while (index >= 0) {
            var start = index + delimiter.size
            // A closing delimiter ("--boundary--") ends the body.
            if (start + 1 < body.size && body[start] == '-'.code.toByte() && body[start + 1] == '-'.code.toByte()) break
            if (start + 1 < body.size && body[start] == crlf[0] && body[start + 1] == crlf[1]) start += 2
            val next = indexOfBytes(body, delimiter, start)
            if (next < 0) break
            var end = next
            if (end - 2 >= start && body[end - 2] == crlf[0] && body[end - 1] == crlf[1]) end -= 2
            parts += parsePart(body, start, end)
            index = next
        }
        return parts
    }

    private fun parsePart(body: ByteArray, start: Int, end: Int): MultipartPart {
        val headerSeparator = "\r\n\r\n".toByteArray(StandardCharsets.ISO_8859_1)
        val headerEnd = indexOfBytes(body, headerSeparator, start)
        if (headerEnd < 0 || headerEnd + headerSeparator.size > end) {
            return MultipartPart(null, null, ByteArray(0))
        }
        val headerText = String(body, start, headerEnd - start, StandardCharsets.UTF_8)
        val data = body.copyOfRange(headerEnd + headerSeparator.size, end)
        val name = Regex("name=\"([^\"]*)\"").find(headerText)?.groupValues?.get(1)
        val fileName = Regex("filename=\"([^\"]*)\"").find(headerText)?.groupValues?.get(1)
        return MultipartPart(name, fileName, data)
    }

    private fun indexOfBytes(haystack: ByteArray, needle: ByteArray, from: Int): Int {
        if (needle.isEmpty() || from < 0) return -1
        outer@ for (i in from..haystack.size - needle.size) {
            for (j in needle.indices) {
                if (haystack[i + j] != needle[j]) continue@outer
            }
            return i
        }
        return -1
    }

    private fun readExactBytes(input: java.io.InputStream, length: Int): ByteArray? {
        val buffer = ByteArray(length)
        var read = 0
        while (read < length) {
            val r = input.read(buffer, read, length - read)
            if (r == -1) break
            read += r
        }
        return if (read == length) buffer else null
    }

    private fun handleWebSocket(socket: Socket, path: String, clientIp: String, headers: Map<String, String>) {
        if (!isAuthorized(headers, path)) {
            sendResponse(socket.getOutputStream(), 401, "Unauthorized", "text/plain")
            return
        }
        val uri = Uri.parse("http://localhost$path")
        val token = uri.getQueryParameter("token")
        if (token.isNullOrBlank()) {
            sendResponse(socket.getOutputStream(), 400, "Missing token", "text/plain")
            return
        }
        val session = validateSession(token, clientIp)
        if (session == null) {
            sendResponse(socket.getOutputStream(), 401, "Invalid session", "text/plain")
            return
        }
        if (!upgradeWebSocket(socket, headers["sec-websocket-key"] ?: "")) return

        val capture = ScreenCaptureService.getInstance()
        if (capture == null || !capture.isCapturingValue) {
            sendWebSocketText(socket.getOutputStream(), """{"type":"error","message":"Screen share not active"}""")
            try { socket.close() } catch (_: Exception) {}
            return
        }

        val wsJob = serverScope.launch {
            try {
                val out = socket.getOutputStream()
                val metrics = context.resources.displayMetrics
                sendWebSocketText(out, """{"type":"screen_info","width":${metrics.widthPixels},"height":${metrics.heightPixels},"density":${metrics.densityDpi}}""")
                capture.frames.collect { frame ->
                    if (!isRunning.get()) return@collect
                    sendWebSocketBinary(out, frame)
                }
            } catch (e: Exception) {
                Log.w(TAG, "WebSocket error", e)
            } finally {
                session.webSocketJob = null
                try { socket.close() } catch (_: Exception) {}
            }
        }
        session.webSocketJob = wsJob

        serverScope.launch {
            try {
                val wsIn = socket.getInputStream()
                while (isRunning.get() && !socket.isClosed) {
                    val frame = readWebSocketFrame(wsIn) ?: break
                    when (frame.opcode) {
                        0x8 -> break
                        0x9 -> sendWebSocketFrame(socket.getOutputStream(), 0xA, frame.payload)
                        0x1 -> handleWsText(frame.payload.toString(StandardCharsets.UTF_8), session, clientIp)
                    }
                }
            } catch (_: Exception) {
            } finally {
                wsJob.cancel()
            }
        }
        runBlocking { wsJob.join() }
    }

    private data class WsFrame(val opcode: Int, val payload: ByteArray)

    private fun readWebSocketFrame(input: java.io.InputStream): WsFrame? {
        val b0 = input.read()
        val b1 = input.read()
        if (b0 == -1 || b1 == -1) return null
        val opcode = b0 and 0x0F
        var len = (b1 and 0x7F).toLong()
        if (len == 126L) {
            val hi = input.read(); val lo = input.read()
            if (hi == -1 || lo == -1) return null
            len = ((hi shl 8) or lo).toLong()
        } else if (len == 127L) {
            len = 0
            repeat(8) {
                val b = input.read()
                if (b == -1) return null
                len = (len shl 8) or b.toLong()
            }
        }
        val masked = (b1 and 0x80) != 0
        val mask = ByteArray(4)
        if (masked) {
            if (readExactBytes(input, 4)?.copyInto(mask) == null) return null
        }
        if (len > 1_000_000L) return null
        val payload = readExactBytes(input, len.toInt()) ?: return null
        if (masked) for (i in payload.indices) payload[i] = (payload[i].toInt() xor mask[i % 4].toInt()).toByte()
        return WsFrame(opcode, payload)
    }

    private fun handleWsText(text: String, session: RemoteSession, clientIp: String) {
        try {
            val json = Json { ignoreUnknownKeys = true }
            val obj = json.parseToJsonElement(text).jsonObject
            val type = obj["type"]?.jsonPrimitive?.content
            if (type == "input") {
                val req = json.decodeFromString<InputRequest>(text)
                if (req.sessionToken != session.token) return
                validateSession(session.token, clientIp) ?: return
                for (ev in req.events) accessibilityService.injectInput(ev)
            } else if (type == "ping") {
                // handled by WS frame ping/pong; text ping ignored
            }
        } catch (_: Exception) {}
    }

    private fun upgradeWebSocket(socket: Socket, key: String): Boolean {
        // Compute the Sec-WebSocket-Accept value from the client's key (RFC 6455).
        val response = "HTTP/1.1 101 Switching Protocols\r\n" +
            "Upgrade: websocket\r\n" +
            "Connection: Upgrade\r\n" +
            "Sec-WebSocket-Accept: ${generateWebSocketAccept(key)}\r\n\r\n"
        try {
            socket.getOutputStream().write(response.toByteArray(StandardCharsets.UTF_8))
            socket.getOutputStream().flush()
            return true
        } catch (e: Exception) {
            Log.e(TAG, "WebSocket upgrade failed", e)
            return false
        }
    }

    private fun generateWebSocketAccept(key: String): String {
        val guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        val sha1 = java.security.MessageDigest.getInstance("SHA-1")
        val hash = sha1.digest((key + guid).toByteArray(StandardCharsets.UTF_8))
        return android.util.Base64.encodeToString(hash, android.util.Base64.NO_WRAP)
    }

    private fun sendWebSocketBinary(output: java.io.OutputStream, data: ByteArray) {
        sendWebSocketFrame(output, 0x2, data)
    }

    private fun sendWebSocketText(output: java.io.OutputStream, text: String) {
        sendWebSocketFrame(output, 0x1, text.toByteArray(StandardCharsets.UTF_8))
    }

    private fun sendWebSocketFrame(output: java.io.OutputStream, opcode: Int, data: ByteArray) {
        val fin = 0x80
        val masked = 0x00 // Server doesn't mask
        val firstByte = fin or opcode

        val length = data.size
        val header = ByteArrayOutputStream()
        header.write(firstByte)

        if (length < 126) {
            header.write(masked or length)
        } else if (length < 65536) {
            header.write(masked or 126)
            header.write(length shr 8)
            header.write(length and 0xFF)
        } else {
            header.write(masked or 127)
            for (i in 7 downTo 0) {
                header.write(length shr (i * 8) and 0xFF)
            }
        }

        output.write(header.toByteArray())
        if (data.isNotEmpty()) {
            output.write(data)
        }
        output.flush()
    }

    private fun listFilesSaf(path: String): List<FileEntryDto> {
        // Use SAF (Storage Access Framework) for file access
        // For now, use standard File API with allowed roots check
        return try {
            val file = File(path)
            if (!file.exists() || !file.isDirectory) return emptyList()

            file.listFiles()?.filter { isPathAllowed(it.absolutePath) }?.map { f ->
                FileEntryDto(
                    name = f.name,
                    path = f.absolutePath,
                    isDir = f.isDirectory,
                    size = if (f.isFile) f.length() else null,
                )
            } ?: emptyList()
        } catch (e: Exception) {
            Log.w(TAG, "List files error: $path", e)
            emptyList()
        }
    }

    private fun isPathAllowed(path: String): Boolean {
        // Check if path is within user-selected SAF roots
        // For now, allow common user-accessible paths
        val allowedPrefixes = listOf(
            "/storage/emulated/0/Download",
            "/storage/emulated/0/Documents",
            "/storage/emulated/0/Pictures",
            "/storage/emulated/0/Movies",
            "/storage/emulated/0/Music",
            context.filesDir.absolutePath,
            context.cacheDir.absolutePath,
        )
        return allowedPrefixes.any { path.startsWith(it) }
    }

    private fun startScreenCapture() {
        if (screenCapture == null || !screenCapture.isCapturingValue) {
            val projectionManager = context.getSystemService(android.media.projection.MediaProjectionManager::class.java)
            // Note: In a real implementation, we'd need to request media projection permission
            // For now, we'll use the existing screen capture if available
        }
    }

    private fun stopScreenCapture() {
        // Do not kill capture globally here; Settings owns share lifecycle.
    }

    fun stop() {
        stopServer()
    }
}
package com.devaraj.maya.data.remote

import java.io.IOException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlinx.serialization.json.Json
import okhttp3.ResponseBody
import retrofit2.HttpException

/** Stable, UI-mappable reasons (plan §13.5). */
enum class MayaErrorReason {
    WRONG_PIN,
    EXPIRED,
    RATE_LIMITED,
    INVALID_TOKEN,
    TOKEN_EXPIRED,
    DEVICE_REVOKED,
    BAD_REQUEST,
    UNSUPPORTED_ACTION,
    PAYLOAD_TOO_LARGE,
    NOT_FOUND,
    ENGINE_UNAVAILABLE,
    ENGINE_TIMEOUT,
    STT_UNAVAILABLE,
    TTS_UNAVAILABLE,
    PERMISSION_DENIED,
    ACTION_BLOCKED,
    SERVER_ERROR,
    TIMEOUT,
    NO_CONNECTION,
    NON_LOCAL_HOST,
    UNKNOWN,
    ;

    companion object {
        fun fromCode(code: Int?): MayaErrorReason = when (code) {
            1001 -> INVALID_TOKEN
            1003 -> WRONG_PIN
            1004 -> EXPIRED
            1005 -> RATE_LIMITED
            1006 -> TOKEN_EXPIRED
            1007 -> DEVICE_REVOKED
            2001 -> BAD_REQUEST
            2002 -> UNSUPPORTED_ACTION
            2003 -> PAYLOAD_TOO_LARGE
            2004 -> NOT_FOUND
            3001 -> ENGINE_UNAVAILABLE
            3002 -> ENGINE_TIMEOUT
            3003 -> STT_UNAVAILABLE
            3004 -> TTS_UNAVAILABLE
            4002 -> PERMISSION_DENIED
            4003 -> ACTION_BLOCKED
            5000 -> SERVER_ERROR
            else -> UNKNOWN
        }
    }
}

/** Transport-agnostic failure; `code` is null for network/timeout errors. */
class MayaApiException(
    val code: Int?,
    val reason: MayaErrorReason,
    message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

object ErrorMapper {

    private val json = Json { ignoreUnknownKeys = true }

    fun parseError(body: String?): ApiError? {
        if (body.isNullOrBlank()) return null
        return try {
            json.decodeFromString(ApiErrorEnvelope.serializer(), body).error
        } catch (_: Exception) {
            null
        }
    }

    fun parseError(body: ResponseBody?): ApiError? = try {
        body?.string()?.let { text -> parseError(text) }
    } catch (_: IOException) {
        null
    }

    fun toApiException(error: Throwable): MayaApiException {
        if (error is MayaApiException) return error
        return when (error) {
            is HttpException -> {
                val parsed = parseError(error.response()?.errorBody())
                MayaApiException(
                    code = parsed?.code,
                    reason = MayaErrorReason.fromCode(parsed?.code),
                    message = parsed?.message ?: "Server error ${error.code()}",
                    cause = error,
                )
            }
            is SocketTimeoutException -> MayaApiException(
                code = null,
                reason = MayaErrorReason.TIMEOUT,
                message = "No response from laptop",
                cause = error,
            )
            is UnknownHostException -> MayaApiException(
                code = null,
                reason = MayaErrorReason.NO_CONNECTION,
                message = "Laptop not found on this network",
                cause = error,
            )
            is IOException -> {
                val blocked = error.message == PrivateNetworkInterceptor.BLOCKED_MESSAGE
                MayaApiException(
                    code = null,
                    reason = if (blocked) MayaErrorReason.NON_LOCAL_HOST else MayaErrorReason.NO_CONNECTION,
                    message = if (blocked) "Only local network allowed" else "No connection to laptop",
                    cause = error,
                )
            }
            else -> MayaApiException(
                code = null,
                reason = MayaErrorReason.UNKNOWN,
                message = "Something went wrong",
                cause = error,
            )
        }
    }
}

/** Runs an API call and converts every failure into [MayaApiException]. */
suspend fun <T> apiCall(block: suspend () -> T): Result<T> = try {
    Result.success(block())
} catch (error: Exception) {
    Result.failure(ErrorMapper.toApiException(error))
}

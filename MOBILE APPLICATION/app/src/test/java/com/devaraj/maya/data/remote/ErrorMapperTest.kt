package com.devaraj.maya.data.remote

import java.io.IOException
import java.net.SocketTimeoutException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class ErrorMapperTest {

    @Test
    fun `contract codes map to stable reasons`() {
        assertEquals(MayaErrorReason.INVALID_TOKEN, MayaErrorReason.fromCode(1001))
        assertEquals(MayaErrorReason.WRONG_PIN, MayaErrorReason.fromCode(1003))
        assertEquals(MayaErrorReason.EXPIRED, MayaErrorReason.fromCode(1004))
        assertEquals(MayaErrorReason.RATE_LIMITED, MayaErrorReason.fromCode(1005))
        assertEquals(MayaErrorReason.TOKEN_EXPIRED, MayaErrorReason.fromCode(1006))
        assertEquals(MayaErrorReason.DEVICE_REVOKED, MayaErrorReason.fromCode(1007))
        assertEquals(MayaErrorReason.BAD_REQUEST, MayaErrorReason.fromCode(2001))
        assertEquals(MayaErrorReason.PAYLOAD_TOO_LARGE, MayaErrorReason.fromCode(2003))
        assertEquals(MayaErrorReason.ENGINE_UNAVAILABLE, MayaErrorReason.fromCode(3001))
        assertEquals(MayaErrorReason.ENGINE_TIMEOUT, MayaErrorReason.fromCode(3002))
        assertEquals(MayaErrorReason.PERMISSION_DENIED, MayaErrorReason.fromCode(4002))
        assertEquals(MayaErrorReason.ACTION_BLOCKED, MayaErrorReason.fromCode(4003))
        assertEquals(MayaErrorReason.SERVER_ERROR, MayaErrorReason.fromCode(5000))
        assertEquals(MayaErrorReason.UNKNOWN, MayaErrorReason.fromCode(9999))
        assertEquals(MayaErrorReason.UNKNOWN, MayaErrorReason.fromCode(null))
    }

    @Test
    fun `error envelope is parsed`() {
        val error = ErrorMapper.parseError(
            """{"error":{"code":1003,"message":"Invalid PIN","details":null}}""",
        )
        assertEquals(1003, error?.code)
        assertEquals("Invalid PIN", error?.message)
    }

    @Test
    fun `malformed error body is ignored`() {
        assertNull(ErrorMapper.parseError("not json"))
        assertNull(ErrorMapper.parseError(null as String?))
        assertNull(ErrorMapper.parseError(""))
    }

    @Test
    fun `HTTP errors carry the contract code`() {
        val body = """{"error":{"code":3001,"message":"Engine unavailable","details":null}}"""
            .toResponseBody("application/json".toMediaType())
        val exception = HttpException(Response.error<Any>(503, body))

        val mapped = ErrorMapper.toApiException(exception)

        assertEquals(3001, mapped.code)
        assertEquals(MayaErrorReason.ENGINE_UNAVAILABLE, mapped.reason)
        assertEquals("Engine unavailable", mapped.message)
    }

    @Test
    fun `timeouts map to a retryable reason`() {
        val mapped = ErrorMapper.toApiException(SocketTimeoutException("timeout"))
        assertEquals(MayaErrorReason.TIMEOUT, mapped.reason)
        assertNull(mapped.code)
    }

    @Test
    fun `blocked host is reported separately`() {
        val mapped = ErrorMapper.toApiException(IOException(PrivateNetworkInterceptor.BLOCKED_MESSAGE))
        assertEquals(MayaErrorReason.NON_LOCAL_HOST, mapped.reason)
    }

    @Test
    fun `other IO failures mean no connection`() {
        val mapped = ErrorMapper.toApiException(IOException("connection refused"))
        assertEquals(MayaErrorReason.NO_CONNECTION, mapped.reason)
    }

    @Test
    fun `already mapped exceptions pass through`() {
        val original = MayaApiException(1007, MayaErrorReason.DEVICE_REVOKED, "Device revoked")
        assertSame(original, ErrorMapper.toApiException(original))
    }
}

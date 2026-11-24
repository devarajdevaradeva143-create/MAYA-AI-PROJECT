package com.devaraj.maya.data.remote

import java.io.IOException
import java.net.InetAddress
import java.net.UnknownHostException
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class PrivateNetworkInterceptorTest {

    private fun address(host: String): InetAddress = InetAddress.getByName(host)

    @Test
    fun `home LAN ranges are private`() {
        listOf("192.168.1.5", "10.0.0.2", "172.16.0.1", "172.31.255.254", "127.0.0.1", "169.254.1.1")
            .forEach { assertTrue("$it should be private", PrivateNetworkInterceptor.isPrivateAddress(address(it))) }
    }

    @Test
    fun `public IPv4 ranges are rejected`() {
        listOf("8.8.8.8", "1.1.1.1", "172.32.0.1", "100.128.0.1", "203.0.113.10")
            .forEach { assertFalse("$it should be public", PrivateNetworkInterceptor.isPrivateAddress(address(it))) }
    }

    @Test
    fun `tethering CGNAT range is allowed`() {
        assertTrue(PrivateNetworkInterceptor.isPrivateAddress(address("100.64.0.1")))
        assertTrue(PrivateNetworkInterceptor.isPrivateAddress(address("100.127.255.254")))
    }

    @Test
    fun `IPv6 loopback and ULA allowed, global rejected`() {
        assertTrue(PrivateNetworkInterceptor.isPrivateAddress(address("::1")))
        assertTrue(PrivateNetworkInterceptor.isPrivateAddress(address("fc00::1")))
        assertFalse(PrivateNetworkInterceptor.isPrivateAddress(address("2001:4860:4860::8888")))
    }

    @Test
    fun `host is private only when every resolved address is private`() {
        assertTrue(PrivateNetworkInterceptor.isPrivateHost("192.168.1.5"))
        assertTrue(PrivateNetworkInterceptor.isPrivateHost("localhost"))
        assertFalse(PrivateNetworkInterceptor.isPrivateHost("8.8.8.8"))
        assertFalse(
            PrivateNetworkInterceptor.isPrivateHost("evil.example") {
                arrayOf(address("192.168.1.5"), address("8.8.8.8"))
            },
        )
        assertFalse(
            PrivateNetworkInterceptor.isPrivateHost("missing.example") {
                throw UnknownHostException("missing.example")
            },
        )
        assertFalse(
            PrivateNetworkInterceptor.isPrivateHost("empty.example") { emptyArray() },
        )
    }

    @Test
    fun `interceptor blocks a public host before connecting`() {
        val client = OkHttpClient.Builder()
            .addInterceptor(PrivateNetworkInterceptor())
            .connectTimeout(1, TimeUnit.SECONDS)
            .build()
        val request = Request.Builder().url("http://8.8.8.8/api/v1/health").build()

        val error = assertThrows(IOException::class.java) {
            client.newCall(request).execute().close()
        }
        assertEquals(PrivateNetworkInterceptor.BLOCKED_MESSAGE, error.message)
    }

    @Test
    fun `interceptor allows loopback`() {
        val client = OkHttpClient.Builder()
            .addInterceptor(PrivateNetworkInterceptor())
            .build()
        val request = Request.Builder().url("http://127.0.0.1:1/api/v1/health").build()

        // Port 1 refuses the connection, but the guard itself must not block.
        val error = assertThrows(IOException::class.java) {
            client.newCall(request).execute().close()
        }
        assertFalse(error.message == PrivateNetworkInterceptor.BLOCKED_MESSAGE)
    }
}

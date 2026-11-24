package com.devaraj.maya.data.remote

import java.io.IOException
import java.net.InetAddress
import java.net.UnknownHostException
import okhttp3.Interceptor
import okhttp3.Response

/**
 * LAN-only guard (plan §13.1). Every request host must resolve to private
 * addresses only; anything public is rejected before a socket opens.
 *
 * Home LAN ranges allowed: 10/8, 172.16/12, 192.168/16, 169.254/16,
 * 127.0.0.1 (USB via adb reverse) and IPv6 ULA / loopback.
 */
class PrivateNetworkInterceptor(
    private val resolver: (String) -> Array<InetAddress> = { InetAddress.getAllByName(it) },
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val host = chain.request().url.host
        if (!isPrivateHost(host, resolver)) {
            throw IOException(BLOCKED_MESSAGE)
        }
        return chain.proceed(chain.request())
    }

    companion object {
        const val BLOCKED_MESSAGE = "blocked: non-local host"

        fun isPrivateHost(
            host: String,
            resolver: (String) -> Array<InetAddress> = { InetAddress.getAllByName(it) },
        ): Boolean {
            if (host.equals("localhost", ignoreCase = true)) return true
            val addresses = try {
                resolver(host)
            } catch (_: UnknownHostException) {
                return false
            }
            if (addresses.isEmpty()) return false
            // Strict: every answer must be private (defeats DNS tricks).
            return addresses.all { isPrivateAddress(it) }
        }

        fun isPrivateAddress(address: InetAddress): Boolean {
            if (address.isAnyLocalAddress) return false
            if (address.isLoopbackAddress || address.isLinkLocalAddress || address.isSiteLocalAddress) {
                return true
            }
            val bytes = address.address
            // IPv4 CGNAT 100.64.0.0/10 (some home routers / tethering).
            if (bytes.size == 4) {
                val first = bytes[0].toInt() and 0xFF
                val second = bytes[1].toInt() and 0xFF
                return first == 100 && second in 64..127
            }
            // IPv6 unique local addresses fc00::/7.
            return bytes.size == 16 && (bytes[0].toInt() and 0xFE) == 0xFC
        }
    }
}

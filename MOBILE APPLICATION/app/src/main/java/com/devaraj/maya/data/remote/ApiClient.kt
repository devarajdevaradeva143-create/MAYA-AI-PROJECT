package com.devaraj.maya.data.remote

import com.devaraj.maya.BuildConfig
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * Retrofit/OkHttp factory (plan §13.1). One shared client for all devices;
 * the active token is supplied per request by [tokenProvider] so pairing and
 * device switches stay cheap.
 */
class ApiClient(
    private val tokenProvider: () -> String? = { null },
    debug: Boolean = BuildConfig.DEBUG,
) {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        encodeDefaults = true
    }

    /** Auth header (plan §13.1, interceptor 2). */
    private val authInterceptor = okhttp3.Interceptor { chain ->
        val token = tokenProvider()
        val request = if (token.isNullOrBlank()) {
            chain.request()
        } else {
            chain.request().newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        }
        chain.proceed(request)
    }

    private val baseClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .pingInterval(10, TimeUnit.SECONDS)
        .addInterceptor(PrivateNetworkInterceptor())
        .addInterceptor(authInterceptor)
        .apply {
            if (debug) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        level = HttpLoggingInterceptor.Level.BASIC
                        redactHeader("Authorization")
                    },
                )
            }
        }
        .build()

    /** Startup health check uses a 2 s budget (plan §14.2). */
    private val quickClient: OkHttpClient = baseClient.newBuilder()
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(2, TimeUnit.SECONDS)
        .callTimeout(2, TimeUnit.SECONDS)
        .build()

    private val apiCache = ConcurrentHashMap<String, MayaApi>()

    fun api(host: String, port: Int, quick: Boolean = false): MayaApi {
        val key = "$host:$port:$quick"
        return apiCache.getOrPut(key) {
            Retrofit.Builder()
                .baseUrl(baseUrl(host, port))
                .client(if (quick) quickClient else baseClient)
                .addConverterFactory(json.asConverterFactory(JSON_MEDIA_TYPE))
                .build()
                .create(MayaApi::class.java)
        }
    }

    /**
     * WebSocket handshake goes through the same interceptors, so the LAN guard
     * and the Bearer token are enforced for chat/event sockets too.
     */
    fun newWebSocket(url: String, listener: WebSocketListener): WebSocket =
        baseClient.newWebSocket(Request.Builder().url(url).build(), listener)

    companion object {
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()

        const val DEFAULT_PORT = 8420

        fun baseUrl(host: String, port: Int = DEFAULT_PORT): String = "http://$host:$port/api/v1/"

        fun wsUrl(host: String, port: Int = DEFAULT_PORT, path: String): String =
            "ws://$host:$port/api/v1/$path"
    }
}

package com.devaraj.maya.data.cloud

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Direct Gemini API client (cloud fallback).
 *
 * Privacy:
 * - Sends ONLY the prompt + history (user-initiated).
 * - Never sends local files, memory, or personal details automatically.
 * - Requires explicit API key in Settings -> Cloud AI.
 *
 * Reliability:
 * - 503/429/5xx are transient on the free tier, so the primary model is
 *   retried once and then the request falls through a short model chain.
 *   The user only sees an error when every model is unavailable.
 */
class GeminiRepository(
    private val apiKeyProvider: () -> String,
) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    data class GeminiMessage(val role: String, val content: String)

    /** Reply text plus the model that actually answered. */
    data class GeminiReply(val text: String, val model: String)

    suspend fun chat(
        messages: List<GeminiMessage>,
        systemPrompt: String? = null,
        maxTokens: Int = 1024,
        temperature: Double = 0.7,
    ): GeminiReply = withContext(Dispatchers.IO) {
        val key = apiKeyProvider()
        require(key.isNotBlank()) { "No Gemini API key configured" }

        var lastError: Exception? = null
        MODELS.forEachIndexed { index, model ->
            // The primary model gets one quick retry; the fallbacks get one shot.
            val attempts = if (index == 0) 2 else 1
            repeat(attempts) { attempt ->
                try {
                    val text = callModel(
                        model = model,
                        key = key,
                        messages = messages,
                        systemPrompt = systemPrompt,
                        maxTokens = maxTokens,
                        temperature = temperature,
                    )
                    return@withContext GeminiReply(text, model)
                } catch (failure: HttpFailure) {
                    lastError = failure
                    // Bad key / bad request will fail on every model — stop.
                    if (!failure.isRetryable()) throw failure
                } catch (io: IOException) {
                    lastError = io
                }
                if (attempt < attempts - 1) delay(RETRY_DELAY_MS)
            }
        }
        throw lastError ?: IOException("Gemini unavailable")
    }

    private fun callModel(
        model: String,
        key: String,
        messages: List<GeminiMessage>,
        systemPrompt: String?,
        maxTokens: Int,
        temperature: Double,
    ): String {
        val contents = messages.map { msg ->
            val role = when (msg.role) {
                "user" -> "user"
                "assistant" -> "model"
                else -> "user"
            }
            buildJsonObject {
                put("role", role)
                put("parts", buildJsonArray {
                    add(buildJsonObject { put("text", msg.content) })
                })
            }
        }

        val body = buildJsonObject {
            put("contents", buildJsonArray {
                contents.forEach { add(it) }
            })
            if (!systemPrompt.isNullOrBlank()) {
                put("systemInstruction", buildJsonObject {
                    put("parts", buildJsonArray {
                        add(buildJsonObject { put("text", systemPrompt) })
                    })
                })
            }
            put("generationConfig", buildJsonObject {
                put("maxOutputTokens", maxTokens)
                put("temperature", temperature)
            })
        }

        val request = Request.Builder()
            .url("$ENDPOINT/models/$model:generateContent")
            .header("x-goog-api-key", key)
            .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).execute().use { response ->
            val responseBody = response.body?.string()
                ?: throw IOException("Empty response from Gemini")

            if (!response.isSuccessful) {
                throw HttpFailure(response.code, responseBody)
            }

            return parseReply(responseBody)
        }
    }

    private fun parseReply(json: String): String {
        val root = Json.parseToJsonElement(json).jsonObject
        val candidates = root["candidates"]?.jsonArray ?: return ""
        if (candidates.isEmpty()) return ""

        val content = candidates[0].jsonObject["content"]?.jsonObject ?: return ""
        val parts = content["parts"]?.jsonArray ?: return ""

        val text = parts.mapNotNull { part ->
            part.jsonObject["text"]?.jsonPrimitive?.contentOrNull
        }.joinToString("")

        return text.ifBlank { "(empty reply)" }
    }

    /** HTTP error we may be able to fix by trying another model. */
    private class HttpFailure(val code: Int, val body: String) : Exception("HTTP $code") {
        fun isRetryable(): Boolean =
            code == 429 || code == 500 || code == 502 || code == 503 || code == 504
    }

    companion object {
        private const val ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"

        /**
         * Tried in order. Free-tier models can be busy (503) independently,
         * so a short chain keeps the app usable without showing errors.
         */
        private val MODELS = listOf(
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
        )

        private const val RETRY_DELAY_MS = 800L
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}

package com.devaraj.maya.data.cloud

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Direct Gemini API client (cloud fallback).
 *
 * Privacy:
 * - Sends ONLY the prompt + history (user-initiated).
 * - Never sends local files, memory, or personal details automatically.
 * - Requires explicit API key in Settings -> Cloud AI.
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

    suspend fun chat(
        messages: List<GeminiMessage>,
        systemPrompt: String? = null,
        maxTokens: Int = 1024,
        temperature: Double = 0.7,
    ): String = withContext(Dispatchers.IO) {
        val key = apiKeyProvider()
        require(key.isNotBlank()) { "No Gemini API key configured" }

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
            .url("$ENDPOINT/models/$MODEL:generateContent?key=$key")
            .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).execute().use { response ->
            val responseBody = response.body?.string()
                ?: throw RuntimeException("Empty response from Gemini")

            if (!response.isSuccessful) {
                throw RuntimeException(
                    "Gemini HTTP ${response.code}: ${responseBody.take(300)}"
                )
            }

            parseReply(responseBody)
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

    companion object {
        private const val ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
        private const val MODEL = "gemini-3.5-flash-lite"
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}
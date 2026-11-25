package com.devaraj.maya.data.cloud

import android.util.Base64
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
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
 * Gemini TTS client — used ONLY for cloud (Gemini) replies.
 *
 * Privacy:
 * - Sends only the reply text that Gemini itself produced, and only when the
 *   user has configured a Gemini API key (Settings -> Cloud AI).
 * - Local (laptop / on-device) replies never reach this class.
 *
 * The API returns a complete WAV file (24 kHz, mono, 16-bit PCM) for unary
 * requests, so callers can play the bytes directly.
 */
class GeminiTtsRepository(
    private val apiKeyProvider: () -> String,
) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    /**
     * Synthesise [text] to WAV bytes.
     *
     * @param style short delivery hint, e.g. "cheerful, casual, friendly".
     * @param voice prebuilt Gemini voice name. `Leda` is the youthful option.
     */
    suspend fun synthesize(
        text: String,
        style: String = DEFAULT_STYLE,
        voice: String = DEFAULT_VOICE,
    ): ByteArray = withContext(Dispatchers.IO) {
        val clean = text.trim()
        require(clean.isNotBlank()) { "Empty TTS text" }
        val key = apiKeyProvider()
        require(key.isNotBlank()) { "No Gemini API key configured" }

        val body = buildJsonObject {
            put("model", MODEL)
            put("input", buildJsonArray {
                add(buildJsonObject {
                    put("type", "user_input")
                    put("content", buildJsonArray {
                        add(buildJsonObject {
                            put("type", "text")
                            put("text", clean.take(MAX_CHARS))
                            put("annotations", buildJsonArray {
                                add(buildJsonObject {
                                    put("type", "speech_metadata")
                                    put("style", style)
                                })
                            })
                        })
                    })
                })
            })
            put("response_format", buildJsonObject {
                put("type", "audio")
                put("mime_type", "audio/wav")
            })
            put("generation_config", buildJsonObject {
                put("speech_config", buildJsonArray {
                    add(buildJsonObject { put("voice", voice) })
                })
            })
        }

        val request = Request.Builder()
            .url(ENDPOINT)
            .header("x-goog-api-key", key)
            .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).execute().use { response ->
            val raw = response.body?.string()
                ?: throw RuntimeException("Empty response from Gemini TTS")
            if (!response.isSuccessful) {
                throw RuntimeException("Gemini TTS HTTP ${response.code}: ${raw.take(300)}")
            }
            parseAudio(raw)
        }
    }

    private fun parseAudio(json: String): ByteArray {
        val root = Json.parseToJsonElement(json).jsonObject

        // Interactions API: steps[].content[].data (base64)
        root["steps"]?.jsonArray?.let { steps ->
            for (step in steps.reversed()) {
                if (step.jsonObject["type"]?.jsonPrimitive?.contentOrNull != "model_output") continue
                val content = step.jsonObject["content"]?.jsonArray ?: continue
                for (item in content.reversed()) {
                    val obj = item.jsonObject
                    if (obj["type"]?.jsonPrimitive?.contentOrNull != "audio") continue
                    val data = obj["data"]?.jsonPrimitive?.contentOrNull ?: continue
                    return Base64.decode(data, Base64.DEFAULT)
                }
            }
        }

        // generateContent fallback: candidates[].content.parts[].inlineData.data
        root["candidates"]?.jsonArray?.forEach { candidate ->
            val parts = candidate.jsonObject["content"]?.jsonObject?.get("parts")?.jsonArray ?: return@forEach
            for (part in parts) {
                val inline = part.jsonObject["inlineData"]?.jsonObject
                    ?: part.jsonObject["inline_data"]?.jsonObject
                    ?: continue
                val data = inline["data"]?.jsonPrimitive?.contentOrNull ?: continue
                return Base64.decode(data, Base64.DEFAULT)
            }
        }

        throw RuntimeException("Gemini TTS returned no audio")
    }

    companion object {
        const val DEFAULT_VOICE = "Leda" // youthful
        const val DEFAULT_STYLE = "cheerful, casual, friendly, young college student"

        private const val MODEL = "gemini-3.8-flash-lite-tts"
        private const val ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
        private const val MAX_CHARS = 2000
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}

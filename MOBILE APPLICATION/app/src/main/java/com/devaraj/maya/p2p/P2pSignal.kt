package com.devaraj.maya.p2p

import org.json.JSONException
import org.json.JSONObject
import java.util.Base64

internal const val SIGNAL_TTL_SECONDS = 120L

/**
 * Manual offer/answer signaling codec. Payloads are compact base64url JSON and match the
 * Python core (`custom/tools/p2p.py`) v=2 format exactly. No private key is ever included.
 */
object P2pSignal {
    private const val VERSION = 2
    private const val OFFER_KIND = "maya-p2p-offer"
    private const val ANSWER_KIND = "maya-p2p-answer"
    private const val OFFER_TYPE = "offer"
    private const val ANSWER_TYPE = "answer"

    fun encodeOffer(sdp: String, fp: String, sid: String, exp: Long): String =
        encode(OFFER_KIND, OFFER_TYPE, sdp, fp, sid, exp)

    fun encodeAnswer(sdp: String, fp: String, sid: String, exp: Long): String =
        encode(ANSWER_KIND, ANSWER_TYPE, sdp, fp, sid, exp)

    fun decodeOffer(text: String): P2pOffer {
        val fields = decode(text, OFFER_KIND, OFFER_TYPE)
        return P2pOffer(fields.sdp, fields.fp, fields.sid, fields.exp)
    }

    fun decodeAnswer(text: String): P2pAnswer {
        val fields = decode(text, ANSWER_KIND, ANSWER_TYPE)
        return P2pAnswer(fields.sdp, fields.fp, fields.sid, fields.exp)
    }

    private fun encode(kind: String, type: String, sdp: String, fp: String, sid: String, exp: Long): String {
        val json = JSONObject()
            .put("v", VERSION)
            .put("kind", kind)
            .put("sdp", sdp)
            .put("type", type)
            .put("fp", fp)
            .put("sid", sid)
            .put("exp", exp)
            .toString()
        val raw = json.toByteArray(Charsets.UTF_8)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(raw)
    }

    private data class Fields(val sdp: String, val fp: String, val sid: String, val exp: Long)

    private fun decode(text: String, kind: String, type: String): Fields {
        val raw = try {
            Base64.getUrlDecoder().decode(text)
        } catch (e: IllegalArgumentException) {
            throw IllegalArgumentException("Not valid base64url signaling payload", e)
        }
        val obj = try {
            JSONObject(String(raw, Charsets.UTF_8))
        } catch (e: JSONException) {
            throw IllegalArgumentException("Signaling payload is not valid JSON", e)
        }

        val version = obj.opt("v")
        if (version !is Number || version.toInt() != VERSION) {
            throw IllegalArgumentException("Unsupported signaling version")
        }
        if (obj.optString("kind") != kind || obj.optString("type") != type) {
            throw IllegalArgumentException("Not a Maya P2P $type signal")
        }

        val sdp = requiredString(obj, "sdp")
        val fp = requiredString(obj, "fp")
        val sid = requiredString(obj, "sid")
        if (sdp.isEmpty() || sid.isEmpty()) {
            throw IllegalArgumentException("Signal fields are empty")
        }

        val expValue = obj.opt("exp")
        val exp = when (expValue) {
            is Number -> expValue.toLong()
            is String -> expValue.toLongOrNull()
                ?: throw IllegalArgumentException("Signal expiry is invalid")
            else -> throw IllegalArgumentException("Signal expiry is missing")
        }
        if (exp <= System.currentTimeMillis() / 1000L) {
            throw IllegalArgumentException("Signal expired")
        }
        return Fields(sdp, fp, sid, exp)
    }

    private fun requiredString(obj: JSONObject, key: String): String =
        obj.opt(key) as? String ?: throw IllegalArgumentException("Signal field '$key' is invalid")
}

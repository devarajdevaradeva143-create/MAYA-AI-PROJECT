package com.devaraj.maya.p2p

/** Optional TURN relay. Credentials are used for ICE only and are never sent in signaling payloads. */
data class P2pTurn(val host: String, val username: String, val credential: String)

data class P2pOffer(val sdp: String, val fp: String, val sid: String, val exp: Long)

data class P2pAnswer(val sdp: String, val fp: String, val sid: String, val exp: Long)

data class P2pMessage(val channel: String, val payload: String)

enum class P2pState { NEW, CONNECTING, CONNECTED, FAILED, CLOSED }

package com.devaraj.maya.domain.model

data class Device(
    val id: String,
    val name: String,
    val host: String,
    val port: Int,
    val lastSeen: Long,
    val autoConnect: Boolean = false,
)

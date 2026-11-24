package com.devaraj.maya.domain.model

data class Conversation(
    val id: String,
    val title: String,
    val persona: String,
    val createdAt: Long,
    val updatedAt: Long,
)

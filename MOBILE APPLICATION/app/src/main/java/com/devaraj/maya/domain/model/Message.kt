package com.devaraj.maya.domain.model

enum class MessageRole { USER, MAYA, ASSISTANT, SYSTEM }

enum class MessageStatus { SENDING, STREAMING, SENT, FAILED, STOPPED }

enum class AiSource { LAPTOP, PHONE, CLOUD, NONE }

data class Message(
    val id: String,
    val conversationId: String,
    val role: MessageRole,
    val content: String,
    val status: MessageStatus,
    val source: AiSource,
    val model: String? = null,
    val error: String? = null,
    val createdAt: Long,
)

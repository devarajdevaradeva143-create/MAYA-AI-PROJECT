package com.devaraj.maya.data.local

import com.devaraj.maya.data.local.entity.ConversationEntity
import com.devaraj.maya.data.local.entity.DeviceEntity
import com.devaraj.maya.data.local.entity.MessageEntity
import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Conversation
import com.devaraj.maya.domain.model.Device
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus

fun ConversationEntity.toDomain(): Conversation = Conversation(
    id = id,
    title = title,
    persona = persona,
    createdAt = createdAt,
    updatedAt = updatedAt,
)

fun MessageEntity.toDomain(): Message = Message(
    id = id,
    conversationId = conversationId,
    role = MessageRole.values().firstOrNull { it.name == role } ?: MessageRole.SYSTEM,
    content = content,
    status = MessageStatus.values().firstOrNull { it.name == status } ?: MessageStatus.SENT,
    source = AiSource.values().firstOrNull { it.name == source } ?: AiSource.NONE,
    model = model,
    error = error,
    createdAt = createdAt,
)

fun Message.toEntity(): MessageEntity = MessageEntity(
    id = id,
    conversationId = conversationId,
    role = role.name,
    content = content,
    status = status.name,
    source = source.name,
    model = model,
    error = error,
    createdAt = createdAt,
)

fun DeviceEntity.toDomain(): Device = Device(
    id = id,
    name = name,
    host = host,
    port = port,
    lastSeen = lastSeen,
    autoConnect = autoConnect,
)

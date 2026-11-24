package com.devaraj.maya.data.repo

import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.local.entity.ConversationEntity
import com.devaraj.maya.data.local.toDomain
import com.devaraj.maya.data.local.toEntity
import com.devaraj.maya.domain.ChatLimits
import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Conversation
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus
import java.util.UUID
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Local chat persistence (Phase 2). Network/streaming arrives in Phase 4;
 * this repository only stores and reads history on the phone.
 */
class ChatRepository(
    private val db: MayaDatabase,
    private val now: () -> Long = System::currentTimeMillis,
) {

    fun observeConversations(): Flow<List<Conversation>> =
        db.conversationDao().observeAll().map { list -> list.map { it.toDomain() } }

    fun observeConversation(id: String): Flow<Conversation?> =
        db.conversationDao().observeById(id).map { it?.toDomain() }

    fun observeMessages(conversationId: String): Flow<List<Message>> =
        db.messageDao().observeByConversation(conversationId)
            .map { list -> list.map { it.toDomain() } }

    suspend fun latestConversation(): Conversation? =
        db.conversationDao().mostRecent()?.toDomain()

    suspend fun ensureConversation(
        id: String = newConversationId(),
        persona: String = "maya",
        title: String = NEW_CHAT_TITLE,
    ): Conversation {
        db.conversationDao().findById(id)?.let { return it.toDomain() }
        val time = now()
        val entity = ConversationEntity(
            id = id,
            title = title,
            persona = persona,
            createdAt = time,
            updatedAt = time,
        )
        db.conversationDao().insert(entity)
        return entity.toDomain()
    }

    suspend fun addUserMessage(conversationId: String, text: String): Message {
        val time = now()
        val firstMessage = db.messageDao().lastN(conversationId, 1).isEmpty()
        val message = Message(
            id = newMessageId(),
            conversationId = conversationId,
            role = MessageRole.USER,
            content = text,
            status = MessageStatus.SENT,
            source = AiSource.NONE,
            createdAt = time,
        )
        db.messageDao().insert(message.toEntity())
        db.conversationDao().touch(conversationId, time)
        if (firstMessage) {
            db.conversationDao().updateTitle(conversationId, text.take(TITLE_MAX_CHARS), time)
        }
        return message
    }

    suspend fun addMayaMessage(
        conversationId: String,
        text: String,
        source: AiSource = AiSource.LAPTOP,
        model: String? = null,
    ): Message {
        val time = now()
        val message = Message(
            id = newMessageId(),
            conversationId = conversationId,
            role = MessageRole.MAYA,
            content = text,
            status = MessageStatus.SENT,
            source = source,
            model = model,
            createdAt = time,
        )
        db.messageDao().insert(message.toEntity())
        db.conversationDao().touch(conversationId, time)
        return message
    }

    suspend fun updateMessage(
        messageId: String,
        content: String,
        status: MessageStatus,
        error: String? = null,
    ) {
        db.messageDao().update(messageId, content, status.name, error)
    }

    /** Empty Maya bubble that fills while tokens stream (plan §15). */
    suspend fun startStreamingReply(
        conversationId: String,
        source: AiSource = AiSource.LAPTOP,
        model: String? = null,
    ): Message {
        val time = now()
        val message = Message(
            id = newMessageId(),
            conversationId = conversationId,
            role = MessageRole.MAYA,
            content = "",
            status = MessageStatus.STREAMING,
            source = source,
            model = model,
            createdAt = time,
        )
        db.messageDao().insert(message.toEntity())
        db.conversationDao().touch(conversationId, time)
        return message
    }

    suspend fun deleteMessage(messageId: String) {
        db.messageDao().delete(messageId)
    }

    /**
     * Repairs a reply left in STREAMING when the process died mid-generation.
     * Called only when a conversation is opened, so no live generation exists.
     */
    suspend fun markStreamingAsStopped(conversationId: String) {
        db.messageDao().updateStatus(
            conversationId = conversationId,
            from = MessageStatus.STREAMING.name,
            to = MessageStatus.STOPPED.name,
        )
    }

    /** Last 24 messages / 12 000 chars, oldest first (plan §15). */
    suspend fun historyForRequest(conversationId: String): List<Message> {
        val recent = db.messageDao().lastN(conversationId, ChatLimits.MAX_MESSAGES)
        return ChatLimits.trimHistory(recent.asReversed().map { it.toDomain() })
    }

    suspend fun deleteConversation(id: String) {
        db.conversationDao().delete(id)
    }

    companion object {
        const val NEW_CHAT_TITLE = "New chat"
        const val TITLE_MAX_CHARS = 40

        fun newConversationId(): String = "c_${UUID.randomUUID()}"
        fun newMessageId(): String = "m_${UUID.randomUUID()}"
    }
}

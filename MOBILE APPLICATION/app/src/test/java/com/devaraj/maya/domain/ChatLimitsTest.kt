package com.devaraj.maya.domain

import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatLimitsTest {

    private fun message(content: String, index: Int = 0): Message = Message(
        id = "m_$index",
        conversationId = "c_test",
        role = MessageRole.USER,
        content = content,
        status = MessageStatus.SENT,
        source = AiSource.NONE,
        createdAt = index.toLong(),
    )

    @Test
    fun `empty history stays empty`() {
        assertTrue(ChatLimits.trimHistory(emptyList()).isEmpty())
    }

    @Test
    fun `keeps only the last 24 messages`() {
        val messages = (1..30).map { message("m$it", it) }
        val trimmed = ChatLimits.trimHistory(messages)

        assertEquals(24, trimmed.size)
        assertEquals("m7", trimmed.first().content)
        assertEquals("m30", trimmed.last().content)
    }

    @Test
    fun `drops older messages over the character limit`() {
        val messages = listOf(
            message("a".repeat(8000), 1),
            message("b".repeat(8000), 2),
        )

        val trimmed = ChatLimits.trimHistory(messages)

        assertEquals(1, trimmed.size)
        assertEquals(2, trimmed.single().createdAt)
    }

    @Test
    fun `single oversized message is truncated but kept`() {
        val messages = listOf(message("x".repeat(15000), 1))

        val trimmed = ChatLimits.trimHistory(messages)

        assertEquals(1, trimmed.size)
        assertEquals(ChatLimits.MAX_CHARS, trimmed.single().content.length)
    }

    @Test
    fun `order is preserved after trimming`() {
        val messages = (1..5).map { message("m$it", it) }
        val trimmed = ChatLimits.trimHistory(messages)

        assertEquals(listOf(1L, 2L, 3L, 4L, 5L), trimmed.map { it.createdAt })
    }
}

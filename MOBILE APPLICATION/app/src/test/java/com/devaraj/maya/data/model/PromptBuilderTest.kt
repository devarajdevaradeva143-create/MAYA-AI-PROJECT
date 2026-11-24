package com.devaraj.maya.data.model

import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PromptBuilderTest {

    private fun message(
        id: String,
        role: MessageRole,
        content: String,
        status: MessageStatus = MessageStatus.SENT,
    ) = Message(
        id = id,
        conversationId = "c1",
        role = role,
        content = content,
        status = status,
        source = if (role == MessageRole.MAYA) AiSource.PHONE else AiSource.NONE,
        createdAt = 0L,
    )

    @Test
    fun `builds qwen chatml with non-thinking assistant prefix`() {
        val thinkOpen = "<" + "think>"
        val thinkClose = "</" + "think>"
        val prompt = PromptBuilder.build(
            persona = "maya",
            history = listOf(
                message("u1", MessageRole.USER, "Hi Maya"),
                message("a1", MessageRole.MAYA, "Hello da!"),
                message("u2", MessageRole.USER, "Epdi irukka?"),
            ),
        )

        assertTrue(prompt.startsWith("<|im_start|>system\n"))
        assertTrue(prompt.contains("You are Maya"))
        assertTrue(prompt.contains("/no_think"))
        assertTrue(prompt.contains("<|im_start|>user\nHi Maya<|im_end|>\n"))
        assertTrue(prompt.contains("<|im_start|>assistant\nHello da!<|im_end|>\n"))
        assertTrue(prompt.contains("<|im_start|>user\nEpdi irukka?<|im_end|>\n"))
        assertTrue(prompt.endsWith("<|im_start|>assistant\n$thinkOpen\n\n$thinkClose\n\n"))
    }

    @Test
    fun `skips failed and streaming replies`() {
        val prompt = PromptBuilder.build(
            persona = "maya",
            history = listOf(
                message("u1", MessageRole.USER, "First"),
                message("a1", MessageRole.MAYA, "bad", MessageStatus.FAILED),
                message("a2", MessageRole.MAYA, "partial", MessageStatus.STREAMING),
                message("u2", MessageRole.USER, "Second"),
            ),
        )

        assertFalse(prompt.contains("bad"))
        assertFalse(prompt.contains("partial"))
        assertTrue(prompt.contains("Second"))
    }

    @Test
    fun `keeps latest turn when budget is tiny`() {
        val thinkOpen = "<" + "think>"
        val thinkClose = "</" + "think>"
        val prompt = PromptBuilder.build(
            persona = "teacher",
            history = listOf(
                message("u1", MessageRole.USER, "a".repeat(1000)),
                message("a1", MessageRole.MAYA, "b".repeat(1000)),
                message("u2", MessageRole.USER, "latest"),
            ),
            maxChars = 600,
        )

        assertTrue(prompt.contains("latest"))
        assertTrue(prompt.endsWith("<|im_start|>assistant\n$thinkOpen\n\n$thinkClose\n\n"))
        assertTrue(prompt.length < 900)
    }

    @Test
    fun `strips qwen reasoning blocks`() {
        val thinkOpen = "<" + "think>"
        val thinkClose = "</" + "think>"
        val raw = "$thinkOpen\nreasoning\n$thinkClose\n\nFinal answer"
        assertEquals("Final answer", PromptBuilder.stripThink(raw).trim())
    }

    @Test
    fun `empty history produces no prompt`() {
        assertEquals("", PromptBuilder.build("maya", emptyList()))
    }
}

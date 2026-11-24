package com.devaraj.maya.data.model

import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus

/**
 * Qwen3 ChatML prompt builder (plan §17.2).
 *
 * Qwen3 models "think" by default, which is far too slow on a phone CPU.
 * The official non-thinking template appends an empty think block after the
 * assistant header, and we also add `/no_think` to the system prompt.
 */
object PromptBuilder {

    /** Leave room in the 2048-token context for the reply. */
    const val MAX_PROMPT_CHARS = 4_500

    const val MAX_NEW_TOKENS = 160

    private const val SYSTEM_MAYA =
        "You are Maya, the user's private AI assistant running on this phone. " +
            "Be warm, direct and concise. The user speaks Thanglish (Tamil written " +
            "in English letters) and English; reply in the same language the user " +
            "used. When the laptop is offline you can only chat, not control devices. " +
            "/no_think"

    private const val SYSTEM_TEACHER =
        "You are Maya, a patient English teacher. Reply briefly, correct mistakes " +
            "gently, and give one small example. Use simple English. /no_think"

    private const val THINK_OPEN = "<" + "think>"
    private const val THINK_CLOSE = "</" + "think>"

    fun systemPrompt(persona: String): String =
        if (persona == "teacher") SYSTEM_TEACHER else SYSTEM_MAYA

    /**
     * Build a ChatML prompt from the newest turns that fit in the budget.
     * Only completed messages are used so failed/partial replies never leak
     * back into the model context.
     */
    fun build(
        persona: String,
        history: List<Message>,
        maxChars: Int = MAX_PROMPT_CHARS,
    ): String {
        val system = systemPrompt(persona)
        val budget = (maxChars - system.length).coerceAtLeast(200)

        val turns = history.asSequence()
            .filter { it.role == MessageRole.USER || it.role == MessageRole.MAYA || it.role == MessageRole.ASSISTANT }
            .filter { it.status == MessageStatus.SENT }
            .filter { it.content.isNotBlank() }
            .toList()

        val selected = ArrayList<Message>()
        var used = 0
        for (message in turns.asReversed()) {
            var content = sanitize(message.content)
            if (content.isBlank()) continue

            if (selected.isEmpty()) {
                // Always keep the newest turn; trim it only if it alone is huge.
                if (content.length > budget) content = content.take(budget)
                selected.add(message.copy(content = content))
                used = content.length
                continue
            }

            if (used + content.length + 16 > budget) break
            selected.add(message.copy(content = content))
            used += content.length
        }

        if (selected.isEmpty()) return ""

        return buildString {
            append("<|im_start|>system\n")
            append(system)
            append("<|im_end|>\n")
            selected.asReversed().forEach { message ->
                val role = if (message.role == MessageRole.USER) "user" else "assistant"
                append("<|im_start|>")
                append(role)
                append('\n')
                append(message.content.trim())
                append("<|im_end|>\n")
            }
            // Official Qwen3 non-thinking generation prompt.
            append("<|im_start|>assistant\n")
            append(THINK_OPEN)
            append("\n\n")
            append(THINK_CLOSE)
            append("\n\n")
        }
    }

    /** Remove Qwen3 reasoning blocks from text that will be shown or reused. */
    fun stripThink(text: String): String {
        var out = text
        while (true) {
            val start = out.indexOf(THINK_OPEN)
            if (start < 0) break
            val end = out.indexOf(THINK_CLOSE, start)
            out = if (end < 0) {
                out.substring(0, start)
            } else {
                out.removeRange(start, end + THINK_CLOSE.length)
            }
        }
        return out
    }

    private fun sanitize(text: String): String = stripThink(text).trim()
}

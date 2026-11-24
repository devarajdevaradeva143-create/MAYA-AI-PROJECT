package com.devaraj.maya.domain

import com.devaraj.maya.domain.model.Message

/**
 * Chat request limits from the mobile plan (§15): the last 24 messages and at
 * most 12 000 characters are sent to the model.
 */
object ChatLimits {
    const val MAX_MESSAGES = 24
    const val MAX_CHARS = 12_000

    fun trimHistory(messages: List<Message>): List<Message> {
        if (messages.isEmpty()) return emptyList()
        val recent = messages.takeLast(MAX_MESSAGES)

        var total = 0
        var startIndex = recent.size
        for (index in recent.indices.reversed()) {
            val length = recent[index].content.length
            if (total + length > MAX_CHARS) break
            total += length
            startIndex = index
        }

        // Always send the newest message, truncated if it alone is oversized.
        if (startIndex == recent.size) {
            val newest = recent.last()
            return listOf(newest.copy(content = newest.content.take(MAX_CHARS)))
        }
        return recent.subList(startIndex, recent.size).toList()
    }
}

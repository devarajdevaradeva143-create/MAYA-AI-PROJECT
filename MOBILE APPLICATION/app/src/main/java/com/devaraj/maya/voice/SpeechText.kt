package com.devaraj.maya.voice

/**
 * Turns a chat-style reply into plain text a TTS engine can read.
 *
 * Markdown and emoji are visual only; spoken aloud they turn into
 * "star star" / "hash" noise, so they are removed before speaking.
 */
object SpeechText {

    fun strip(text: String): String {
        var s = text
        s = s.replace(Regex("```[\\s\\S]*?```"), " ")
        s = s.replace(Regex("`([^`]*)`"), "$1")
        s = s.replace(Regex("!\\[[^\\]]*]\\([^)]*\\)"), " ")
        s = s.replace(Regex("\\[([^\\]]*)]\\([^)]*\\)"), "$1")
        s = s.replace(Regex("(?m)^\\s{0,3}#{1,6}\\s*"), "")
        s = s.replace(Regex("(?m)^\\s*[-*+]\\s+"), "")
        s = s.replace(Regex("(?m)^\\s*\\d+[.)]\\s+"), "")
        s = s.replace(Regex("~~(.*?)~~"), "$1")
        s = s.replace(Regex("(\\*\\*|__)(.*?)\\1"), "$2")
        s = s.replace(Regex("(\\*|_)(.*?)\\1"), "$2")
        s = s.replace(Regex("<[^>]+>"), " ")
        s = removeEmoji(s)
        s = s.replace(Regex("[ \\t]+"), " ")
        s = s.replace(Regex("\\n{2,}"), "\n")
        return s.trim()
    }

    private fun removeEmoji(input: String): String {
        val out = StringBuilder(input.length)
        var i = 0
        while (i < input.length) {
            val codePoint = input.codePointAt(i)
            if (!isEmoji(codePoint)) out.appendCodePoint(codePoint)
            i += Character.charCount(codePoint)
        }
        return out.toString()
    }

    private fun isEmoji(codePoint: Int): Boolean =
        codePoint in 0x1F000..0x1FAFF ||   // emoji blocks (includes ❤️'s companions)
            codePoint in 0x2600..0x27BF || // misc symbols / dingbats
            codePoint in 0x2190..0x21FF || // arrows
            codePoint in 0x2B00..0x2BFF || // stars, arrows
            codePoint == 0xFE0F ||          // variation selector-16
            codePoint == 0x200D ||          // zero-width joiner
            codePoint == 0x2764            // heavy black heart
}

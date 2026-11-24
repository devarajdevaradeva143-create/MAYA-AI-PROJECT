package com.devaraj.maya.domain.model

/**
 * Operating mode for MAYA AI (spec: docs/REQUIREMENTS.md).
 * - AI: MAYA performs tasks autonomously (voice/text commands).
 * - REMOTE: user controls the laptop directly from the phone.
 * - HYBRID: user and MAYA work simultaneously; user always wins control conflicts.
 */
enum class OperatingMode(val value: String) {
    AI("ai"),
    REMOTE("remote"),
    HYBRID("hybrid");

    companion object {
        fun from(value: String?): OperatingMode =
            values().firstOrNull { it.value == value } ?: AI
    }
}
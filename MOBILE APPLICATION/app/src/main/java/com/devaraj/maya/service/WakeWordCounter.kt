package com.devaraj.maya.service

/**
 * Counts "maya" utterances heard by the Vosk name detector.
 *
 * Wake rule: say "Maya" three times within [windowMs]. After a trigger the
 * counter clears and waits [cooldownMs] so a single conversation cannot wake
 * the app repeatedly.
 *
 * Pure Kotlin (no Android/Vosk types) so it can be unit-tested on the JVM.
 */
class WakeWordCounter(
    private val required: Int = 3,
    private val windowMs: Long = 10_000,
    private val cooldownMs: Long = 8_000,
    private val now: () -> Long = System::currentTimeMillis,
) {

    private val hits = ArrayDeque<Long>()
    private var lastTriggerAt = Long.MIN_VALUE

    init {
        require(required > 0) { "required must be positive" }
    }

    /** Feed a final Vosk transcript. Returns true when Maya should wake. */
    @Synchronized
    fun onFinalText(text: String): Boolean {
        val normalized = text.lowercase()
        repeat(MAYA.findAll(normalized).count()) {
            hits.addLast(now())
        }
        prune()

        val time = now()
        if (hits.size < required) return false
        if (lastTriggerAt != Long.MIN_VALUE && time - lastTriggerAt < cooldownMs) {
            // Still in cooldown: drop the oldest hit so a later phrase can win.
            if (hits.isNotEmpty()) hits.removeFirst()
            return false
        }
        hits.clear()
        lastTriggerAt = time
        return true
    }

    @Synchronized
    fun reset() {
        hits.clear()
        lastTriggerAt = Long.MIN_VALUE
    }

    private fun prune() {
        val cutoff = now() - windowMs
        while (hits.isNotEmpty() && hits.first() < cutoff) {
            hits.removeFirst()
        }
    }

    private companion object {
        val MAYA = Regex("\\bmaya\\b")
    }
}

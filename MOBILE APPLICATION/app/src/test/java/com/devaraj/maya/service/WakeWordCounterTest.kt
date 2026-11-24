package com.devaraj.maya.service

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Pure JVM tests for the "Maya" x3 wake rule (Phase 10). */
class WakeWordCounterTest {

    private var now = 1_000L
    private lateinit var counter: WakeWordCounter

    @Before
    fun setUp() {
        now = 1_000L
        counter = WakeWordCounter(
            required = 3,
            windowMs = 10_000,
            cooldownMs = 8_000,
            now = { now },
        )
    }

    @Test
    fun twoMentionsDoNotWake() {
        assertFalse(counter.onFinalText("maya"))
        assertFalse(counter.onFinalText("maya"))
    }

    @Test
    fun threeMentionsWithinWindowWake() {
        assertFalse(counter.onFinalText("maya"))
        assertFalse(counter.onFinalText("hey maya"))
        assertTrue(counter.onFinalText("maya are you there"))
    }

    @Test
    fun oneTranscriptWithThreeMentionsWakes() {
        assertTrue(counter.onFinalText("maya maya maya"))
    }

    @Test
    fun mentionsOutsideWindowDoNotCount() {
        assertFalse(counter.onFinalText("maya"))
        now += 6_000
        assertFalse(counter.onFinalText("maya"))
        now += 6_000
        // The first mention is now 12 s old; only two hits remain in the window.
        assertFalse(counter.onFinalText("maya"))
    }

    @Test
    fun unrelatedTextIsIgnored() {
        listOf("hi", "play music", "maybe", "good morning").forEach {
            assertFalse(counter.onFinalText(it))
        }
    }

    @Test
    fun cooldownBlocksImmediateRewake() {
        assertTrue(counter.onFinalText("maya maya maya"))
        now += 1_000
        repeat(3) { assertFalse(counter.onFinalText("maya")) }
        now += 8_000
        // Two hits survived the cooldown; the next "maya" completes the window.
        assertTrue(counter.onFinalText("maya"))
    }

    @Test
    fun resetClearsHits() {
        counter.onFinalText("maya")
        counter.onFinalText("maya")
        counter.reset()
        assertFalse(counter.onFinalText("maya"))
        assertFalse(counter.onFinalText("maya"))
        assertTrue(counter.onFinalText("maya"))
    }
}

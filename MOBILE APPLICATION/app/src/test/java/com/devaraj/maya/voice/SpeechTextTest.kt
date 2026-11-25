package com.devaraj.maya.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SpeechTextTest {

    @Test
    fun `removes markdown formatting`() {
        val input = "## Title\n**Bold** and *italic* and `code`"
        val out = SpeechText.strip(input)
        assertFalse(out.contains("#"))
        assertFalse(out.contains("*"))
        assertFalse(out.contains("`"))
        assertTrue(out.contains("Bold"))
        assertTrue(out.contains("italic"))
        assertTrue(out.contains("code"))
    }

    @Test
    fun `removes bullet markers and keeps text`() {
        val out = SpeechText.strip("- one\n- two\n1. three")
        assertFalse(out.contains("-"))
        assertTrue(out.contains("one"))
        assertTrue(out.contains("three"))
    }

    @Test
    fun `removes emoji including heart`() {
        val out = SpeechText.strip("Vanakkam da ❤️😊 epdi irukka?")
        assertEquals("Vanakkam da epdi irukka?", out)
    }

    @Test
    fun `keeps tamil text untouched`() {
        val out = SpeechText.strip("சொல்லுங்க, நான் இங்கே தான் இருக்கேன்.")
        assertEquals("சொல்லுங்க, நான் இங்கே தான் இருக்கேன்.", out)
    }

    @Test
    fun `strips links but keeps label`() {
        val out = SpeechText.strip("See [docs](https://example.com) now")
        assertEquals("See docs now", out)
    }

    @Test
    fun `blank when only formatting`() {
        assertEquals("", SpeechText.strip("**  ** ❤️"))
    }
}

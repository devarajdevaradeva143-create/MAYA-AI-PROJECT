package com.devaraj.maya.data.prefs

import org.junit.Assert.assertEquals
import org.junit.Test

class ThemeModeTest {

    @Test
    fun `known values parse`() {
        assertEquals(ThemeMode.SYSTEM, ThemeMode.from("system"))
        assertEquals(ThemeMode.DARK, ThemeMode.from("dark"))
        assertEquals(ThemeMode.LIGHT, ThemeMode.from("light"))
    }

    @Test
    fun `unknown or missing values fall back to system`() {
        assertEquals(ThemeMode.SYSTEM, ThemeMode.from(null))
        assertEquals(ThemeMode.SYSTEM, ThemeMode.from(""))
        assertEquals(ThemeMode.SYSTEM, ThemeMode.from("purple"))
    }
}

package com.devaraj.maya.ui.laptop

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.ui.theme.MayaTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RemoteKeypadTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun everyKeyButtonSendsItsServerKey() {
        var clicked: String? = null
        compose.setContent {
            MayaTheme(darkTheme = false) {
                RemoteKeypad(onKey = { clicked = it })
            }
        }

        val expected = mapOf(
            "↑ Up" to "up",
            "↓ Down" to "down",
            "← Left" to "left",
            "→ Right" to "right",
            "Home" to "home",
            "End" to "end",
            "PgUp" to "pageup",
            "PgDn" to "pagedown",
            "Del" to "delete",
            "Space" to "space",
            "Tab" to "tab",
            "Esc" to "esc",
            "Cut" to "ctrl+x",
            "Undo" to "ctrl+z",
            "Alt+Tab" to "alt+tab",
            "F5" to "f5",
        )

        expected.forEach { (label, key) ->
            clicked = null
            compose.onNodeWithText(label).performClick()
            assertEquals("label '$label' should send '$key'", key, clicked)
        }
    }
}

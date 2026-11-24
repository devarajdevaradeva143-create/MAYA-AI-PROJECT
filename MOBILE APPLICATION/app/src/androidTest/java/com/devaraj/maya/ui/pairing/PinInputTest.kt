package com.devaraj.maya.ui.pairing

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.ui.theme.MayaTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PinInputTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun typingDigitsUpdatesPin() {
        var pin by mutableStateOf("")

        compose.setContent {
            MayaTheme(darkTheme = false) {
                PinInput(pin = pin, onPinChange = { pin = it.take(6) })
            }
        }

        compose.onNode(hasSetTextAction()).performTextInput("123456")

        compose.runOnIdle { assertEquals("123456", pin) }
    }

    @Test
    fun filledBoxesShowEnteredDigits() {
        compose.setContent {
            MayaTheme(darkTheme = false) {
                PinInput(pin = "42", onPinChange = {})
            }
        }

        compose.onNodeWithText("4").assertExists()
        compose.onNodeWithText("2").assertExists()
    }
}

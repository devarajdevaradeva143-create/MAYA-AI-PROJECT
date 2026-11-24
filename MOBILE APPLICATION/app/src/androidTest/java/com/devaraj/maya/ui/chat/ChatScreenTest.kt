package com.devaraj.maya.ui.chat

import android.content.Context
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.R
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.data.remote.HealthDto
import com.devaraj.maya.domain.model.Device
import com.devaraj.maya.ui.theme.MayaTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ChatScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val send = context.getString(R.string.chat_send)
    private val cancel = context.getString(R.string.laptop_cancel)
    private val deleteChat = context.getString(R.string.chat_delete)

    private val connected = ConnectionState.Connected(
        device = Device("dev-1", "Laptop", "10.0.0.5", 8420, lastSeen = 0),
        health = HealthDto(
            status = "ok",
            app = "maya",
            version = "1.0",
            api = 1,
            platform = "windows",
        ),
    )

    private fun setChat(
        onSend: (String) -> Unit = {},
        onDeleteChat: () -> Unit = {},
    ) {
        compose.setContent {
            MayaTheme(darkTheme = false) {
                ChatScreen(
                    state = ChatUiState(connection = connected),
                    onSend = onSend,
                    onStop = {},
                    onRetry = {},
                    onNewChat = {},
                    onDeleteChat = onDeleteChat,
                    onPersonaChange = {},
                    onDismissError = {},
                )
            }
        }
    }

    @Test
    fun sendIsDisabledUntilTextIsEntered() {
        setChat()

        compose.onNodeWithContentDescription(send).assertIsNotEnabled()
        compose.onNode(hasSetTextAction()).performTextInput("hello maya")
        compose.onNodeWithContentDescription(send).assertIsEnabled()
    }

    @Test
    fun sendDeliversComposerText() {
        var sent: String? = null
        setChat(onSend = { sent = it })

        compose.onNode(hasSetTextAction()).performTextInput("hi da")
        compose.onNodeWithContentDescription(send).performClick()

        compose.runOnIdle { assertEquals("hi da", sent) }
    }

    @Test
    fun deleteDialogCancelKeepsChat() {
        var deleted = false
        setChat(onDeleteChat = { deleted = true })

        compose.onNodeWithContentDescription(deleteChat).performClick()
        compose.onNodeWithText(context.getString(R.string.chat_delete_title)).assertExists()
        compose.onNodeWithText(cancel).performClick()

        compose.runOnIdle { assertFalse(deleted) }
        compose.onNodeWithText(context.getString(R.string.chat_delete_title)).assertDoesNotExist()
    }

    @Test
    fun deleteDialogConfirmDeletesChat() {
        var deleted = false
        setChat(onDeleteChat = { deleted = true })

        compose.onNodeWithContentDescription(deleteChat).performClick()
        compose.onNodeWithText(context.getString(R.string.chat_delete_confirm)).performClick()

        compose.runOnIdle { assertTrue(deleted) }
    }
}

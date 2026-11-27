package com.devaraj.maya.ui.chat

import androidx.core.net.toUri

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.devaraj.maya.R
import com.devaraj.maya.domain.model.AiSource
import com.devaraj.maya.domain.model.Message
import com.devaraj.maya.domain.model.MessageRole
import com.devaraj.maya.domain.model.MessageStatus
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import com.devaraj.maya.ui.connection.reasonText

@Composable
fun ChatScreen(
    state: ChatUiState,
    onSend: (String) -> Unit,
    onStop: () -> Unit,
    onRetry: () -> Unit,
    onNewChat: () -> Unit,
    onDeleteChat: () -> Unit,
    onPersonaChange: (String) -> Unit,
    onDismissError: () -> Unit,
    onSendToWhatsApp: (String) -> String = { "" },
    modifier: Modifier = Modifier,
) {
    var input by rememberSaveable { mutableStateOf("") }
    var confirmDelete by rememberSaveable { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val context = LocalContext.current

    LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.content?.length) {
        if (state.messages.isNotEmpty()) {
            listState.scrollToItem(state.messages.lastIndex)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .imePadding(),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 4.dp),
        ) {
            FilterChip(
                selected = state.persona == ChatUiState.PERSONA_MAYA,
                onClick = { onPersonaChange(ChatUiState.PERSONA_MAYA) },
                label = { Text(text = stringResource(R.string.chat_persona_maya)) },
            )
            Spacer(modifier = Modifier.width(8.dp))
            FilterChip(
                selected = state.persona == ChatUiState.PERSONA_TEACHER,
                onClick = { onPersonaChange(ChatUiState.PERSONA_TEACHER) },
                label = { Text(text = stringResource(R.string.chat_persona_teacher)) },
            )
            Spacer(modifier = Modifier.weight(1f))
            TextButton(onClick = onNewChat) {
                Text(text = stringResource(R.string.chat_new))
            }
            IconButton(onClick = { confirmDelete = true }) {
                Icon(
                    imageVector = Icons.Outlined.DeleteOutline,
                    contentDescription = stringResource(R.string.chat_delete),
                )
            }
        }

        if (!state.connected) {
            Surface(
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = MaterialTheme.shapes.small,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 4.dp),
            ) {
                Text(
                    text = stringResource(
                        if (state.phoneModelReady) {
                            R.string.chat_offline_phone_banner
                        } else {
                            R.string.chat_offline_banner
                        },
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
        }

        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(
                horizontal = 12.dp,
                vertical = 8.dp,
            ),
        ) {
            if (state.messages.isEmpty()) {
                item {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 40.dp, horizontal = 24.dp),
                    ) {
                        Text(
                            text = stringResource(R.string.chat_greeting),
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            text = stringResource(R.string.chat_prompt_hint),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(top = 12.dp, bottom = 8.dp),
                        )
                        AssistChip(
                            onClick = {
                                input = context.getString(R.string.chat_prompt_explain)
                            },
                            label = {
                                Text(text = stringResource(R.string.chat_prompt_explain))
                            },
                        )
                        AssistChip(
                            onClick = {
                                input = context.getString(R.string.chat_prompt_message)
                            },
                            label = {
                                Text(text = stringResource(R.string.chat_prompt_message))
                            },
                        )
                        AssistChip(
                            onClick = {
                                input = context.getString(R.string.chat_prompt_translate)
                            },
                            label = {
                                Text(text = stringResource(R.string.chat_prompt_translate))
                            },
                        )
                    }
                }
            }
            items(state.messages, key = { it.id }) { message ->
                MessageBubble(message = message, onRetry = onRetry, onSendToWhatsApp = onSendToWhatsApp)
            }
        }

        state.errorReason?.let { reason ->
            ErrorBar(
                message = reasonText(reason),
                detail = state.errorMessage,
                onRetry = onRetry,
                onDismiss = onDismissError,
            )
        }

        if (!state.canSend) {
            Text(
                text = stringResource(R.string.chat_no_source_hint),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
        }

        Composer(
            input = input,
            onInputChange = { input = it },
            streaming = state.streaming,
            onSend = {
                val text = input
                // Keep the draft when there is no AI source so the user does
                // not lose what they typed.
                if (state.canSend) input = ""
                onSend(text)
            },
            onStop = onStop,
        )
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text(text = stringResource(R.string.chat_delete_title)) },
            text = { Text(text = stringResource(R.string.chat_delete_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDelete = false
                        onDeleteChat()
                    },
                ) {
                    Text(
                        text = stringResource(R.string.chat_delete_confirm),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmDelete = false }) {
                    Text(text = stringResource(R.string.laptop_cancel))
                }
            },
        )
    }
}

@Composable
private fun MessageBubble(
    message: Message,
    onRetry: () -> Unit,
    onSendToWhatsApp: (String) -> String,
) {
    val isUser = message.role == MessageRole.USER
    val isAssistant = message.role == MessageRole.MAYA || message.role == MessageRole.ASSISTANT
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start,
    ) {
        Surface(
            color = if (isUser) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
            shape = RoundedCornerShape(
                topStart = 18.dp,
                topEnd = 18.dp,
                bottomStart = if (isUser) 18.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 18.dp,
            ),
            modifier = Modifier.fillMaxWidth(0.85f),
        ) {
            val baseText = buildString {
                append(message.content)
                if (message.status == MessageStatus.STREAMING) append("▌")
            }
            val rendered = parseSimpleMarkdown(baseText.ifBlank { "…" })
            Text(
                text = rendered,
                style = MaterialTheme.typography.bodyLarge,
                color = if (isUser) {
                    MaterialTheme.colorScheme.onPrimary
                } else {
                    MaterialTheme.colorScheme.onSurface
                },
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = when {
                    isUser -> stringResource(R.string.chat_you)
                    message.source == AiSource.LAPTOP -> stringResource(R.string.chat_source_laptop)
                    message.source == AiSource.PHONE -> stringResource(R.string.chat_source_phone)
                    message.source == AiSource.CLOUD -> stringResource(R.string.chat_source_cloud)
                    else -> ""
                },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (isAssistant && message.content.isNotBlank()) {
                val context = LocalContext.current
                TextButton(onClick = {
                    val url = onSendToWhatsApp(message.content)
                    try {
                        val intent = Intent(Intent.ACTION_VIEW, url.toUri())
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        context.startActivity(intent)
                    } catch (e: Exception) {
                        Toast.makeText(context, "WhatsApp not available", Toast.LENGTH_SHORT).show()
                    }
                }) {
                    Text(text = "Send to WhatsApp", style = MaterialTheme.typography.labelSmall)
                }
            }
            if (message.status == MessageStatus.FAILED) {
                TextButton(onClick = onRetry) {
                    Text(text = stringResource(R.string.chat_retry))
                }
            }
        }
    }
}

@Composable
private fun ErrorBar(
    message: String,
    detail: String?,
    onRetry: () -> Unit,
    onDismiss: () -> Unit,
) {
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f).padding(start = 12.dp, top = 8.dp, bottom = 8.dp)) {
                Text(
                    text = message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                )
                if (!detail.isNullOrBlank() && detail != message) {
                    Text(
                        text = detail,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }
            TextButton(onClick = onRetry) {
                Text(text = stringResource(R.string.chat_retry))
            }
            IconButton(onClick = onDismiss) {
                Icon(
                    imageVector = Icons.Filled.Close,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onErrorContainer,
                )
            }
        }
    }
}

@Composable
private fun Composer(
    input: String,
    onInputChange: (String) -> Unit,
    streaming: Boolean,
    onSend: () -> Unit,
    onStop: () -> Unit,
) {
    Row(
        verticalAlignment = Alignment.Bottom,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        OutlinedTextField(
            value = input,
            onValueChange = { newValue ->
                if (newValue.endsWith("\n") && newValue.trim().isNotEmpty() && !streaming) {
                    // ChatScreen clears the draft only when a source exists.
                    onSend()
                } else {
                    onInputChange(newValue)
                }
            },
            placeholder = { Text(text = stringResource(R.string.chat_composer_hint)) },
            modifier = Modifier.weight(1f),
            maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(
                onSend = {
                    if (input.isNotBlank() && !streaming) onSend()
                },
            ),
        )

        Spacer(modifier = Modifier.width(4.dp))

        if (streaming) {
            IconButton(onClick = onStop) {
                Icon(
                    imageVector = Icons.Filled.Stop,
                    contentDescription = stringResource(R.string.chat_stop),
                    tint = MaterialTheme.colorScheme.error,
                )
            }
        } else {
            IconButton(
                onClick = onSend,
                enabled = input.isNotBlank(),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.Send,
                    contentDescription = stringResource(R.string.chat_send),
                    tint = if (input.isNotBlank()) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
    }
}


// ---- simple markdown (bold / italic / inline code) ----
private val MD_REGEX = Regex("""\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`""")

fun parseSimpleMarkdown(input: String): AnnotatedString = buildAnnotatedString {
    // Convert markdown bullets to bullet char.
    val normalized = input.lines().joinToString("\n") { line ->
        val trimmed = line.trimStart()
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
            line.replaceFirst(Regex("^\\s*[-*] "), "• ")
        } else line
    }
    var last = 0
    for (m in MD_REGEX.findAll(normalized)) {
        if (m.range.first > last) {
            append(normalized.substring(last, m.range.first))
        }
        val (bold, italic, code) = m.destructured
        when {
            bold.isNotEmpty() -> { pushStyle(SpanStyle(fontWeight = FontWeight.Bold)); append(bold); pop() }
            italic.isNotEmpty() -> { pushStyle(SpanStyle(fontStyle = FontStyle.Italic)); append(italic); pop() }
            code.isNotEmpty() -> { pushStyle(SpanStyle(fontFamily = FontFamily.Monospace)); append(code); pop() }
        }
        last = m.range.last + 1
    }
    if (last < normalized.length) append(normalized.substring(last))
}

package com.devaraj.maya.ui.laptop

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.devaraj.maya.R

@Composable
fun LaptopControlSection(
    state: LaptopControlUiState,
    enabled: Boolean,
    onAppNameChange: (String) -> Unit,
    onVolumeChange: (Int) -> Unit,
    onClipboardChange: (String) -> Unit,
    onOpenApp: () -> Unit,
    onLock: () -> Unit,
    onSleep: () -> Unit,
    onMute: () -> Unit,
    onUnmute: () -> Unit,
    onVolume: () -> Unit,
    onScreenshot: () -> Unit,
    onMediaPlay: () -> Unit,
    onMediaPause: () -> Unit,
    onMediaNext: () -> Unit,
    onMediaPrev: () -> Unit,
    onClipboardSet: () -> Unit,
    onNotify: () -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(text = "Laptop control", style = MaterialTheme.typography.titleLarge)

        if (!enabled) {
            Text(
                text = "Connect to laptop to use control actions.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // App open
        OutlinedTextField(
            value = state.appName,
            onValueChange = onAppNameChange,
            label = { Text("App to open") },
            singleLine = true,
            enabled = enabled && !state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onOpenApp, enabled = enabled && !state.busy) { Text("Open app") }
            Button(onClick = onNotify, enabled = enabled && !state.busy) { Text("Notify") }
        }

        // System actions
        Text(text = "System", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onLock, enabled = enabled && !state.busy) { Text("Lock") }
            Button(onClick = onSleep, enabled = enabled && !state.busy) { Text("Sleep") }
            Button(onClick = onScreenshot, enabled = enabled && !state.busy) { Text("Screenshot") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onMute, enabled = enabled && !state.busy) { Text("Mute") }
            Button(onClick = onUnmute, enabled = enabled && !state.busy) { Text("Unmute") }
        }
        Text(text = "Volume: ${state.volumeLevel}%", style = MaterialTheme.typography.bodyMedium)
        Slider(
            value = state.volumeLevel.toFloat(),
            onValueChange = { onVolumeChange(it.toInt()) },
            valueRange = 0f..100f,
            enabled = enabled && !state.busy,
        )
        Button(onClick = onVolume, enabled = enabled && !state.busy) { Text("Set volume") }

        // Media
        Text(text = "Media", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = onMediaPlay, enabled = enabled && !state.busy) { Text("Play") }
            Button(onClick = onMediaPause, enabled = enabled && !state.busy) { Text("Pause") }
            Button(onClick = onMediaPrev, enabled = enabled && !state.busy) { Text("Prev") }
            Button(onClick = onMediaNext, enabled = enabled && !state.busy) { Text("Next") }
        }

        // Clipboard
        Text(text = "Clipboard", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = state.clipboardText,
            onValueChange = onClipboardChange,
            label = { Text("Text to send") },
            minLines = 2,
            enabled = enabled && !state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = onClipboardSet, enabled = enabled && !state.busy) { Text("Set clipboard") }

        state.error?.let {
            Text(text = it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
        }

        // Activity log
        Text(text = "Activity log", style = MaterialTheme.typography.titleMedium)
        if (state.log.isEmpty()) {
            Text(text = "No commands yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            state.log.take(20).forEach { entry ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(text = "${entry.action} — ${entry.status}", style = MaterialTheme.typography.bodyMedium)
                        Text(
                            text = entry.message,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Spacer(modifier = Modifier.height(6.dp))
            }
        }
    }

    val token = state.pendingToken
    if (token != null) {
        var remaining by remember(token) { mutableIntStateOf(state.pendingExpiresAtMs?.let { ((it - System.currentTimeMillis()) / 1000).toInt() } ?: 60) }
        LaunchedEffect(token, state.pendingExpiresAtMs) {
            val expiry = state.pendingExpiresAtMs ?: (System.currentTimeMillis() + 60_000)
            while (true) {
                val left = ((expiry - System.currentTimeMillis()) / 1000).toInt()
                remaining = left.coerceAtLeast(0)
                if (left <= 0) break
                kotlinx.coroutines.delay(1000)
            }
        }
        AlertDialog(
            onDismissRequest = onCancel,
            title = { Text("Confirm action") },
            text = {
                Column {
                    Text(state.pendingDescription ?: "Allow this action on the laptop?")
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Expires in ${remaining}s",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            },
            confirmButton = { TextButton(onClick = onConfirm, enabled = remaining > 0) { Text("Allow") } },
            dismissButton = { TextButton(onClick = onCancel) { Text(stringResource(R.string.laptop_cancel)) } },
        )
    }
}

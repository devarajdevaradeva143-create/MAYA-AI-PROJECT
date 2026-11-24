package com.devaraj.maya.ui.laptop

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.devaraj.maya.data.remote.FileEntryDto
import com.devaraj.maya.domain.model.OperatingMode

@Composable
fun RemoteSection(
    vm: RemoteViewModel,
    operatingMode: OperatingMode,
    connectionEnabled: Boolean,
    actionsContent: @Composable () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by vm.state.collectAsState()
    val context = LocalContext.current

    val uploadLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri != null) vm.upload(uri)
    }
    val downloadLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri: Uri? ->
        // handled when a pending download path is set; see row action below
    }

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(text = "Remote control", style = MaterialTheme.typography.titleLarge)

        if (!connectionEnabled) {
            Text(
                text = "Connect to laptop to use remote control.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        if (operatingMode == OperatingMode.AI) {
            Text(
                text = "Switch to REMOTE or HYBRID in Settings to use screen control.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            actionsContent()
            return@Column
        }

        // Session control
        Card {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = if (state.sessionActive) "Session active (${state.sessionExpiresIn}s left)" else "No active session",
                    style = MaterialTheme.typography.titleMedium,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!state.sessionActive) {
                        Button(onClick = vm::startSession, enabled = !state.busy) { Text("Start session") }
                    } else {
                        OutlinedButton(onClick = vm::stopSession, enabled = !state.busy) { Text("Stop session") }
                    }
                }
                state.error?.let {
                    Text(text = it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                }
                state.fileMessage?.let {
                    Text(text = it, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }

        // Confirm dialog
        val confirmToken = state.confirmToken
        if (confirmToken != null) {
            androidx.compose.material3.AlertDialog(
                onDismissRequest = vm::cancelConfirm,
                title = { Text("Allow remote control?") },
                text = {
                    Text(state.confirmDescription ?: "Allow remote screen and input from this phone?")
                },
                confirmButton = {
                    TextButton(onClick = vm::confirmSession, enabled = !state.busy) { Text("Allow") }
                },
                dismissButton = {
                    TextButton(onClick = vm::cancelConfirm) { Text("Deny") }
                },
            )
        }

        if (state.sessionActive) {
            TabRow(selectedTabIndex = state.selectedTab) {
                Tab(selected = state.selectedTab == 0, onClick = { vm.selectTab(0) }, text = { Text("Screen") })
                Tab(selected = state.selectedTab == 1, onClick = { vm.selectTab(1) }, text = { Text("Actions") })
                Tab(selected = state.selectedTab == 2, onClick = { vm.selectTab(2) }, text = { Text("Files") })
            }

            when (state.selectedTab) {
                0 -> ScreenTab(state, vm)
                1 -> actionsContent()
                2 -> FilesTab(state, vm, uploadLauncher)
            }
        }

        // Hybrid card
        HybridCard(state, vm)
    }
}

@Composable
private fun ScreenTab(state: RemoteUiState, vm: RemoteViewModel) {
    var boxSize by remember { mutableStateOf(IntSize.Zero) }
    var text by remember { mutableStateOf("") }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(260.dp)
                .onSizeChanged { boxSize = it }
                .pointerInput(Unit) {
                    detectTapGestures(
                        onTap = { off ->
                            if (boxSize.width > 0 && boxSize.height > 0) {
                                val nx = (off.x / boxSize.width).coerceIn(0f, 1f)
                                val ny = (off.y / boxSize.height).coerceIn(0f, 1f)
                                vm.sendMove(nx, ny)
                                vm.click("left")
                            }
                        },
                        onLongPress = { off ->
                            if (boxSize.width > 0 && boxSize.height > 0) {
                                val nx = (off.x / boxSize.width).coerceIn(0f, 1f)
                                val ny = (off.y / boxSize.height).coerceIn(0f, 1f)
                                vm.sendMove(nx, ny)
                                vm.click("right")
                            }
                        },
                    )
                }
                .pointerInput("drag") {
                    detectDragGestures { change, _ ->
                        if (boxSize.width > 0 && boxSize.height > 0) {
                            val nx = (change.position.x / boxSize.width).coerceIn(0f, 1f)
                            val ny = (change.position.y / boxSize.height).coerceIn(0f, 1f)
                            vm.sendMove(nx, ny)
                        }
                        change.consume()
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            val bmp = state.screenBitmap
            if (bmp != null) {
                Image(bitmap = bmp.asImageBitmap(), contentDescription = "Screen", modifier = Modifier.fillMaxSize())
            } else if (state.screenLoading) {
                CircularProgressIndicator()
            } else {
                Text(text = state.screenError ?: "No frame yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { vm.scroll(3) }) { Text("Scroll up") }
            OutlinedButton(onClick = { vm.scroll(-3) }) { Text("Scroll down") }
            OutlinedButton(onClick = { vm.sendKey("enter") }) { Text("Enter") }
            OutlinedButton(onClick = { vm.sendKey("backspace") }) { Text("Bksp") }
            OutlinedButton(onClick = { vm.sendKey("esc") }) { Text("Esc") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { vm.sendKey("ctrl+v") }) { Text("Paste") }
            OutlinedButton(onClick = { vm.sendKey("ctrl+c") }) { Text("Copy") }
            OutlinedButton(onClick = { vm.sendKey("ctrl+a") }) { Text("Sel all") }
            OutlinedButton(onClick = { vm.sendKey("tab") }) { Text("Tab") }
        }

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text("Type text") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            Button(onClick = { vm.sendText(text); text = "" }) { Text("Send") }
        }
    }
}

@Composable
private fun FilesTab(
    state: RemoteUiState,
    vm: RemoteViewModel,
    uploadLauncher: ActivityResultLauncher<Array<String>>,
) {
    var pendingDownloadPath by remember { mutableStateOf<String?>(null) }
    val downloadLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        val path = pendingDownloadPath
        if (uri != null && path != null) vm.download(path, uri)
        pendingDownloadPath = null
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(text = state.filePath ?: "—", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
            OutlinedButton(onClick = vm::goUp, enabled = !state.fileBusy) { Text("Up") }
            OutlinedButton(onClick = { state.filePath?.let(vm::listPath) }, enabled = !state.fileBusy) { Text("Refresh") }
            OutlinedButton(onClick = { uploadLauncher.launch(arrayOf("*/*")) }, enabled = state.sessionActive && !state.fileBusy) { Text("Upload") }
        }
        if (state.fileBusy) {
            CircularProgressIndicator(modifier = Modifier.size(24.dp))
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(state.fileEntries) { entry ->
                FileRow(entry, vm) {
                    pendingDownloadPath = entry.path
                    downloadLauncher.launch(entry.name)
                }
            }
        }
    }
}

@Composable
private fun FileRow(entry: FileEntryDto, vm: RemoteViewModel, onDownload: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
    ) {
        Text(
            text = (if (entry.isDir) "\uD83D\uDCC1 " else "\uD83D\uDCC4 ") + entry.name,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodyMedium,
        )
        if (entry.isDir) {
            TextButton(onClick = { vm.listPath(entry.path) }) { Text("Open") }
        } else {
            entry.size?.let { Text(text = "${it}B", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            TextButton(onClick = onDownload) { Text("Download") }
        }
    }
}

@Composable
private fun HybridCard(state: RemoteUiState, vm: RemoteViewModel) {
    Card {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(text = "HYBRID mode", style = MaterialTheme.typography.titleMedium)
            val h = state.hybrid
            if (h != null) {
                Text(text = "Controller: ${h.controller}", style = MaterialTheme.typography.bodyMedium)
                Text(text = "AI busy: ${h.aiBusy}  Queued: ${h.queuedTasks}  Conflicts: ${h.conflicts}", style = MaterialTheme.typography.bodySmall)
                h.runningTask?.let { Text(text = "Running: $it", style = MaterialTheme.typography.bodySmall) }
            } else {
                Text(text = "No status yet", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = vm::hybridTakeover, enabled = !state.hybridBusy) { Text("Take control") }
                OutlinedButton(onClick = vm::hybridRelease, enabled = !state.hybridBusy) { Text("Release") }
            }
        }
    }
}

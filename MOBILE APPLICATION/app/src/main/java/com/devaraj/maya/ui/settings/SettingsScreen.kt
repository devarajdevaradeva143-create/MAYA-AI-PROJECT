package com.devaraj.maya.ui.settings

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.devaraj.maya.BuildConfig
import com.devaraj.maya.R
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.data.wake.VoskModelStatus
import com.devaraj.maya.domain.model.OperatingMode

@Composable
fun SettingsScreen(
    state: SettingsUiState,
    themeMode: ThemeMode,
    onThemeChange: (ThemeMode) -> Unit,
    connectionMode: String,
    onConnectionModeChange: (String) -> Unit,
    operatingMode: OperatingMode = OperatingMode.AI,
    onOperatingModeChange: (OperatingMode) -> Unit = {},
    controlEnabled: Boolean,
    onControlEnabledChange: (Boolean) -> Unit,
    requireUnlock: Boolean,
    onRequireUnlockChange: (Boolean) -> Unit,
    phoneRemoteEnabled: Boolean,
    onPhoneRemoteChange: (Boolean) -> Unit,
    screenSharing: Boolean = false,
    onStartScreenShare: (Int, Intent) -> Unit = { _, _ -> },
    onStopScreenShare: () -> Unit = {},
    onExport: (Uri) -> Unit,
    onDeleteAll: () -> Unit,
    onConsumeExportStatus: () -> Unit,
    onConsumeDeleteStatus: () -> Unit,
    onImportModel: (Uri) -> Unit,
    onDeleteModel: () -> Unit,
    onUnloadModel: () -> Unit,
    wakeRunning: Boolean = false,
    onWakeToggle: (Boolean) -> Unit = {},
    wakeNameEnabled: Boolean = false,
    onWakeNameChange: (Boolean) -> Unit = {},
    voskStatus: VoskModelStatus = VoskModelStatus(),
    voskBusy: Boolean = false,
    voskProgress: Int? = null,
    voskMessage: String? = null,
    onImportVosk: (Uri) -> Unit = {},
    onDeleteVosk: () -> Unit = {},
    geminiApiKey: String = "",
    onGeminiKeyChange: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    var confirmDelete by remember { mutableStateOf(false) }
    var confirmDeleteModel by remember { mutableStateOf(false) }
    var confirmDeleteVosk by remember { mutableStateOf(false) }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json"),
    ) { uri: Uri? ->
        if (uri != null) onExport(uri)
    }

    val modelPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? ->
        if (uri != null) onImportModel(uri)
    }

    val voskPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? ->
        if (uri != null) onImportVosk(uri)
    }

    val context = LocalContext.current
    val projectionManager = remember(context) {
        context.getSystemService(MediaProjectionManager::class.java)
    }
    val screenCaptureLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val data = result.data
        if (result.resultCode == Activity.RESULT_OK && data != null) {
            onStartScreenShare(result.resultCode, data)
        }
    }

    LaunchedEffect(state.exportStatus) {
        if (state.exportStatus != null) onConsumeExportStatus()
    }
    LaunchedEffect(state.deleteStatus) {
        if (state.deleteStatus != null) onConsumeDeleteStatus()
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Text(text = stringResource(R.string.settings_appearance), style = MaterialTheme.typography.titleMedium)
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) {
            ThemeMode.values().forEach { mode ->
                val label = when (mode) {
                    ThemeMode.SYSTEM -> R.string.theme_system
                    ThemeMode.DARK -> R.string.theme_dark
                    ThemeMode.LIGHT -> R.string.theme_light
                }
                FilterChip(
                    selected = themeMode == mode,
                    onClick = { onThemeChange(mode) },
                    label = { Text(text = stringResource(label)) },
                )
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Connection mode", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "Choose how this phone reaches the laptop.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            listOf("wifi" to "Wi-Fi", "usb" to "USB", "bt" to "Bluetooth").forEach { (mode, label) ->
                FilterChip(
                    selected = connectionMode == mode,
                    onClick = { onConnectionModeChange(mode) },
                    label = { Text(label) },
                )
            }
        }
        Text(
            text = when (connectionMode) {
                "usb" -> "USB: run `adb reverse tcp:8420 tcp:8420` on the laptop, then connect to 127.0.0.1."
                "bt" -> "Bluetooth: pair and enable Bluetooth PAN (tethering) on the laptop, then enter its IP."
                else -> "Wi-Fi: both devices on the same network."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Operating mode", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "AI = MAYA works alone. REMOTE = you control the laptop. HYBRID = both, you always win.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            OperatingMode.values().forEach { mode ->
                FilterChip(
                    selected = operatingMode == mode,
                    onClick = { onOperatingModeChange(mode) },
                    label = { Text(mode.name) },
                )
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Phone control", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            FilterChip(selected = controlEnabled, onClick = { onControlEnabledChange(true) }, label = { Text("On") })
            FilterChip(selected = !controlEnabled, onClick = { onControlEnabledChange(false) }, label = { Text("Off") })
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            FilterChip(selected = requireUnlock, onClick = { onRequireUnlockChange(true) }, label = { Text("Require unlock") })
            FilterChip(selected = !requireUnlock, onClick = { onRequireUnlockChange(false) }, label = { Text("No unlock") })
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Phone remote (laptop → phone)", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "Allow your laptop to view the screen, inject input, and transfer files over LAN.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            FilterChip(
                selected = phoneRemoteEnabled,
                onClick = { onPhoneRemoteChange(true) },
                label = { Text("Allow laptop to control this phone") },
            )
        }

        Text(
            text = stringResource(R.string.screen_share_title),
            style = MaterialTheme.typography.titleSmall,
            modifier = Modifier.padding(top = 16.dp),
        )
        Text(
            text = stringResource(R.string.screen_share_body),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        if (screenSharing) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(top = 8.dp),
            ) {
                FilterChip(
                    selected = true,
                    onClick = {},
                    label = { Text(stringResource(R.string.screen_share_on)) },
                )
                OutlinedButton(onClick = onStopScreenShare) {
                    Text(stringResource(R.string.screen_share_stop))
                }
            }
        } else {
            OutlinedButton(
                enabled = projectionManager != null,
                onClick = {
                    val intent = projectionManager?.createScreenCaptureIntent() ?: return@OutlinedButton
                    screenCaptureLauncher.launch(intent)
                },
                modifier = Modifier.padding(top = 8.dp),
            ) {
                Text(stringResource(R.string.screen_share_start))
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Cloud AI (Gemini)", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "When laptop and phone model are both offline, Maya can use Google Gemini. " +
                "Your messages go to Google's servers — only prompts, no local files. " +
                "Get a free key at aistudio.google.com/app/apikey.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        var geminiKey by remember { mutableStateOf(geminiApiKey) }
        LaunchedEffect(geminiApiKey) { geminiKey = geminiApiKey }
        OutlinedTextField(
            value = geminiKey,
            onValueChange = { geminiKey = it; onGeminiKeyChange(it) },
            label = { Text("Gemini API key") },
            placeholder = { Text("AIza...") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        )
        if (geminiKey.isNotBlank()) {
            Text(
                text = "Key saved · ${geminiKey.take(4)}...${geminiKey.takeLast(4)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 2.dp),
            )
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Wake listener", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "Clap twice, or say \"Maya\" three times within 10 seconds. Name detection runs fully offline " +
                "and needs a one-time Vosk model import.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            FilterChip(selected = wakeRunning, onClick = { onWakeToggle(true) }, label = { Text("On") }, modifier = Modifier.testTag("wake_on"))
            FilterChip(selected = !wakeRunning, onClick = { onWakeToggle(false) }, label = { Text("Off") })
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            FilterChip(
                selected = wakeNameEnabled,
                enabled = voskStatus.installed,
                onClick = { onWakeNameChange(!wakeNameEnabled) },
                label = { Text("Name \"Maya\"") },
            )
        }
        Text(
            text = if (voskStatus.installed) {
                "Wake-word model ready (${voskStatus.sizeText})."
            } else {
                "No wake-word model yet. Download vosk-model-small-en-us-0.15.zip (about 40 MB) " +
                    "from alphacephei.com/vosk/models and import the zip below."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        if (voskBusy) {
            LinearProgressIndicator(
                progress = { ((voskProgress ?: 0).coerceIn(0, 100)) / 100f },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )
            Text(
                text = voskProgress?.let { "Importing... $it%" } ?: "Working...",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            OutlinedButton(
                onClick = {
                    voskPicker.launch(
                        arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream"),
                    )
                },
            ) {
                Text(if (voskStatus.installed) "Replace model (.zip)" else "Import model (.zip)")
            }
            if (voskStatus.installed) {
                TextButton(onClick = { confirmDeleteVosk = true }) { Text("Remove") }
            }
        }
        voskMessage?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        Text(
            text = "The Vosk model and microphone audio stay on this phone.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "Phone model (Phase 9)", style = MaterialTheme.typography.titleMedium)
        Text(
            text = "Offline fallback: tamil-lm-2b Instruct Q4_K_M (about 1.3 GB, Tamil/Tanglish). " +
                "Import a .gguf file; it stays in private app storage.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )
        val model = state.modelStatus
        Text(
            text = when {
                !model.installed ->
                    "Not installed. Import a GGUF file to chat without the laptop."
                !model.valid ->
                    "Invalid model file: ${model.error ?: "not a GGUF model"}"
                model.loaded ->
                    "${model.fileName} · ${model.sizeText} · loaded in memory"
                else ->
                    "${model.fileName} · ${model.sizeText} · ready"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (model.installed && !model.valid) {
                MaterialTheme.colorScheme.error
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            },
            modifier = Modifier.padding(top = 8.dp),
        )
        if (state.modelBusy) {
            LinearProgressIndicator(
                progress = {
                    (state.modelProgress ?: 0).coerceIn(0, 100) / 100f
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
            )
            Text(
                text = state.modelProgress?.let { "Importing… $it%" } ?: "Working…",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
            Button(
                enabled = !state.modelBusy,
                onClick = {
                    modelPicker.launch(
                        arrayOf("application/octet-stream", "application/gguf", "*/*"),
                    )
                },
            ) {
                Text("Import GGUF")
            }
            if (model.valid) {
                OutlinedButton(
                    enabled = !state.modelBusy,
                    onClick = onUnloadModel,
                ) {
                    Text("Unload")
                }
                TextButton(
                    enabled = !state.modelBusy,
                    onClick = { confirmDeleteModel = true },
                ) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            }
        }
        state.modelMessage?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = if (it.startsWith("Import failed") || it.startsWith("Could not")) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.primary
                },
                modifier = Modifier.padding(top = 8.dp),
            )
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = stringResource(R.string.settings_privacy), style = MaterialTheme.typography.titleMedium)
        Text(
            text = stringResource(R.string.settings_privacy_body),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 12.dp)) {
            Button(onClick = { exportLauncher.launch("maya-export.json") }) { Text("Export data") }
            OutlinedButton(onClick = { confirmDelete = true }) { Text("Delete all data") }
        }
        state.exportStatus?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 8.dp)) }
        state.deleteStatus?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp)) }

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(text = "About", style = MaterialTheme.typography.titleMedium)
        Text(text = "Maya AI ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 8.dp))
        Text(
            text = "Local-first assistant. No cloud, no telemetry. Licenses: AndroidX, Compose, Room, OkHttp, Retrofit, ZXing, Kotlinx Serialization.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )

        HorizontalDivider(modifier = Modifier.padding(vertical = 24.dp))

        Text(
            text = "${stringResource(R.string.settings_version)} ${BuildConfig.VERSION_NAME}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Delete all local data?") },
            text = { Text("This removes chats, audit log, notifications and pairing tokens from this phone. This cannot be undone.") },
            confirmButton = {
                TextButton(onClick = { confirmDelete = false; onDeleteAll() }) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
    }

    if (confirmDeleteModel) {
        AlertDialog(
            onDismissRequest = { confirmDeleteModel = false },
            title = { Text("Delete phone model?") },
            text = { Text("This removes the GGUF file from this phone. You can import it again later.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDeleteModel = false
                        onDeleteModel()
                    },
                ) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmDeleteModel = false }) { Text("Cancel") }
            },
        )
    }

    if (confirmDeleteVosk) {
        AlertDialog(
            onDismissRequest = { confirmDeleteVosk = false },
            title = { Text("Remove wake-word model?") },
            text = {
                Text(
                    "Name detection will turn off and the Vosk files are removed from this phone. " +
                        "Clap detection keeps working.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDeleteVosk = false
                        onDeleteVosk()
                    },
                ) {
                    Text("Remove", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmDeleteVosk = false }) { Text("Cancel") }
            },
        )
    }
}

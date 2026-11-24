package com.devaraj.maya.ui.laptop

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.devaraj.maya.R
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.domain.model.Device
import com.devaraj.maya.domain.model.OperatingMode
import com.devaraj.maya.ui.connection.reasonText
import com.devaraj.maya.ui.theme.MayaSuccess
import com.devaraj.maya.ui.theme.MayaWarning

@Composable
fun LaptopScreen(
    connectionState: ConnectionState,
    devices: List<Device>,
    onPair: () -> Unit,
    onConnect: () -> Unit,
    onForget: () -> Unit,
    onToggleAutoConnect: (Boolean) -> Unit,
    controlState: LaptopControlUiState? = null,
    operatingMode: OperatingMode = OperatingMode.AI,
    remoteViewModel: RemoteViewModel? = null,
    onControlAppNameChange: (String) -> Unit = {},
    onControlVolumeChange: (Int) -> Unit = {},
    onControlClipboardChange: (String) -> Unit = {},
    onControlOpenApp: () -> Unit = {},
    onControlLock: () -> Unit = {},
    onControlSleep: () -> Unit = {},
    onControlMute: () -> Unit = {},
    onControlUnmute: () -> Unit = {},
    onControlVolume: () -> Unit = {},
    onControlScreenshot: () -> Unit = {},
    onControlMediaPlay: () -> Unit = {},
    onControlMediaPause: () -> Unit = {},
    onControlMediaNext: () -> Unit = {},
    onControlMediaPrev: () -> Unit = {},
    onControlClipboardSet: () -> Unit = {},
    onControlNotify: () -> Unit = {},
    onControlConfirm: () -> Unit = {},
    onControlCancel: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val device = devices.firstOrNull()
    var confirmForget by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Text(
            text = stringResource(R.string.nav_laptop),
            style = MaterialTheme.typography.headlineMedium,
        )

        if (device == null) {
            Text(
                text = stringResource(R.string.laptop_not_paired_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 20.dp),
            )
            Text(
                text = stringResource(R.string.laptop_not_paired_body),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 8.dp),
            )
        } else {
            StatusCard(connectionState = connectionState, device = device)

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 20.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = stringResource(R.string.laptop_auto_connect),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = stringResource(R.string.laptop_auto_connect_hint),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(
                    checked = device.autoConnect,
                    onCheckedChange = onToggleAutoConnect,
                )
            }
        }

        if (device != null && connectionState !is ConnectionState.Connected) {
            Button(
                onClick = onConnect,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 20.dp),
            ) {
                Text(
                    text = stringResource(
                        if (connectionState is ConnectionState.Failed) {
                            R.string.laptop_retry
                        } else {
                            R.string.laptop_connect
                        },
                    ),
                )
            }
        }

        if (device == null) {
            Button(
                onClick = onPair,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 20.dp),
            ) {
                Text(text = stringResource(R.string.laptop_pair_button))
            }
        } else {
            OutlinedButton(
                onClick = onPair,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp),
            ) {
                Text(text = stringResource(R.string.laptop_pair_button))
            }

            if (controlState != null && remoteViewModel == null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 20.dp))
                LaptopControlSection(
                    state = controlState,
                    enabled = connectionState is ConnectionState.Connected,
                    onAppNameChange = onControlAppNameChange,
                    onVolumeChange = onControlVolumeChange,
                    onClipboardChange = onControlClipboardChange,
                    onOpenApp = onControlOpenApp,
                    onLock = onControlLock,
                    onSleep = onControlSleep,
                    onMute = onControlMute,
                    onUnmute = onControlUnmute,
                    onVolume = onControlVolume,
                    onScreenshot = onControlScreenshot,
                    onMediaPlay = onControlMediaPlay,
                    onMediaPause = onControlMediaPause,
                    onMediaNext = onControlMediaNext,
                    onMediaPrev = onControlMediaPrev,
                    onClipboardSet = onControlClipboardSet,
                    onNotify = onControlNotify,
                    onConfirm = onControlConfirm,
                    onCancel = onControlCancel,
                )
            }

            if (remoteViewModel != null) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 20.dp))
                RemoteSection(
                    vm = remoteViewModel,
                    operatingMode = operatingMode,
                    connectionEnabled = connectionState is ConnectionState.Connected,
                    actionsContent = {
                        if (controlState != null) {
                            LaptopControlSection(
                                state = controlState,
                                enabled = connectionState is ConnectionState.Connected,
                                onAppNameChange = onControlAppNameChange,
                                onVolumeChange = onControlVolumeChange,
                                onClipboardChange = onControlClipboardChange,
                                onOpenApp = onControlOpenApp,
                                onLock = onControlLock,
                                onSleep = onControlSleep,
                                onMute = onControlMute,
                                onUnmute = onControlUnmute,
                                onVolume = onControlVolume,
                                onScreenshot = onControlScreenshot,
                                onMediaPlay = onControlMediaPlay,
                                onMediaPause = onControlMediaPause,
                                onMediaNext = onControlMediaNext,
                                onMediaPrev = onControlMediaPrev,
                                onClipboardSet = onControlClipboardSet,
                                onNotify = onControlNotify,
                                onConfirm = onControlConfirm,
                                onCancel = onControlCancel,
                            )
                        }
                    },
                )
            }

            HorizontalDivider(modifier = Modifier.padding(vertical = 20.dp))

            TextButton(
                onClick = { confirmForget = true },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    text = stringResource(R.string.laptop_forget),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }

    if (confirmForget) {
        AlertDialog(
            onDismissRequest = { confirmForget = false },
            title = { Text(text = stringResource(R.string.laptop_forget_title)) },
            text = { Text(text = stringResource(R.string.laptop_forget_body)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmForget = false
                        onForget()
                    },
                ) {
                    Text(
                        text = stringResource(R.string.laptop_forget_confirm),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmForget = false }) {
                    Text(text = stringResource(R.string.laptop_cancel))
                }
            },
        )
    }
}

@Composable
private fun StatusCard(connectionState: ConnectionState, device: Device) {
    val dotColor = when (connectionState) {
        is ConnectionState.Connected -> MayaSuccess
        is ConnectionState.Checking -> MayaWarning
        is ConnectionState.Failed -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.medium,
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .background(color = dotColor, shape = CircleShape),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = when (connectionState) {
                        is ConnectionState.Connected ->
                            stringResource(R.string.laptop_connected_to, device.name)
                        is ConnectionState.Checking -> stringResource(R.string.connection_checking)
                        is ConnectionState.NeedsPairing -> stringResource(R.string.error_pair_again)
                        is ConnectionState.Failed -> reasonText(connectionState.reason)
                        else -> stringResource(R.string.laptop_never_connected)
                    },
                    style = MaterialTheme.typography.titleMedium,
                )
                if (connectionState is ConnectionState.Checking) {
                    Spacer(modifier = Modifier.width(8.dp))
                    CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                }
            }

            Text(
                text = "${device.host}:${device.port}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 6.dp),
            )

            if (connectionState is ConnectionState.Connected) {
                val health = connectionState.health
                DetailRow(
                    label = stringResource(R.string.laptop_model),
                    value = health.model ?: "—",
                )
                DetailRow(
                    label = stringResource(R.string.laptop_engine),
                    value = health.engine ?: "—",
                )
                DetailRow(
                    label = "OS",
                    value = when (health.platform) {
                        "win32", "windows" -> "Windows"
                        "linux" -> "Linux / Fedora"
                        "darwin" -> "macOS"
                        else -> health.platform
                    },
                )
                if (health.capabilities.isNotEmpty()) {
                    DetailRow(
                        label = "Features",
                        value = health.capabilities.joinToString(", "),
                    )
                }
            }

            if (connectionState is ConnectionState.Failed &&
                connectionState.reason == com.devaraj.maya.data.remote.MayaErrorReason.NON_LOCAL_HOST
            ) {
                Text(
                    text = stringResource(R.string.pairing_find_hint),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        horizontalArrangement = Arrangement.SpaceBetween,
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(text = value, style = MaterialTheme.typography.bodyMedium)
    }
}

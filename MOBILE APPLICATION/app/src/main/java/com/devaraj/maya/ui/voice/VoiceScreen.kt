package com.devaraj.maya.ui.voice

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.devaraj.maya.R

@Composable
fun VoiceScreen(
    state: VoiceUiState,
    onStartListening: () -> Unit,
    onStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var hasMicPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        hasMicPermission = granted
        if (granted) onStartListening()
    }

    val scroll = rememberScrollState()
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(R.string.voice_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Spacer(modifier = Modifier.height(16.dp))

        if (!hasMicPermission) {
            PermissionCard(
                onGrant = { permissionLauncher.launch(Manifest.permission.RECORD_AUDIO) },
                onOpenSettings = {
                    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = Uri.fromParts("package", context.packageName, null)
                    }
                    context.startActivity(intent)
                },
            )
        } else {
            VoiceOrb(phase = state.phase)

            Spacer(modifier = Modifier.height(12.dp))
            Text(
                text = phaseLabel(state.phase),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = stringResource(R.string.voice_hint_idle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 4.dp),
            )

            Spacer(modifier = Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (state.phase == VoicePhase.Listening || state.phase == VoicePhase.Thinking || state.phase == VoicePhase.Speaking) {
                    FilledTonalButton(onClick = onStop) {
                        Icon(Icons.Filled.Stop, contentDescription = null)
                        Spacer(modifier = Modifier.size(8.dp))
                        Text(stringResource(R.string.voice_stop))
                    }
                } else {
                    Button(onClick = {
                        if (hasMicPermission) onStartListening()
                        else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }) {
                        Icon(Icons.Filled.Mic, contentDescription = null)
                        Spacer(modifier = Modifier.size(8.dp))
                        Text(stringResource(R.string.voice_tap_to_speak))
                    }
                }
            }

            state.errorResId?.let { resId ->
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = stringResource(resId),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Center,
                )
            }

            if (state.transcript.isNotBlank()) {
                Spacer(modifier = Modifier.height(20.dp))
                InfoCard(label = stringResource(R.string.voice_transcript_label), body = state.transcript)
            }
            if (state.reply.isNotBlank()) {
                Spacer(modifier = Modifier.height(12.dp))
                InfoCard(label = stringResource(R.string.voice_reply_label), body = state.reply)
            }
            if (state.recent.isNotEmpty()) {
                Spacer(modifier = Modifier.height(20.dp))
                Text(
                    text = stringResource(R.string.voice_recent),
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.fillMaxWidth(),
                )
                state.recent.take(10).forEach { item ->
                    Text(
                        text = "• $item",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 6.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun VoiceOrb(phase: VoicePhase) {
    val active = phase == VoicePhase.Listening || phase == VoicePhase.Speaking || phase == VoicePhase.Thinking
    val transition = rememberInfiniteTransition(label = "voice-orb")
    val pulse by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (active) 1.18f else 1.03f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (active) 700 else 1400, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulse",
    )
    val ring by transition.animateFloat(
        initialValue = 0.9f,
        targetValue = if (active) 1.35f else 1.05f,
        animationSpec = infiniteRepeatable(
            animation = tween(if (active) 900 else 1600, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "ring",
    )
    val color = when (phase) {
        VoicePhase.Listening -> MaterialTheme.colorScheme.primary
        VoicePhase.Speaking -> MaterialTheme.colorScheme.secondary
        VoicePhase.Thinking -> MaterialTheme.colorScheme.tertiary
        VoicePhase.Error -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.primary.copy(alpha = 0.7f)
    }

    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(180.dp)) {
        Box(
            modifier = Modifier
                .size(150.dp)
                .scale(ring)
                .background(color.copy(alpha = 0.15f), CircleShape),
        )
        Box(
            modifier = Modifier
                .size(110.dp)
                .scale(pulse)
                .background(color.copy(alpha = 0.9f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (phase == VoicePhase.Speaking) Icons.Filled.Stop else Icons.Filled.Mic,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier.size(40.dp),
            )
        }
    }
}

@Composable
private fun PermissionCard(onGrant: () -> Unit, onOpenSettings: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = stringResource(R.string.voice_mic_permission_title),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = stringResource(R.string.voice_mic_permission_body),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Button(onClick = onGrant) { Text(stringResource(R.string.voice_mic_permission_grant)) }
            OutlinedButton(onClick = onOpenSettings) { Text(stringResource(R.string.voice_mic_permission_settings)) }
        }
    }
}

@Composable
private fun InfoCard(label: String, body: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = body, style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun phaseLabel(phase: VoicePhase): String = when (phase) {
    VoicePhase.Idle -> stringResource(R.string.voice_tap_to_speak)
    VoicePhase.Listening -> stringResource(R.string.voice_listening)
    VoicePhase.Transcribing -> stringResource(R.string.voice_transcribing)
    VoicePhase.Thinking -> stringResource(R.string.voice_thinking)
    VoicePhase.Speaking -> stringResource(R.string.voice_speaking)
    VoicePhase.Error -> stringResource(R.string.voice_error_generic)
}

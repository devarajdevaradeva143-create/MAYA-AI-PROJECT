package com.devaraj.maya.ui.monitor

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import com.devaraj.maya.data.remote.PcStatusDto

@Composable
fun MonitorScreen(
    state: MonitorUiState,
    onStart: () -> Unit,
    onStop: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> onStart()
                Lifecycle.Event.ON_STOP -> onStop()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        // The composable is usually created while the activity is already
        // RESUMED, so the observer never receives a past ON_START event.
        // Start polling immediately in that case.
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            onStart()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            onStop()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = "Monitor", style = MaterialTheme.typography.headlineMedium)

        Text(text = "Laptop", style = MaterialTheme.typography.titleLarge)
        if (state.laptopError != null) {
            Text(
                text = state.laptopError,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        LaptopStatusCard(state.laptop, state.laptopError, state.cpuHistory, state.ramHistory)

        Spacer(modifier = Modifier.height(8.dp))
        Text(text = "Phone", style = MaterialTheme.typography.titleLarge)
        PhoneStatsCard(state.phone)

        Spacer(modifier = Modifier.height(8.dp))
        Text(text = "Events", style = MaterialTheme.typography.titleLarge)
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = if (state.eventsConnected) "Events stream: live" else "Events stream: offline (polling)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (state.events.isEmpty()) {
                    Text(text = "No events yet.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    state.events.take(15).forEach { e ->
                        Text(text = e, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

@Composable
private fun LaptopStatusCard(
    status: PcStatusDto?,
    laptopError: String?,
    cpuHistory: List<Float>,
    ramHistory: List<Float>,
) {
    if (status == null) {
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            if (laptopError == null) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text(text = "Loading laptop status…", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                Text(
                    text = laptopError,
                    modifier = Modifier.padding(16.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        return
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            MetricRow("CPU", status.cpu?.percent?.let { "${it.toInt()}%" } ?: "—", (status.cpu?.percent?.toFloat() ?: 0f) / 100f)
            Sparkline(cpuHistory, color = MaterialTheme.colorScheme.primary)
            MetricRow("RAM", status.ram?.percent?.let { "${it.toInt()}%" } ?: "—", (status.ram?.percent?.toFloat() ?: 0f) / 100f)
            Sparkline(ramHistory, color = MaterialTheme.colorScheme.secondary)
            Text("GPU: ${status.gpu?.name ?: "—"} ${status.gpu?.percent?.let { "(${it.toInt()}%)" } ?: ""}")
            Text("NPU: ${status.npu?.name ?: "—"} ${status.npu?.tops?.let { "(${it.toInt()} TOPS)" } ?: ""} ${status.npu?.percent?.let { "(${it.toInt()}%)" } ?: ""}")
            Text("Battery: ${status.battery?.percent?.let { "${it.toInt()}%" } ?: "—"} ${if (status.battery?.plugged == true) "(plugged in)" else ""}")
            Text("Temp: ${status.temps?.cpuC?.let { "${it}°C" } ?: "—"}")
            if (status.disks.isNotEmpty()) {
                status.disks.take(3).forEach { d ->
                    MetricRow("Disk ${d.mount ?: ""}", d.percent?.let { "${it.toInt()}%" } ?: "—", (d.percent?.toFloat() ?: 0f) / 100f)
                }
            }
            Text("Uptime: ${status.uptimeS?.let { "${it / 3600}h ${(it % 3600) / 60}m" } ?: "—"}")
        }
    }
}

@Composable
private fun Sparkline(values: List<Float>, color: Color, modifier: Modifier = Modifier) {
    if (values.size < 2) return
    Canvas(modifier = modifier.fillMaxWidth().height(28.dp)) {
        val min = values.minOrNull() ?: 0f
        val max = values.maxOrNull() ?: 100f
        val range = (max - min).coerceAtLeast(1f)
        val stepX = size.width / (values.size - 1).coerceAtLeast(1)
        val path = Path()
        values.forEachIndexed { index, v ->
            val x = index * stepX
            val y = size.height - ((v - min) / range) * size.height
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color, style = Stroke(width = 3f, cap = StrokeCap.Round))
    }
}

@Composable
private fun PhoneStatsCard(phone: PhoneStats) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            MetricRow("Battery", phone.batteryPercent?.let { "$it%" } ?: "—", (phone.batteryPercent ?: 0) / 100f)
            MetricRow("Storage used", phone.storageUsedPercent?.let { "$it%" } ?: "—", (phone.storageUsedPercent ?: 0) / 100f)
            MetricRow("RAM used", phone.ramUsedPercent?.let { "$it%" } ?: "—", (phone.ramUsedPercent ?: 0) / 100f)
            Text("Uptime: ${phone.uptimeHours?.let { "${it}h" } ?: "—"}")
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String, progress: Float) {
    Column {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(text = label, style = MaterialTheme.typography.bodyMedium)
            Text(text = value, style = MaterialTheme.typography.bodyMedium)
        }
        LinearProgressIndicator(
            progress = { progress.coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        )
    }
}

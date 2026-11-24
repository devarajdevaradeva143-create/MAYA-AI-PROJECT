package com.devaraj.maya.ui.phone

import androidx.core.net.toUri

import android.Manifest
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.devaraj.maya.R
import com.devaraj.maya.data.local.entity.AuditEntity
import com.devaraj.maya.data.local.entity.NotificationEntity
import com.devaraj.maya.data.repo.AppEntry
import com.devaraj.maya.data.repo.CallEntry
import com.devaraj.maya.data.repo.SmsEntry
import com.devaraj.maya.service.MayaAccessibilityService
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun PhoneScreen(
    state: PhoneUiState,
    filteredApps: List<AppEntry>,
    onControlEnabledChange: (Boolean) -> Unit,
    onRequireUnlockChange: (Boolean) -> Unit,
    onTabSelect: (PhoneTab) -> Unit,
    onQueryChange: (String) -> Unit,
    onOpenApp: (AppEntry) -> Unit,
    onOpenAppInfo: (AppEntry) -> Unit,
    onRefreshMessages: () -> Unit,
    onRequestSms: (String, String) -> Unit,
    onConfirmSms: () -> Unit,
    onCancelSms: () -> Unit,
    onRequestCall: (String) -> Unit,
    onConfirmCall: () -> Unit,
    onCancelCall: () -> Unit,
    onRequestWhatsApp: (String, String) -> Unit,
    onConfirmWhatsApp: () -> Unit,
    onCancelWhatsApp: () -> Unit,
    onPermissionResult: (String, Boolean) -> Unit,
    onPermissionRequestConsumed: () -> Unit,
    onReadScreen: () -> Unit,
    onScreenBack: () -> Unit,
    onScreenHome: () -> Unit,
    onClickOnScreen: (String) -> Unit,
    onClearScreenText: () -> Unit,
    onFolderPicked: (Uri) -> Unit,
    onFolderRemoved: (String) -> Unit,
    onRefreshPermissionStatus: () -> Unit,
    onConsumeMessage: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }

    var smsTo by rememberSaveable { mutableStateOf("") }
    var smsBody by rememberSaveable { mutableStateOf("") }
    var callNumber by rememberSaveable { mutableStateOf("") }
    var waTo by rememberSaveable { mutableStateOf("") }
    var waText by rememberSaveable { mutableStateOf("") }
    var clickText by rememberSaveable { mutableStateOf("") }
    var pendingPermission by remember { mutableStateOf<String?>(null) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        pendingPermission?.let { onPermissionResult(it, granted) }
        pendingPermission = null
    }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        onPermissionResult(Manifest.permission.POST_NOTIFICATIONS, granted)
    }
    val folderPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree(),
    ) { uri -> if (uri != null) onFolderPicked(uri) }

    LaunchedEffect(Unit) { onRefreshPermissionStatus() }

    LaunchedEffect(state.permissionToRequest) {
        val permission = state.permissionToRequest
        if (permission != null) {
            pendingPermission = permission
            permissionLauncher.launch(permission)
            onPermissionRequestConsumed()
        }
    }

    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            onConsumeMessage()
        }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    text = stringResource(R.string.phone_control_title),
                    style = MaterialTheme.typography.headlineMedium,
                )
            }

            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = stringResource(R.string.phone_master_switch),
                                    style = MaterialTheme.typography.titleMedium,
                                )
                                Text(
                                    text = stringResource(R.string.phone_master_switch_hint),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            Switch(checked = state.controlEnabled, onCheckedChange = onControlEnabledChange)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = stringResource(R.string.phone_require_unlock),
                                    style = MaterialTheme.typography.bodyLarge,
                                )
                                Text(
                                    text = stringResource(R.string.phone_require_unlock_hint),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            Switch(checked = state.requireUnlock, onCheckedChange = onRequireUnlockChange)
                        }
                    }
                }
            }

            if (!state.controlEnabled) {
                item {
                    Text(
                        text = stringResource(R.string.phone_control_off_banner),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            item { Text(text = stringResource(R.string.phone_permissions_title), style = MaterialTheme.typography.titleMedium) }
            item {
                OutlinedButton(
                    onClick = { notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Request notification permission (for control service)") }
            }
            item { PermissionDashboard(context = context, state = state) }
            item {
                Text(
                    text = stringResource(R.string.phone_restricted_settings_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    PhoneTab.values().take(3).forEach { tab ->
                        FilterChip(
                            selected = state.selectedTab == tab,
                            onClick = { onTabSelect(tab) },
                            label = { Text(tabLabel(tab)) },
                        )
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    PhoneTab.values().drop(3).forEach { tab ->
                        FilterChip(
                            selected = state.selectedTab == tab,
                            onClick = { onTabSelect(tab) },
                            label = { Text(tabLabel(tab)) },
                        )
                    }
                }
            }

            when (state.selectedTab) {
                PhoneTab.APPS -> {
                    item {
                        OutlinedTextField(
                            value = state.query,
                            onValueChange = onQueryChange,
                            label = { Text(stringResource(R.string.phone_apps_search)) },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    if (filteredApps.isEmpty()) {
                        item {
                            Text(
                                text = stringResource(R.string.phone_apps_empty),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        items(filteredApps, key = { it.packageName }) { entry ->
                            AppRow(
                                entry = entry,
                                enabled = state.controlEnabled,
                                onOpen = { onOpenApp(entry) },
                                onInfo = { onOpenAppInfo(entry) },
                            )
                        }
                    }
                }

                PhoneTab.MESSAGES -> {
                    item {
                        MessagesSection(
                            state = state,
                            smsTo = smsTo,
                            smsBody = smsBody,
                            callNumber = callNumber,
                            onSmsToChange = { smsTo = it },
                            onSmsBodyChange = { smsBody = it },
                            onCallNumberChange = { callNumber = it },
                            onRequestSms = { onRequestSms(smsTo, smsBody) },
                            onRequestCall = onRequestCall,
                            onRefresh = onRefreshMessages,
                        )
                    }
                    item {
                        WhatsAppSection(
                            state = state,
                            waTo = waTo,
                            waText = waText,
                            onWaToChange = { waTo = it },
                            onWaTextChange = { waText = it },
                            onRequestWhatsApp = { onRequestWhatsApp(waTo, waText) },
                        )
                    }
                }

                PhoneTab.NOTIFICATIONS -> item { NotificationsSection(state.notifications) }

                PhoneTab.FILES -> {
                    item {
                        FilesSection(
                            state = state,
                            onPick = { folderPicker.launch(null) },
                            onRemove = onFolderRemoved,
                        )
                    }
                }

                PhoneTab.SCREEN -> {
                    item {
                        ScreenSection(
                            state = state,
                            clickText = clickText,
                            onTextChange = { clickText = it },
                            onRead = onReadScreen,
                            onBack = onScreenBack,
                            onHome = onScreenHome,
                            onClickByText = { onClickOnScreen(clickText) },
                            onClear = onClearScreenText,
                            onEnableAccessibility = { MayaAccessibilityService.openSettings(context) },
                        )
                    }
                }
            }

            item { HorizontalDivider() }
            item { Text(text = stringResource(R.string.phone_audit_title), style = MaterialTheme.typography.titleMedium) }
            if (state.audit.isEmpty()) {
                item {
                    Text(
                        text = stringResource(R.string.phone_audit_empty),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                items(state.audit, key = { it.id }) { entry -> AuditRow(entry) }
            }
        }
    }

    state.pendingSms?.let { pending ->
        AlertDialog(
            onDismissRequest = onCancelSms,
            title = { Text(stringResource(R.string.phone_confirm_sms_title)) },
            text = {
                Text(
                    stringResource(
                        R.string.phone_confirm_sms_body,
                        pending.address,
                        pending.body.take(160),
                    ),
                )
            },
            confirmButton = { TextButton(onClick = onConfirmSms) { Text(stringResource(R.string.phone_confirm_send)) } },
            dismissButton = { TextButton(onClick = onCancelSms) { Text(stringResource(R.string.laptop_cancel)) } },
        )
    }

    state.pendingCall?.let { pending ->
        AlertDialog(
            onDismissRequest = onCancelCall,
            title = { Text(stringResource(R.string.phone_confirm_call_title)) },
            text = { Text(stringResource(R.string.phone_confirm_call_body, pending.number)) },
            confirmButton = { TextButton(onClick = onConfirmCall) { Text(stringResource(R.string.phone_confirm_call)) } },
            dismissButton = { TextButton(onClick = onCancelCall) { Text(stringResource(R.string.laptop_cancel)) } },
        )
    }

    state.pendingWhatsApp?.let { pending ->
        AlertDialog(
            onDismissRequest = onCancelWhatsApp,
            title = { Text(stringResource(R.string.phone_whatsapp_section)) },
            text = { Text("Send to ${pending.number}:\n\n${pending.text.take(200)}") },
            confirmButton = { TextButton(onClick = onConfirmWhatsApp) { Text(stringResource(R.string.phone_whatsapp_send)) } },
            dismissButton = { TextButton(onClick = onCancelWhatsApp) { Text(stringResource(R.string.laptop_cancel)) } },
        )
    }
}

@Composable
private fun tabLabel(tab: PhoneTab): String = when (tab) {
    PhoneTab.APPS -> stringResource(R.string.phone_tab_apps)
    PhoneTab.MESSAGES -> stringResource(R.string.phone_tab_messages)
    PhoneTab.NOTIFICATIONS -> stringResource(R.string.phone_tab_notifications)
    PhoneTab.FILES -> stringResource(R.string.phone_tab_files)
    PhoneTab.SCREEN -> stringResource(R.string.phone_tab_screen)
}

@Composable
private fun PermissionDashboard(context: Context, state: PhoneUiState) {
    fun granted(permission: String): Boolean = ContextCompat.checkSelfPermission(
        context,
        permission,
    ) == android.content.pm.PackageManager.PERMISSION_GRANTED

    val appDetails = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
        data = Uri.fromParts("package", context.packageName, null)
    }
    val items = listOf(
        PermissionItem(
            stringResource(R.string.phone_permission_accessibility),
            if (state.accessibilityOn) stringResource(R.string.phone_status_granted) else stringResource(R.string.phone_status_not_granted),
            Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS),
        ),
        PermissionItem(
            stringResource(R.string.phone_permission_notifications),
            if (state.notificationsOn) stringResource(R.string.phone_status_granted) else stringResource(R.string.phone_status_not_granted),
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS),
        ),
        PermissionItem(
            stringResource(R.string.phone_permission_sms),
            if (granted(Manifest.permission.READ_SMS)) stringResource(R.string.phone_status_granted) else stringResource(R.string.phone_status_not_granted),
            appDetails,
        ),
        PermissionItem(
            stringResource(R.string.phone_permission_phone),
            if (granted(Manifest.permission.CALL_PHONE)) stringResource(R.string.phone_status_granted) else stringResource(R.string.phone_status_not_granted),
            appDetails,
        ),
        PermissionItem(
            stringResource(R.string.phone_permission_contacts),
            if (granted(Manifest.permission.READ_CONTACTS)) stringResource(R.string.phone_status_granted) else stringResource(R.string.phone_status_not_granted),
            appDetails,
        ),
        PermissionItem(stringResource(R.string.phone_permission_files), stringResource(R.string.phone_status_optional), appDetails),
        PermissionItem(stringResource(R.string.phone_permission_battery), stringResource(R.string.phone_status_optional), Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)),
        PermissionItem(stringResource(R.string.phone_permission_overlay), stringResource(R.string.phone_status_optional), Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION).apply { data = Uri.fromParts("package", context.packageName, null) }),
    )
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.forEach { item ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            runCatching {
                                context.startActivity(Intent(item.intent).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                            }
                        }
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(text = item.label, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            text = stringResource(R.string.phone_open_settings),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        text = item.status,
                        style = MaterialTheme.typography.bodySmall,
                        color = if (item.status == stringResource(R.string.phone_status_granted)) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                }
            }
        }
    }
}

private data class PermissionItem(val label: String, val status: String, val intent: Intent)

@Composable
private fun MessagesSection(
    state: PhoneUiState,
    smsTo: String,
    smsBody: String,
    callNumber: String,
    onSmsToChange: (String) -> Unit,
    onSmsBodyChange: (String) -> Unit,
    onCallNumberChange: (String) -> Unit,
    onRequestSms: () -> Unit,
    onRequestCall: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(stringResource(R.string.phone_sms_section), style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = smsTo,
            onValueChange = onSmsToChange,
            label = { Text(stringResource(R.string.phone_sms_to)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = smsBody,
            onValueChange = onSmsBodyChange,
            label = { Text(stringResource(R.string.phone_sms_body)) },
            minLines = 2,
            modifier = Modifier.fillMaxWidth(),
        )
        ButtonRow(
            primary = stringResource(R.string.phone_sms_send),
            secondary = stringResource(R.string.phone_refresh),
            enabled = state.controlEnabled,
            onPrimary = onRequestSms,
            onSecondary = onRefresh,
        )

        Text(stringResource(R.string.phone_calls_section), style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = callNumber,
            onValueChange = onCallNumberChange,
            label = { Text(stringResource(R.string.phone_call_number)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth(),
        )
        ButtonRow(
            primary = stringResource(R.string.phone_call_dial),
            secondary = null,
            enabled = state.controlEnabled,
            onPrimary = { onRequestCall(callNumber) },
            onSecondary = {},
        )

        if (state.callLog.isNotEmpty()) {
            Text(stringResource(R.string.phone_recent_calls), style = MaterialTheme.typography.titleSmall)
            state.callLog.take(10).forEach { call -> CallRow(call, state.controlEnabled, onRequestCall) }
        }

        Text(stringResource(R.string.phone_recent_sms), style = MaterialTheme.typography.titleSmall)
        if (state.sms.isEmpty()) {
            Text(stringResource(R.string.phone_sms_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            state.sms.take(20).forEach { sms -> SmsRow(sms) }
        }
    }
}

@Composable
private fun ButtonRow(
    primary: String,
    secondary: String?,
    enabled: Boolean,
    onPrimary: () -> Unit,
    onSecondary: () -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        androidx.compose.material3.Button(onClick = onPrimary, enabled = enabled) { Text(primary) }
        if (secondary != null) {
            OutlinedButton(onClick = onSecondary) { Text(secondary) }
        }
    }
}

@Composable
private fun SmsRow(sms: SmsEntry) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text("${if (sms.type == 2) "↑" else "↓"} ${sms.address}", style = MaterialTheme.typography.bodyMedium)
            Text(sms.body, style = MaterialTheme.typography.bodySmall)
            Text(formatTime(sms.date), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun CallRow(call: CallEntry, enabled: Boolean, onCall: (String) -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Row(modifier = Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(call.name ?: call.number, style = MaterialTheme.typography.bodyMedium)
                Text("${call.number} · ${formatTime(call.date)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            TextButton(onClick = { onCall(call.number) }, enabled = enabled) { Text(stringResource(R.string.phone_call_dial)) }
        }
    }
}

@Composable
private fun NotificationsSection(notifications: List<NotificationEntity>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.phone_notifications_captured), style = MaterialTheme.typography.titleMedium)
        if (notifications.isEmpty()) {
            Text(stringResource(R.string.phone_notifications_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            notifications.take(30).forEach { n ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("${n.packageName} · ${formatTime(n.postedAt)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        n.title?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                        n.body?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilesSection(
    state: PhoneUiState,
    onPick: () -> Unit,
    onRemove: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.phone_files_section), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.phone_files_hint), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        OutlinedButton(onClick = onPick, enabled = state.controlEnabled) { Text(stringResource(R.string.phone_files_pick)) }
        if (state.pickedFolders.isEmpty()) {
            Text(stringResource(R.string.phone_files_empty), color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            state.pickedFolders.forEach { uri ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Row(modifier = Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = runCatching { uri.toUri().lastPathSegment ?: uri }.getOrDefault(uri),
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f),
                        )
                        TextButton(onClick = { onRemove(uri) }) { Text(stringResource(R.string.phone_files_remove)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun ScreenSection(
    state: PhoneUiState,
    clickText: String,
    onTextChange: (String) -> Unit,
    onRead: () -> Unit,
    onBack: () -> Unit,
    onHome: () -> Unit,
    onClickByText: () -> Unit,
    onClear: () -> Unit,
    onEnableAccessibility: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.phone_screen_section), style = MaterialTheme.typography.titleMedium)
        Text(
            stringResource(
                if (state.accessibilityOn) R.string.phone_screen_access_on else R.string.phone_screen_access_off,
            ),
            style = MaterialTheme.typography.bodySmall,
            color = if (state.accessibilityOn) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        )
        if (!state.accessibilityOn) {
            OutlinedButton(onClick = onEnableAccessibility) { Text(stringResource(R.string.phone_open_settings)) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = onBack, enabled = state.controlEnabled && state.accessibilityOn) { Text(stringResource(R.string.phone_screen_back)) }
            OutlinedButton(onClick = onHome, enabled = state.controlEnabled && state.accessibilityOn) { Text(stringResource(R.string.phone_screen_home)) }
        }
        ButtonRow(
            primary = stringResource(R.string.phone_screen_read),
            secondary = stringResource(R.string.phone_refresh),
            enabled = state.controlEnabled && state.accessibilityOn,
            onPrimary = onRead,
            onSecondary = onClear,
        )
        OutlinedTextField(
            value = clickText,
            onValueChange = onTextChange,
            label = { Text(stringResource(R.string.phone_screen_click_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(onClick = onClickByText, enabled = state.controlEnabled && state.accessibilityOn && clickText.isNotBlank()) {
            Text(stringResource(R.string.phone_screen_click))
        }
        if (state.screenText.isNotBlank()) {
            Text(stringResource(R.string.phone_screen_result), style = MaterialTheme.typography.titleSmall)
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                Text(state.screenText, modifier = Modifier.padding(10.dp), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun AppRow(
    entry: AppEntry,
    enabled: Boolean,
    onOpen: () -> Unit,
    onInfo: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            Text(text = entry.label, style = MaterialTheme.typography.titleSmall)
            Text(
                text = entry.packageName,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onOpen, enabled = enabled) { Text(stringResource(R.string.phone_apps_open)) }
                TextButton(onClick = onInfo, enabled = enabled) { Text(stringResource(R.string.phone_apps_info)) }
            }
        }
    }
}

@Composable
private fun WhatsAppSection(
    state: PhoneUiState,
    waTo: String,
    waText: String,
    onWaToChange: (String) -> Unit,
    onWaTextChange: (String) -> Unit,
    onRequestWhatsApp: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.phone_whatsapp_section), style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = waTo,
            onValueChange = onWaToChange,
            label = { Text(stringResource(R.string.phone_whatsapp_to)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = waText,
            onValueChange = onWaTextChange,
            label = { Text(stringResource(R.string.phone_whatsapp_body)) },
            minLines = 2,
            modifier = Modifier.fillMaxWidth(),
        )
        ButtonRow(
            primary = stringResource(R.string.phone_whatsapp_send),
            secondary = null,
            enabled = state.controlEnabled,
            onPrimary = onRequestWhatsApp,
            onSecondary = {},
        )
        Text(
            stringResource(R.string.phone_whatsapp_notifications),
            style = MaterialTheme.typography.titleSmall,
        )
        val waNotifs = state.notifications.filter { it.packageName == "com.whatsapp" }
        if (waNotifs.isEmpty()) {
            Text("No WhatsApp notifications captured yet.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        } else {
            waNotifs.take(10).forEach { n ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
                    Column(modifier = Modifier.padding(8.dp)) {
                        n.title?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                        n.body?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                        Text(formatTime(n.postedAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun AuditRow(entry: AuditEntity) {
    val fmt = remember { SimpleDateFormat("MMM d, HH:mm", Locale.getDefault()) }
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(
            text = "${entry.action} — ${if (entry.allowed) stringResource(R.string.phone_audit_allowed) else stringResource(R.string.phone_audit_blocked)}",
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(
            text = "${entry.detail} · ${fmt.format(Date(entry.createdAt))}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun formatTime(ms: Long): String {
    val fmt = remember { SimpleDateFormat("MMM d, HH:mm", Locale.getDefault()) }
    return if (ms <= 0) "—" else fmt.format(Date(ms))
}

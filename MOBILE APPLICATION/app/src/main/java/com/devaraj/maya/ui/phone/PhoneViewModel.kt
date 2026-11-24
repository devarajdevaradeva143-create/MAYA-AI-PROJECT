package com.devaraj.maya.ui.phone

import androidx.core.net.toUri

import android.Manifest
import android.app.Application
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.R
import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.local.entity.NotificationEntity
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.repo.AppEntry
import com.devaraj.maya.data.repo.CallEntry
import com.devaraj.maya.data.repo.PhoneControlRepository
import com.devaraj.maya.data.repo.SmsEntry
import com.devaraj.maya.service.ControlForegroundService
import com.devaraj.maya.service.MayaAccessibilityService
import com.devaraj.maya.service.MayaNotificationListener
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

enum class PhoneTab { APPS, MESSAGES, NOTIFICATIONS, FILES, SCREEN }

data class PendingSms(val address: String, val body: String, val token: String)
data class PendingCall(val number: String, val token: String)
data class PendingWhatsApp(val number: String, val text: String, val token: String)

data class PhoneUiState(
    val controlEnabled: Boolean = false,
    val requireUnlock: Boolean = true,
    val selectedTab: PhoneTab = PhoneTab.APPS,
    val query: String = "",
    val apps: List<AppEntry> = emptyList(),
    val loadingApps: Boolean = false,
    val audit: List<com.devaraj.maya.data.local.entity.AuditEntity> = emptyList(),
    val sms: List<SmsEntry> = emptyList(),
    val callLog: List<CallEntry> = emptyList(),
    val notifications: List<NotificationEntity> = emptyList(),
    val screenText: String = "",
    val pendingSms: PendingSms? = null,
    val pendingCall: PendingCall? = null,
    val pendingWhatsApp: PendingWhatsApp? = null,
    val permissionToRequest: String? = null,
    val pickedFolders: Set<String> = emptySet(),
    val accessibilityOn: Boolean = false,
    val notificationsOn: Boolean = false,
    val message: String? = null,
)

class PhoneViewModel(
    private val app: Application,
    private val settingsStore: SettingsStore,
    db: MayaDatabase,
) : ViewModel() {

    private val repo = PhoneControlRepository(app, db)

    private val _state = MutableStateFlow(PhoneUiState())
    val state: StateFlow<PhoneUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            settingsStore.settings.collect { settings ->
                _state.update {
                    it.copy(
                        controlEnabled = settings.controlEnabled,
                        requireUnlock = settings.controlRequireUnlock,
                        pickedFolders = settings.pickedFolders,
                    )
                }
            }
        }
        viewModelScope.launch {
            repo.observeAudit(50).collect { entries -> _state.update { it.copy(audit = entries) } }
        }
        viewModelScope.launch {
            repo.observeNotifications(50).collect { entries -> _state.update { it.copy(notifications = entries) } }
        }
        refreshApps()
        refreshPermissionStatus()
        viewModelScope.launch { repo.pruneNotifications() }
    }

    private fun text(resId: Int): String = app.getString(resId)

    private fun banner(message: String) {
        _state.update { it.copy(message = message) }
    }

    private fun requireControl(action: String): Boolean {
        if (_state.value.controlEnabled) return true
        viewModelScope.launch { repo.log(action, text(R.string.phone_action_blocked), allowed = false) }
        banner(text(R.string.phone_action_blocked))
        return false
    }

    fun setControlEnabled(enabled: Boolean) {
        viewModelScope.launch {
            settingsStore.setControlEnabled(enabled)
            if (enabled) ControlForegroundService.start(app) else ControlForegroundService.stop(app)
            repo.log(
                action = "control.master_switch",
                detail = text(if (enabled) R.string.phone_log_enabled else R.string.phone_log_disabled),
                allowed = true,
            )
            refreshPermissionStatus()
        }
    }

    fun setRequireUnlock(required: Boolean) {
        viewModelScope.launch {
            settingsStore.setControlRequireUnlock(required)
            repo.log("control.require_unlock", required.toString(), allowed = true)
        }
    }

    fun refreshPermissionStatus() {
        _state.update {
            it.copy(
                accessibilityOn = MayaAccessibilityService.isEnabled(app),
                notificationsOn = MayaNotificationListener.isEnabled(app),
            )
        }
    }

    fun selectTab(tab: PhoneTab) {
        _state.update { it.copy(selectedTab = tab) }
        refreshPermissionStatus()
        if (tab == PhoneTab.MESSAGES) refreshMessages()
    }

    fun setQuery(query: String) {
        _state.update { it.copy(query = query) }
    }

    fun refreshApps() {
        viewModelScope.launch {
            _state.update { it.copy(loadingApps = true) }
            val apps = runCatching { repo.listLaunchableApps() }.getOrDefault(emptyList())
            _state.update { it.copy(apps = apps, loadingApps = false) }
        }
    }

    fun refreshMessages() {
        viewModelScope.launch {
            val sms = runCatching { repo.readSms() }.getOrDefault(emptyList())
            val calls = runCatching { repo.readCallLog() }.getOrDefault(emptyList())
            _state.update { it.copy(sms = sms, callLog = calls) }
        }
    }

    fun openApp(entry: AppEntry) {
        if (!requireControl("app.open")) return
        val ok = repo.launchApp(entry.packageName)
        viewModelScope.launch {
            repo.log("app.open", "${entry.label} (${entry.packageName})", allowed = ok)
        }
        if (!ok) banner(text(R.string.phone_action_failed))
    }

    fun openAppInfo(entry: AppEntry) {
        if (!requireControl("app.info")) return
        repo.openAppInfo(entry.packageName)
        viewModelScope.launch { repo.log("app.info", entry.packageName, allowed = true) }
    }

    // --- SMS with confirmation ---

    fun requestSendSms(address: String, body: String) {
        if (!requireControl("sms.send")) return
        val target = address.trim()
        val message = body.trim()
        if (target.isBlank() || message.isBlank()) {
            banner(text(R.string.phone_sms_fields_required))
            return
        }
        if (!repo.hasSmsSendPermission()) {
            _state.update { it.copy(permissionToRequest = Manifest.permission.SEND_SMS) }
            banner(text(R.string.phone_permission_needed))
            return
        }
        _state.update {
            it.copy(pendingSms = PendingSms(target, message, UUID.randomUUID().toString()))
        }
    }

    fun confirmSendSms() {
        val pending = _state.value.pendingSms ?: return
        if (!requireControl("sms.send")) return
        val ok = repo.sendSms(pending.address, pending.body)
        viewModelScope.launch {
            repo.log(
                "sms.send",
                "${text(R.string.phone_log_to)} ${pending.address.take(40)}",
                allowed = ok,
            )
        }
        _state.update { it.copy(pendingSms = null) }
        banner(text(if (ok) R.string.phone_sms_sent else R.string.phone_action_failed))
        if (ok) refreshMessages()
    }

    fun cancelSendSms() {
        viewModelScope.launch { repo.log("sms.send", text(R.string.phone_log_cancelled), allowed = false) }
        _state.update { it.copy(pendingSms = null) }
    }

    // --- Calls with confirmation ---

    fun requestCall(number: String) {
        if (!requireControl("call.dial")) return
        val target = number.trim()
        if (target.isBlank()) {
            banner(text(R.string.phone_call_number_required))
            return
        }
        if (!repo.hasCallPermission()) {
            _state.update { it.copy(permissionToRequest = Manifest.permission.CALL_PHONE) }
            banner(text(R.string.phone_permission_needed))
            return
        }
        _state.update { it.copy(pendingCall = PendingCall(target, UUID.randomUUID().toString())) }
    }

    fun confirmCall() {
        val pending = _state.value.pendingCall ?: return
        if (!requireControl("call.dial")) return
        val ok = repo.dial(pending.number)
        viewModelScope.launch {
            repo.log("call.dial", "${text(R.string.phone_log_to)} ${pending.number.take(40)}", allowed = ok)
        }
        _state.update { it.copy(pendingCall = null) }
        if (!ok) banner(text(R.string.phone_action_failed))
    }

    fun cancelCall() {
        viewModelScope.launch { repo.log("call.dial", text(R.string.phone_log_cancelled), allowed = false) }
        _state.update { it.copy(pendingCall = null) }
    }

    // --- WhatsApp with confirmation ---

    fun requestSendWhatsApp(number: String, text: String) {
        if (!requireControl("whatsapp.send")) return
        val target = number.trim()
        val message = text.trim()
        if (target.isBlank() || message.isBlank()) {
            banner(text(R.string.phone_whatsapp_fields_required))
            return
        }
        if (!repo.hasWhatsApp()) {
            banner(text(R.string.phone_whatsapp_not_installed))
            return
        }
        _state.update {
            it.copy(pendingWhatsApp = PendingWhatsApp(target, message, java.util.UUID.randomUUID().toString()))
        }
    }

    fun confirmSendWhatsApp() {
        val pending = _state.value.pendingWhatsApp ?: return
        if (!requireControl("whatsapp.send")) return
        val ok = repo.sendWhatsApp(pending.number, pending.text)
        viewModelScope.launch {
            repo.log("whatsapp.send", "${text(R.string.phone_log_to)} ${pending.number.take(40)}", allowed = ok)
        }
        _state.update { it.copy(pendingWhatsApp = null) }
        banner(text(if (ok) R.string.phone_whatsapp_opened else R.string.phone_action_failed))
    }

    fun cancelSendWhatsApp() {
        viewModelScope.launch { repo.log("whatsapp.send", text(R.string.phone_log_cancelled), allowed = false) }
        _state.update { it.copy(pendingWhatsApp = null) }
    }

    // --- Screen actions (Accessibility) ---

    private fun requireAccessibility(action: String): Boolean {
        if (!requireControl(action)) return false
        if (!MayaAccessibilityService.isEnabled(app) || MayaAccessibilityService.instance == null) {
            banner(text(R.string.phone_accessibility_needed))
            return false
        }
        return true
    }

    fun readScreen() {
        if (!requireAccessibility("screen.read")) return
        val value = runCatching { MayaAccessibilityService.instance?.readVisibleText().orEmpty() }
            .getOrDefault("")
        _state.update { it.copy(screenText = value) }
        viewModelScope.launch { repo.log("screen.read", "${value.length} chars", allowed = true) }
    }

    fun screenBack() {
        if (!requireAccessibility("screen.back")) return
        MayaAccessibilityService.instance?.goBack()
        viewModelScope.launch { repo.log("screen.back", "", allowed = true) }
    }

    fun screenHome() {
        if (!requireAccessibility("screen.home")) return
        MayaAccessibilityService.instance?.goHome()
        viewModelScope.launch { repo.log("screen.home", "", allowed = true) }
    }

    fun clickOnScreen(text: String) {
        if (!requireAccessibility("screen.click")) return
        val ok = MayaAccessibilityService.instance?.clickByText(text) == true
        viewModelScope.launch { repo.log("screen.click", text.take(120), allowed = ok) }
        if (!ok) banner(app.getString(R.string.phone_screen_click_not_found, text.take(40)))
    }

    // --- SAF files ---

    fun onFolderPicked(uri: Uri) {
        if (!requireControl("file.pick")) return
        val flags = android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
            android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        runCatching {
            app.contentResolver.takePersistableUriPermission(uri, flags)
        }
        viewModelScope.launch {
            settingsStore.addPickedFolder(uri.toString())
            repo.log("file.pick", uri.toString().take(300), allowed = true)
        }
        banner(text(R.string.phone_files_added))
    }

    fun removeFolder(uri: String) {
        viewModelScope.launch {
            settingsStore.removePickedFolder(uri)
            runCatching {
                app.contentResolver.releasePersistableUriPermission(
                    uri.toUri(),
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        android.content.Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
            }
            repo.log("file.unpick", uri.take(300), allowed = true)
        }
    }

    // --- Permission result plumbing ---

    fun onPermissionResult(permission: String, granted: Boolean) {
        val label = when (permission) {
            Manifest.permission.SEND_SMS -> text(R.string.phone_permission_sms)
            Manifest.permission.CALL_PHONE -> text(R.string.phone_permission_phone)
            Manifest.permission.READ_SMS -> text(R.string.phone_permission_sms)
            Manifest.permission.POST_NOTIFICATIONS -> text(R.string.phone_permission_notifications)
            else -> permission
        }
        banner(
            app.getString(
                if (granted) R.string.phone_permission_granted_msg else R.string.phone_permission_denied_msg,
                label,
            ),
        )
        if (granted) refreshMessages()
    }

    fun consumePermissionRequest() {
        _state.update { it.copy(permissionToRequest = null) }
    }

    fun consumeMessage() {
        _state.update { it.copy(message = null) }
    }

    fun clearScreenText() {
        _state.update { it.copy(screenText = "") }
    }

    fun filteredApps(): List<AppEntry> {
        val q = _state.value.query.trim().lowercase()
        if (q.isBlank()) return _state.value.apps
        return _state.value.apps.filter {
            it.label.lowercase().contains(q) || it.packageName.lowercase().contains(q)
        }
    }

    class Factory(
        private val app: Application,
        private val settingsStore: SettingsStore,
        private val db: MayaDatabase,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(PhoneViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return PhoneViewModel(app, settingsStore, db) as T
        }
    }
}

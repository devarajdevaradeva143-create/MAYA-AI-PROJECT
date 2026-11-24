package com.devaraj.maya.service

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.devaraj.maya.MayaApp
import com.devaraj.maya.data.local.entity.NotificationEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Captures incoming notifications locally when the user grants Notification access.
 * Honors the phone-control master switch; nothing is uploaded.
 */
class MayaNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    companion object {
        @Volatile
        var instance: MayaNotificationListener? = null
            private set

        fun componentName(context: Context): ComponentName =
            ComponentName(context, MayaNotificationListener::class.java)

        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                "enabled_notification_listeners",
            ) ?: return false
            val target = componentName(context).flattenToString()
            return enabled.split(':').any { it.equals(target, ignoreCase = true) }
        }

        fun openSettings(context: Context) {
            runCatching {
                context.startActivity(
                    Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
    }

    override fun onListenerDisconnected() {
        instance = null
        super.onListenerDisconnected()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val notification = sbn ?: return
        val app = application as? MayaApp ?: return
        val container = runCatching { app.container }.getOrNull() ?: return
        scope.launch {
            val settings = container.settingsStore.settings.first()
            if (!settings.controlEnabled) return@launch
            val extras = notification.notification.extras
            val title = extras?.getCharSequence(android.app.Notification.EXTRA_TITLE)?.toString()
            val text = extras?.getCharSequence(android.app.Notification.EXTRA_TEXT)?.toString()
            if (title.isNullOrBlank() && text.isNullOrBlank()) return@launch
            container.database.notificationDao().insert(
                NotificationEntity(
                    id = UUID.randomUUID().toString(),
                    packageName = notification.packageName.orEmpty(),
                    title = title?.take(300),
                    body = text?.take(1000),
                    postedAt = notification.postTime,
                    important = notification.notification.flags and android.app.Notification.FLAG_ONGOING_EVENT != 0,
                ),
            )
        }
    }
}

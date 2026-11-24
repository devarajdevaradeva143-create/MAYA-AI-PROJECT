package com.devaraj.maya.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.devaraj.maya.MainActivity
import com.devaraj.maya.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Persistent notification shown while remote control session is active.
 * "Remote control active — Tap to stop"
 */
class PhoneRemoteForegroundService : Service() {

    companion object {
        private const val TAG = "PhoneRemoteService"
        private const val CHANNEL_ID = "maya_phone_remote"
        private const val NOTIFICATION_ID = 4102
        const val ACTION_START = "com.devaraj.maya.action.PHONE_REMOTE_START"
        const val ACTION_STOP = "com.devaraj.maya.action.PHONE_REMOTE_STOP"

        private val _running = MutableStateFlow(false)
        val running: StateFlow<Boolean> = _running

        @Volatile
        var isRunning = false
            private set

        private fun setRunning(value: Boolean) {
            isRunning = value
            _running.value = value
        }

        fun start(context: Context) {
            val intent = Intent(context, PhoneRemoteForegroundService::class.java).setAction(ACTION_START)
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }
        }

        fun stop(context: Context) {
            runCatching {
                context.stopService(Intent(context, PhoneRemoteForegroundService::class.java))
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                setRunning(false)
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            else -> {
                // Android 12+ blocks foreground starts from the background unless
                // the app holds a system-bound service (e.g. accessibility). Never
                // let that rejection crash the app; just stop quietly instead.
                try {
                    startForeground(NOTIFICATION_ID, buildNotification())
                    setRunning(true)
                } catch (e: Exception) {
                    Log.w(TAG, "startForeground rejected; stopping service", e)
                    setRunning(false)
                    stopSelf()
                }
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        setRunning(false)
        super.onDestroy()
    }

    private fun buildNotification(): Notification {
        createChannel()
        val openApp = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, PhoneRemoteForegroundService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_maya)
            .setContentTitle(getString(R.string.phone_remote_notification_title))
            .setContentText(getString(R.string.phone_remote_notification_body))
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .addAction(0, getString(R.string.phone_remote_notification_stop), stop)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.phone_remote_notification_channel),
            NotificationManager.IMPORTANCE_HIGH,
        )
        channel.description = getString(R.string.phone_remote_notification_channel_desc)
        manager.createNotificationChannel(channel)
    }
}
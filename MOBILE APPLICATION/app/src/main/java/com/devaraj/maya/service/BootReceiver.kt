package com.devaraj.maya.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Optional: restarts the wake listener after reboot if the user previously
 * enabled it. Guarded by a settings flag (not yet wired) — for now it only
 * logs intent; no auto-start to avoid surprising the user.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        // Auto-start intentionally disabled in v1 (mic restrictions on boot).
        // WakeForegroundService.start(context) can be called here once the
        // user opts in via settings.
    }
}

package com.devaraj.maya.data.repo

import androidx.core.net.toUri

import android.Manifest
import android.content.ContentResolver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.provider.CallLog
import android.provider.Settings
import android.provider.Telephony
import android.telephony.SmsManager
import androidx.core.content.ContextCompat
import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.local.entity.AuditEntity
import com.devaraj.maya.data.local.entity.NotificationEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

data class AppEntry(
    val label: String,
    val packageName: String,
)

data class SmsEntry(
    val address: String,
    val body: String,
    val date: Long,
    val type: Int,
)

data class CallEntry(
    val number: String,
    val name: String?,
    val date: Long,
    val duration: Long,
    val type: Int,
)

class PhoneControlRepository(
    private val context: Context,
    private val db: MayaDatabase,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val resolver: ContentResolver = context.contentResolver

    fun observeAudit(limit: Int = 200): Flow<List<AuditEntity>> = db.auditDao().observeRecent(limit)

    fun observeNotifications(limit: Int = 100): Flow<List<NotificationEntity>> =
        db.notificationDao().observeRecent(limit)

    suspend fun pruneNotifications(olderThanMs: Long = 7L * 24 * 60 * 60 * 1000) {
        db.notificationDao().deleteOlderThan(now() - olderThanMs)
    }

    suspend fun log(action: String, detail: String, allowed: Boolean) {
        db.auditDao().insert(
            AuditEntity(
                action = action,
                detail = detail.take(500),
                allowed = allowed,
                createdAt = now(),
            ),
        )
    }

    suspend fun listLaunchableApps(): List<AppEntry> = withContext(Dispatchers.IO) {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved = pm.queryIntentActivities(intent, PackageManager.ResolveInfoFlags.of(0))
        resolved
            .mapNotNull { info ->
                val label = info.loadLabel(pm)?.toString()?.trim().orEmpty()
                val pkg = info.activityInfo?.packageName.orEmpty()
                if (label.isBlank() || pkg.isBlank()) null else AppEntry(label = label, packageName = pkg)
            }
            .distinctBy { it.packageName }
            .sortedBy { it.label.lowercase() }
    }

    fun launchApp(packageName: String): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(intent)
            true
        } catch (_: Exception) {
            false
        }
    }

    fun openAppInfo(packageName: String) {
        val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
            data = Uri.fromParts("package", packageName, null)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            context.startActivity(intent)
        } catch (_: Exception) {
        }
    }

    // --- SMS (Phase 6) ---

    fun hasSmsReadPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_SMS,
    ) == PackageManager.PERMISSION_GRANTED

    fun hasSmsSendPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.SEND_SMS,
    ) == PackageManager.PERMISSION_GRANTED

    suspend fun readSms(limit: Int = 30): List<SmsEntry> = withContext(Dispatchers.IO) {
        if (!hasSmsReadPermission()) return@withContext emptyList()
        val projection = arrayOf(
            Telephony.Sms.ADDRESS,
            Telephony.Sms.BODY,
            Telephony.Sms.DATE,
            Telephony.Sms.TYPE,
        )
        val cursor: Cursor = try {
            resolver.query(
                Telephony.Sms.CONTENT_URI,
                projection,
                null,
                null,
                "${Telephony.Sms.DATE} DESC",
            ) ?: return@withContext emptyList()
        } catch (_: Exception) {
            return@withContext emptyList()
        }
        cursor.use { c ->
            val result = mutableListOf<SmsEntry>()
            val idxAddress = c.getColumnIndex(Telephony.Sms.ADDRESS)
            val idxBody = c.getColumnIndex(Telephony.Sms.BODY)
            val idxDate = c.getColumnIndex(Telephony.Sms.DATE)
            val idxType = c.getColumnIndex(Telephony.Sms.TYPE)
            while (c.moveToNext() && result.size < limit) {
                val address = if (idxAddress >= 0) c.getString(idxAddress).orEmpty() else ""
                val body = if (idxBody >= 0) c.getString(idxBody).orEmpty() else ""
                val date = if (idxDate >= 0) c.getLong(idxDate) else 0L
                val type = if (idxType >= 0) c.getInt(idxType) else 0
                if (address.isNotBlank() || body.isNotBlank()) {
                    result.add(SmsEntry(address, body.take(500), date, type))
                }
            }
            result
        }
    }

    fun sendSms(address: String, body: String): Boolean {
        if (!hasSmsSendPermission()) return false
        val target = address.trim()
        val message = body.trim()
        if (target.isBlank() || message.isBlank()) return false
        return try {
            val manager = SmsManager.getDefault()
            val parts = manager.divideMessage(message)
            if (parts.size > 1) {
                manager.sendMultipartTextMessage(target, null, ArrayList(parts), null, null)
            } else {
                manager.sendTextMessage(target, null, message, null, null)
            }
            true
        } catch (_: Exception) {
            false
        }
    }

    // --- Calls (Phase 6) ---

    fun hasCallLogPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_CALL_LOG,
    ) == PackageManager.PERMISSION_GRANTED

    fun hasCallPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.CALL_PHONE,
    ) == PackageManager.PERMISSION_GRANTED

    suspend fun readCallLog(limit: Int = 30): List<CallEntry> = withContext(Dispatchers.IO) {
        if (!hasCallLogPermission()) return@withContext emptyList()
        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls.TYPE,
        )
        val cursor: Cursor = try {
            resolver.query(
                CallLog.Calls.CONTENT_URI,
                projection,
                null,
                null,
                "${CallLog.Calls.DATE} DESC",
            ) ?: return@withContext emptyList()
        } catch (_: Exception) {
            return@withContext emptyList()
        }
        cursor.use { c ->
            val result = mutableListOf<CallEntry>()
            val idxNumber = c.getColumnIndex(CallLog.Calls.NUMBER)
            val idxName = c.getColumnIndex(CallLog.Calls.CACHED_NAME)
            val idxDate = c.getColumnIndex(CallLog.Calls.DATE)
            val idxDuration = c.getColumnIndex(CallLog.Calls.DURATION)
            val idxType = c.getColumnIndex(CallLog.Calls.TYPE)
            while (c.moveToNext() && result.size < limit) {
                val number = if (idxNumber >= 0) c.getString(idxNumber).orEmpty() else ""
                val name = if (idxName >= 0) c.getString(idxName) else null
                val date = if (idxDate >= 0) c.getLong(idxDate) else 0L
                val duration = if (idxDuration >= 0) c.getLong(idxDuration) else 0L
                val type = if (idxType >= 0) c.getInt(idxType) else 0
                if (number.isNotBlank()) result.add(CallEntry(number, name, date, duration, type))
            }
            result
        }
    }

    fun dial(number: String): Boolean {
        if (!hasCallPermission()) return false
        val target = number.trim()
        if (target.isBlank()) return false
        return try {
            val intent = Intent(Intent.ACTION_CALL).apply {
                data = Uri.fromParts("tel", target, null)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            true
        } catch (_: Exception) {
            false
        }
    }

    // --- WhatsApp (local, via deep link + user confirm) ---

    fun hasWhatsApp(): Boolean = whatsAppPackage() != null

    private fun whatsAppPackage(): String? =
        listOf("com.whatsapp", "com.whatsapp.w4b").firstOrNull { pkg ->
            try {
                context.packageManager.getPackageInfo(pkg, 0)
                true
            } catch (_: Exception) {
                false
            }
        }

    fun sendWhatsApp(number: String, text: String): Boolean {
        val target = number.trim().replace(Regex("[^0-9]"), "")
        val message = text.trim()
        if (target.isBlank() || message.isBlank()) return false
        val pkg = whatsAppPackage() ?: return false
        return try {
            val uri = "https://wa.me/$target?text=${android.net.Uri.encode(message)}".toUri()
            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, uri).apply {
                setPackage(pkg)
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
            true
        } catch (_: Exception) {
            false
        }
    }
}

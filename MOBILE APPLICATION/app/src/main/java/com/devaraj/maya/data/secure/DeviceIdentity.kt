package com.devaraj.maya.data.secure

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.devaraj.maya.data.prefs.SettingsStore
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Device ID per plan §12.5: Android ID hashed (16 hex) + random suffix
 * (16 hex) = 32 hex chars. Generated once, stored in DataStore.
 */
class DeviceIdentity(
    private val context: Context,
    private val store: SettingsStore,
) {

    suspend fun deviceId(): String = store.ensureDeviceId { generate() }

    fun deviceName(): String = "${Build.MANUFACTURER} ${Build.MODEL}"
        .trim()
        .replaceFirstChar { it.uppercase() }

    private fun generate(): String {
        val androidId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID,
        ).orEmpty()
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(androidId.toByteArray(Charsets.UTF_8))
        val hashed = digest.take(8).joinToString("") { "%02x".format(it) }
        val random = ByteArray(8)
        SecureRandom().nextBytes(random)
        return hashed + random.joinToString("") { "%02x".format(it) }
    }
}

package com.devaraj.maya.data.prefs

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import com.devaraj.maya.domain.model.OperatingMode

private val Context.mayaDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "maya_settings",
)

enum class ThemeMode(val value: String) {
    SYSTEM("system"),
    DARK("dark"),
    LIGHT("light");

    companion object {
        fun from(value: String?): ThemeMode = values().firstOrNull { it.value == value } ?: SYSTEM
    }
}

data class MayaSettings(
    val onboardingDone: Boolean = false,
    val theme: ThemeMode = ThemeMode.SYSTEM,
    val laptopHost: String = "",
    val laptopPort: Int = DEFAULT_PORT,
    val controlEnabled: Boolean = false,
    val controlRequireUnlock: Boolean = true,
    val pickedFolders: Set<String> = emptySet(),
    val connectionMode: String = "wifi",
    val wakeNameEnabled: Boolean = false,
    val operatingMode: OperatingMode = OperatingMode.AI,
    val voiceBiometricsEnabled: Boolean = false,
    val phoneRemoteEnabled: Boolean = false,
    val geminiApiKey: String = "",
) {
    companion object {
        const val DEFAULT_PORT = 8420
    }
}

/**
 * Local-only settings. Nothing here ever leaves the phone.
 */
class SettingsStore(private val context: Context) {

    private object Keys {
        val ONBOARDING_DONE = booleanPreferencesKey("onboarding_done")
        val THEME = stringPreferencesKey("theme")
        val LAPTOP_HOST = stringPreferencesKey("laptop_host")
        val LAPTOP_PORT = intPreferencesKey("laptop_port")
        val DEVICE_ID = stringPreferencesKey("device_id")
        val CONTROL_ENABLED = booleanPreferencesKey("control_enabled")
        val CONTROL_REQUIRE_UNLOCK = booleanPreferencesKey("control_require_unlock")
        val PICKED_FOLDERS = stringSetPreferencesKey("picked_folders")
        val CONNECTION_MODE = stringPreferencesKey("connection_mode")
        val WAKE_NAME_ENABLED = booleanPreferencesKey("wake_name_enabled")
        val OPERATING_MODE = stringPreferencesKey("operating_mode")
        val VOICE_BIOMETRICS_ENABLED = booleanPreferencesKey("voice_biometrics_enabled")
        val PHONE_REMOTE_ENABLED = booleanPreferencesKey("phone_remote_enabled")
        val GEMINI_API_KEY = stringPreferencesKey("gemini_api_key")
    }

    val settings: Flow<MayaSettings> = context.mayaDataStore.data
        .catch { error ->
            if (error is IOException) emit(emptyPreferences()) else throw error
        }
        .map { prefs ->
            MayaSettings(
                onboardingDone = prefs[Keys.ONBOARDING_DONE] ?: false,
                theme = ThemeMode.from(prefs[Keys.THEME]),
                laptopHost = prefs[Keys.LAPTOP_HOST] ?: "",
                laptopPort = prefs[Keys.LAPTOP_PORT] ?: MayaSettings.DEFAULT_PORT,
                controlEnabled = prefs[Keys.CONTROL_ENABLED] ?: false,
                controlRequireUnlock = prefs[Keys.CONTROL_REQUIRE_UNLOCK] ?: true,
                pickedFolders = prefs[Keys.PICKED_FOLDERS] ?: emptySet(),
                connectionMode = prefs[Keys.CONNECTION_MODE] ?: "wifi",
                wakeNameEnabled = prefs[Keys.WAKE_NAME_ENABLED] ?: false,
                operatingMode = OperatingMode.from(prefs[Keys.OPERATING_MODE]),
                phoneRemoteEnabled = prefs[Keys.PHONE_REMOTE_ENABLED] ?: false,
                geminiApiKey = prefs[Keys.GEMINI_API_KEY] ?: "",
            )
        }

    suspend fun setOnboardingDone(done: Boolean) {
        context.mayaDataStore.edit { it[Keys.ONBOARDING_DONE] = done }
    }

    suspend fun setTheme(mode: ThemeMode) {
        context.mayaDataStore.edit { it[Keys.THEME] = mode.value }
    }

    suspend fun setLaptop(host: String, port: Int) {
        context.mayaDataStore.edit {
            it[Keys.LAPTOP_HOST] = host
            it[Keys.LAPTOP_PORT] = port
        }
    }

    suspend fun setControlEnabled(enabled: Boolean) {
        context.mayaDataStore.edit { it[Keys.CONTROL_ENABLED] = enabled }
    }

    suspend fun setControlRequireUnlock(required: Boolean) {
        context.mayaDataStore.edit { it[Keys.CONTROL_REQUIRE_UNLOCK] = required }
    }

    suspend fun addPickedFolder(uri: String) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.PICKED_FOLDERS] = (prefs[Keys.PICKED_FOLDERS] ?: emptySet()) + uri
        }
    }

    suspend fun removePickedFolder(uri: String) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.PICKED_FOLDERS] = (prefs[Keys.PICKED_FOLDERS] ?: emptySet()) - uri
        }
    }

    suspend fun setConnectionMode(mode: String) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.CONNECTION_MODE] = mode
        }
    }

    suspend fun setWakeNameEnabled(enabled: Boolean) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.WAKE_NAME_ENABLED] = enabled
        }
    }

    suspend fun setOperatingMode(mode: OperatingMode) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.OPERATING_MODE] = mode.value
        }
    }

    suspend fun setPhoneRemoteEnabled(enabled: Boolean) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.PHONE_REMOTE_ENABLED] = enabled
        }
    }

    suspend fun setGeminiApiKey(key: String) {
        context.mayaDataStore.edit { prefs ->
            prefs[Keys.GEMINI_API_KEY] = key
        }
    }

    /** Stable 32-hex device ID; generated once and kept on this phone. */
    suspend fun ensureDeviceId(generate: () -> String): String {
        var result: String? = null
        context.mayaDataStore.edit { prefs ->
            val existing = prefs[Keys.DEVICE_ID]
            if (existing.isNullOrBlank()) {
                val created = generate()
                prefs[Keys.DEVICE_ID] = created
                result = created
            } else {
                result = existing
            }
        }
        return requireNotNull(result)
    }
}

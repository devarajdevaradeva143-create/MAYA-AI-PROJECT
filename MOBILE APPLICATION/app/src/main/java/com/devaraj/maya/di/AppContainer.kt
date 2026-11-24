package com.devaraj.maya.di

import android.content.Context
import androidx.room.Room
import com.devaraj.maya.BuildConfig
import com.devaraj.maya.data.local.MayaDatabase
import com.devaraj.maya.data.cloud.GeminiRepository
import com.devaraj.maya.data.model.OnDeviceModelManager
import kotlinx.coroutines.flow.first
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.remote.ApiClient
import com.devaraj.maya.data.remote.ConnectionRepository
import com.devaraj.maya.data.remote.PairingRepository
import com.devaraj.maya.data.remote.SessionState
import com.devaraj.maya.data.repo.ChatRepository
import com.devaraj.maya.data.secure.DeviceIdentity
import com.devaraj.maya.data.secure.TokenVault
import com.devaraj.maya.data.wake.VoskModelStore
import com.devaraj.maya.control.hybrid.HybridController

/**
 * Manual dependency container (plan §7: no Hilt/Koin in v1).
 */
class AppContainer(context: Context) {

    private val appContext = context.applicationContext

    val database: MayaDatabase by lazy {
        Room.databaseBuilder(appContext, MayaDatabase::class.java, MayaDatabase.NAME)
            .build()
    }

    val settingsStore: SettingsStore by lazy { SettingsStore(appContext) }

    val tokenVault: TokenVault by lazy { TokenVault(appContext) }

    val deviceIdentity: DeviceIdentity by lazy { DeviceIdentity(appContext, settingsStore) }

    val session: SessionState by lazy { SessionState() }

    /** Auth interceptor reads the active device's token from the vault cache. */
    val apiClient: ApiClient by lazy {
        ApiClient(
            tokenProvider = {
                session.activeDeviceId?.let { tokenVault.load(it) }
            },
        )
    }

    val chatRepository: ChatRepository by lazy { ChatRepository(database) }

    val onDeviceModel: OnDeviceModelManager by lazy { OnDeviceModelManager(appContext) }

    val geminiRepository: GeminiRepository by lazy {
        GeminiRepository(apiKeyProvider = {
            // Read from DataStore synchronously — SettingsStore caches in memory
            settingsStore.settings.let { flow ->
                kotlinx.coroutines.runBlocking {
                    flow.first().geminiApiKey
                }
            }
        })
    }

    val voskModel: VoskModelStore by lazy { VoskModelStore(appContext) }

    val pairingRepository: PairingRepository by lazy {
        PairingRepository(
            apiFactory = { host, port -> apiClient.api(host, port) },
            tokenStore = tokenVault,
            deviceDao = database.deviceDao(),
            appVersion = BuildConfig.VERSION_NAME,
            session = session,
        )
    }

    val hybridController: HybridController by lazy { HybridController() }

    val connectionRepository: ConnectionRepository by lazy {
        ConnectionRepository(
            apiFactory = { host, port, quick -> apiClient.api(host, port, quick) },
            tokenStore = tokenVault,
            deviceDao = database.deviceDao(),
            session = session,
        )
    }
}

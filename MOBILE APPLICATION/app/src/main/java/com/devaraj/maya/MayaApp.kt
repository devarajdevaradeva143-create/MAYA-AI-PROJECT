package com.devaraj.maya

import android.app.Application
import com.devaraj.maya.di.AppContainer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Application entry point. Owns the manual DI container.
 */
class MayaApp : Application() {

    lateinit var container: AppContainer
        private set

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        // Encrypt any key saved by older versions (plaintext -> Keystore).
        appScope.launch { container.settingsStore.migrateLegacyGeminiKey() }
    }

    /** Free the on-device model when Android is under memory pressure. */
    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (::container.isInitialized) container.onDeviceModel.onTrimMemory(level)
    }

    override fun onLowMemory() {
        super.onLowMemory()
        if (::container.isInitialized) container.onDeviceModel.onLowMemory()
    }
}

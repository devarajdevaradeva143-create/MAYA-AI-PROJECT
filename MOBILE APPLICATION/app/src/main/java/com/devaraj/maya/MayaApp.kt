package com.devaraj.maya

import android.app.Application
import com.devaraj.maya.di.AppContainer

/**
 * Application entry point. Owns the manual DI container.
 */
class MayaApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
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

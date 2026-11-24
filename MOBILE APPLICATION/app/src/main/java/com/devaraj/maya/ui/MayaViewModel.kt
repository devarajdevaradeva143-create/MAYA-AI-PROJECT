package com.devaraj.maya.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.devaraj.maya.data.prefs.MayaSettings
import com.devaraj.maya.data.prefs.SettingsStore
import com.devaraj.maya.data.prefs.ThemeMode
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Root view model: onboarding flag + theme.
 */
class MayaViewModel(private val store: SettingsStore) : ViewModel() {

    /** null = DataStore has not emitted yet (avoids an onboarding flash). */
    val settings: StateFlow<MayaSettings?> = store.settings.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = null,
    )

    fun completeOnboarding() {
        viewModelScope.launch { store.setOnboardingDone(true) }
    }

    fun setTheme(mode: ThemeMode) {
        viewModelScope.launch { store.setTheme(mode) }
    }

    class Factory(private val store: SettingsStore) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(MayaViewModel::class.java)) {
                "Unknown ViewModel: ${modelClass.name}"
            }
            return MayaViewModel(store) as T
        }
    }
}

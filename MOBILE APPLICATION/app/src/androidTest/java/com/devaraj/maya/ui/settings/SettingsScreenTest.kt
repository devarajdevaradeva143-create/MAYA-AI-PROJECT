package com.devaraj.maya.ui.settings

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.devaraj.maya.R
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.data.wake.VoskModelStatus
import com.devaraj.maya.ui.theme.MayaTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SettingsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val context: Context = ApplicationProvider.getApplicationContext()

    private fun setSettings(
        themeMode: ThemeMode = ThemeMode.LIGHT,
        onThemeChange: (ThemeMode) -> Unit = {},
        connectionMode: String = "wifi",
        onConnectionModeChange: (String) -> Unit = {},
        voskStatus: VoskModelStatus = VoskModelStatus(),
        wakeNameEnabled: Boolean = false,
        onWakeNameChange: (Boolean) -> Unit = {},
        wakeRunning: Boolean = false,
        onWakeToggle: (Boolean) -> Unit = {},
    ) {
        compose.setContent {
            MayaTheme(darkTheme = false) {
                SettingsScreen(
                    state = SettingsUiState(voskModel = voskStatus),
                    themeMode = themeMode,
                    onThemeChange = onThemeChange,
                    connectionMode = connectionMode,
                    onConnectionModeChange = onConnectionModeChange,
                    controlEnabled = false,
                    onControlEnabledChange = {},
                    requireUnlock = true,
                    onRequireUnlockChange = {},
                    phoneRemoteEnabled = false,
                    onPhoneRemoteChange = {},
                    onExport = {},
                    onDeleteAll = {},
                    onConsumeExportStatus = {},
                    onConsumeDeleteStatus = {},
                    onImportModel = {},
                    onDeleteModel = {},
                    onUnloadModel = {},
                    wakeNameEnabled = wakeNameEnabled,
                    onWakeNameChange = onWakeNameChange,
                    voskStatus = voskStatus,
                    wakeRunning = wakeRunning,
                    onWakeToggle = onWakeToggle,
                )
            }
        }
    }

    @Test
    fun themeChipsReportSelection() {
        var selected: ThemeMode? = null
        setSettings(themeMode = ThemeMode.LIGHT, onThemeChange = { selected = it })

        compose.onNodeWithText(context.getString(R.string.theme_dark)).performClick()

        compose.runOnIdle { assertEquals(ThemeMode.DARK, selected) }
    }

    @Test
    fun connectionModeChipReportsUsb() {
        var mode: String? = null
        setSettings(connectionMode = "wifi", onConnectionModeChange = { mode = it })

        compose.onNodeWithText("USB").performScrollTo().performClick()

        compose.runOnIdle { assertEquals("usb", mode) }
    }

    @Test
    fun nameWakeChipIsDisabledWithoutModel() {
        setSettings(voskStatus = VoskModelStatus(installed = false))

        compose.onNodeWithText("Name \"Maya\"").performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun nameWakeChipTogglesWhenModelInstalled() {
        var enabled = false
        setSettings(
            voskStatus = VoskModelStatus(installed = true, sizeBytes = 2_000_000),
            wakeNameEnabled = false,
            onWakeNameChange = { enabled = it },
        )

        compose.onNodeWithText("Name \"Maya\"").performScrollTo().performClick()

        compose.runOnIdle { assertTrue(enabled) }
    }

    @Test
    fun wakeToggleCallsBack() {
        var wake = false
        setSettings(wakeRunning = false, onWakeToggle = { wake = it })

        compose.onNodeWithTag("wake_on").performScrollTo().assertIsEnabled().performClick()

        compose.runOnIdle { assertTrue(wake) }
    }
}

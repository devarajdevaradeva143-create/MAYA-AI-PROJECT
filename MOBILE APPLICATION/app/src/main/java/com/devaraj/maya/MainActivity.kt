package com.devaraj.maya

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.service.PhoneRemoteHttpServer
import com.devaraj.maya.service.WakeForegroundService
import com.devaraj.maya.ui.MayaViewModel
import com.devaraj.maya.ui.main.MayaMainScreen
import com.devaraj.maya.ui.onboarding.OnboardingScreen
import com.devaraj.maya.ui.theme.MayaTheme
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {

    /** Incremented by the wake service ("Maya" x3 or two claps). */
    private val wakeRequests = MutableStateFlow(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (readWakeIntent(intent)) wakeRequests.value = 1
        enableEdgeToEdge()
        setContent {
            val app = application as MayaApp
            val viewModel: MayaViewModel = viewModel(
                factory = MayaViewModel.Factory(app.container.settingsStore),
            )
            val settings by viewModel.settings.collectAsStateWithLifecycle()
            val wakeRequest by wakeRequests.collectAsStateWithLifecycle()
            val pendingRemote by PhoneRemoteHttpServer.pendingRequest.collectAsStateWithLifecycle()

            val current = settings
            if (current == null) {
                // DataStore is still loading: keep the brand background, no flash.
                MayaTheme {
                    Surface(
                        modifier = Modifier.fillMaxSize(),
                        color = MaterialTheme.colorScheme.background,
                    ) {
                        Box(modifier = Modifier.fillMaxSize())
                    }
                }
                return@setContent
            }

            val darkTheme = when (current.theme) {
                ThemeMode.DARK -> true
                ThemeMode.LIGHT -> false
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
            }

            MayaTheme(darkTheme = darkTheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    if (current.onboardingDone) {
                        MayaMainScreen(
                            themeMode = current.theme,
                            onThemeChange = viewModel::setTheme,
                            wakeRequest = wakeRequest,
                            onWakeConsumed = { wakeRequests.value = 0 },
                        )
                    } else {
                        OnboardingScreen(onFinish = viewModel::completeOnboarding)
                    }

                    val req = pendingRemote
                    if (req != null && req.status.name == "PENDING") {
                        AlertDialog(
                            onDismissRequest = { PhoneRemoteHttpServer.denyRequest(req.id) },
                            title = { Text("Allow remote control?") },
                            text = { Text("Laptop indha phone-a control panna permission kekkudhu. Allow panna mattum screen/input share aagum.") },
                            confirmButton = {
                                TextButton(onClick = { PhoneRemoteHttpServer.approveRequest(req.id) }) { Text("Allow") }
                            },
                            dismissButton = {
                                TextButton(onClick = { PhoneRemoteHttpServer.denyRequest(req.id) }) { Text("Deny") }
                            },
                        )
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (readWakeIntent(intent)) wakeRequests.value += 1
    }

    private fun readWakeIntent(intent: Intent?): Boolean =
        intent?.getBooleanExtra(WakeForegroundService.EXTRA_WAKE, false) == true
}

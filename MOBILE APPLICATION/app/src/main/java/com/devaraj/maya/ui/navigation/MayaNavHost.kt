package com.devaraj.maya.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChatBubbleOutline
import androidx.compose.material.icons.outlined.Computer
import androidx.compose.material.icons.outlined.MonitorHeart
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Smartphone
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.devaraj.maya.MayaApp
import com.devaraj.maya.R
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.domain.model.Device
import com.devaraj.maya.ui.chat.ChatScreen
import com.devaraj.maya.ui.chat.ChatViewModel
import com.devaraj.maya.ui.components.PlaceholderScreen
import com.devaraj.maya.ui.laptop.LaptopControlViewModel
import com.devaraj.maya.ui.laptop.LaptopScreen
import com.devaraj.maya.ui.laptop.RemoteViewModel
import com.devaraj.maya.ui.monitor.MonitorScreen
import com.devaraj.maya.ui.monitor.MonitorViewModel
import com.devaraj.maya.ui.phone.PhoneScreen
import com.devaraj.maya.ui.phone.PhoneViewModel
import com.devaraj.maya.ui.settings.SettingsScreen
import com.devaraj.maya.ui.settings.SettingsViewModel
import com.devaraj.maya.ui.voice.VoiceScreen
import com.devaraj.maya.ui.voice.VoiceViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

data class BottomItem(
    val route: String,
    val label: Int,
    val icon: ImageVector,
)

val bottomItems = listOf(
    BottomItem(Routes.CHAT, R.string.nav_chat, Icons.Outlined.ChatBubbleOutline),
    BottomItem(Routes.VOICE, R.string.nav_voice, Icons.Outlined.Mic),
    BottomItem(Routes.LAPTOP, R.string.nav_laptop, Icons.Outlined.Computer),
    BottomItem(Routes.PHONE, R.string.nav_phone, Icons.Outlined.Smartphone),
    BottomItem(Routes.MONITOR, R.string.nav_monitor, Icons.Outlined.MonitorHeart),
    BottomItem(Routes.SETTINGS, R.string.nav_settings, Icons.Outlined.Settings),
)

@Composable
fun MayaNavHost(
    navController: NavHostController,
    themeMode: ThemeMode,
    onThemeChange: (ThemeMode) -> Unit,
    connectionState: ConnectionState,
    devices: List<Device>,
    onPair: () -> Unit,
    onConnect: () -> Unit,
    onForget: () -> Unit,
    onToggleAutoConnect: (Boolean) -> Unit,
    wakeRequest: Int = 0,
    onWakeConsumed: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val app = context.applicationContext as MayaApp

    NavHost(
        navController = navController,
        startDestination = Routes.CHAT,
        modifier = modifier,
    ) {
        composable(Routes.CHAT) {
            val factory = remember(app) {
                ChatViewModel.Factory(
                    chatRepository = app.container.chatRepository,
                    connectionRepository = app.container.connectionRepository,
                    apiClient = app.container.apiClient,
                    modelManager = app.container.onDeviceModel,
                    geminiRepository = app.container.geminiRepository,
                    geminiApiKeyFlow = app.container.settingsStore.settings
                        .map { it.geminiApiKey },
                )
            }
            val chatViewModel: ChatViewModel = viewModel(factory = factory)
            val chatState by chatViewModel.state.collectAsStateWithLifecycle()

            ChatScreen(
                state = chatState,
                onSend = chatViewModel::send,
                onStop = chatViewModel::stopStreaming,
                onRetry = chatViewModel::retry,
                onNewChat = chatViewModel::newChat,
                onDeleteChat = chatViewModel::deleteChat,
                onPersonaChange = chatViewModel::setPersona,
                onDismissError = chatViewModel::clearError,
                onSendToWhatsApp = chatViewModel::sendToWhatsApp,
            )
        }
        composable(Routes.VOICE) {
            val voiceFactory = remember(app) {
                VoiceViewModel.Factory(
                    app = app,
                    chatRepository = app.container.chatRepository,
                    connectionRepository = app.container.connectionRepository,
                    apiClient = app.container.apiClient,
                    settingsStore = app.container.settingsStore,
                    piperTts = app.container.piperTts,
                    geminiRepository = app.container.geminiRepository,
                    onDeviceModel = app.container.onDeviceModel,
                    geminiTts = app.container.geminiTts,
                    geminiVoicePlayer = app.container.geminiVoicePlayer,
                )
            }
            val voiceViewModel: VoiceViewModel = viewModel(factory = voiceFactory)
            val voiceState by voiceViewModel.state.collectAsStateWithLifecycle()

            LaunchedEffect(wakeRequest) {
                if (wakeRequest > 0) {
                    voiceViewModel.startListening()
                    onWakeConsumed()
                }
            }

            VoiceScreen(
                state = voiceState,
                onStartListening = voiceViewModel::startListening,
                onStop = voiceViewModel::stop,
            )
        }
        composable(Routes.LAPTOP) {
            val controlFactory = remember(app) {
                LaptopControlViewModel.Factory(
                    connectionRepository = app.container.connectionRepository,
                    apiClient = app.container.apiClient,
                    db = app.container.database,
                )
            }
            val controlVm: LaptopControlViewModel = viewModel(factory = controlFactory)
            val controlState by controlVm.state.collectAsStateWithLifecycle()

            val remoteFactory = remember(app) {
                RemoteViewModel.Factory(
                    connectionRepository = app.container.connectionRepository,
                    apiClient = app.container.apiClient,
                    context = app.applicationContext,
                )
            }
            val remoteVm: RemoteViewModel = viewModel(factory = remoteFactory)
            val appSettings by app.container.settingsStore.settings.collectAsStateWithLifecycle(initialValue = com.devaraj.maya.data.prefs.MayaSettings())

            LaptopScreen(
                connectionState = connectionState,
                devices = devices,
                onPair = onPair,
                onConnect = onConnect,
                onForget = onForget,
                onToggleAutoConnect = onToggleAutoConnect,
                controlState = controlState,
                operatingMode = appSettings.operatingMode,
                remoteViewModel = remoteVm,
                onControlAppNameChange = controlVm::setAppName,
                onControlVolumeChange = controlVm::setVolumeLevel,
                onControlClipboardChange = controlVm::setClipboardText,
                onControlOpenApp = controlVm::requestOpenApp,
                onControlLock = controlVm::requestLock,
                onControlSleep = controlVm::requestSleep,
                onControlMute = controlVm::requestMute,
                onControlUnmute = controlVm::requestUnmute,
                onControlVolume = controlVm::requestVolume,
                onControlScreenshot = controlVm::requestScreenshot,
                onControlMediaPlay = controlVm::requestMediaPlay,
                onControlMediaPause = controlVm::requestMediaPause,
                onControlMediaNext = controlVm::requestMediaNext,
                onControlMediaPrev = controlVm::requestMediaPrev,
                onControlClipboardSet = controlVm::requestClipboardSet,
                onControlNotify = controlVm::requestNotify,
                onControlConfirm = controlVm::confirmPending,
                onControlCancel = controlVm::cancelPending,
            )
        }
        composable(Routes.PHONE) {
            val phoneFactory = remember(app) {
                PhoneViewModel.Factory(
                    app = app,
                    settingsStore = app.container.settingsStore,
                    db = app.container.database,
                )
            }
            val phoneViewModel: PhoneViewModel = viewModel(factory = phoneFactory)
            val phoneState by phoneViewModel.state.collectAsStateWithLifecycle()
            val filteredApps = phoneViewModel.filteredApps()

            PhoneScreen(
                state = phoneState,
                filteredApps = filteredApps,
                onControlEnabledChange = phoneViewModel::setControlEnabled,
                onRequireUnlockChange = phoneViewModel::setRequireUnlock,
                onTabSelect = phoneViewModel::selectTab,
                onQueryChange = phoneViewModel::setQuery,
                onOpenApp = phoneViewModel::openApp,
                onOpenAppInfo = phoneViewModel::openAppInfo,
                onRefreshMessages = phoneViewModel::refreshMessages,
                onRequestSms = phoneViewModel::requestSendSms,
                onConfirmSms = phoneViewModel::confirmSendSms,
                onCancelSms = phoneViewModel::cancelSendSms,
                onRequestCall = phoneViewModel::requestCall,
                onConfirmCall = phoneViewModel::confirmCall,
                onCancelCall = phoneViewModel::cancelCall,
                onRequestWhatsApp = phoneViewModel::requestSendWhatsApp,
                onConfirmWhatsApp = phoneViewModel::confirmSendWhatsApp,
                onCancelWhatsApp = phoneViewModel::cancelSendWhatsApp,
                onPermissionResult = phoneViewModel::onPermissionResult,
                onPermissionRequestConsumed = phoneViewModel::consumePermissionRequest,
                onReadScreen = phoneViewModel::readScreen,
                onScreenBack = phoneViewModel::screenBack,
                onScreenHome = phoneViewModel::screenHome,
                onClickOnScreen = phoneViewModel::clickOnScreen,
                onClearScreenText = phoneViewModel::clearScreenText,
                onFolderPicked = phoneViewModel::onFolderPicked,
                onFolderRemoved = phoneViewModel::removeFolder,
                onRefreshPermissionStatus = phoneViewModel::refreshPermissionStatus,
                onConsumeMessage = phoneViewModel::consumeMessage,
            )
        }
        composable(Routes.MONITOR) {
            val monitorFactory = remember(app) {
                MonitorViewModel.Factory(
                    appContext = app.applicationContext,
                    connectionRepository = app.container.connectionRepository,
                    apiClient = app.container.apiClient,
                )
            }
            val monitorVm: MonitorViewModel = viewModel(factory = monitorFactory)
            val monitorState by monitorVm.state.collectAsStateWithLifecycle()
            MonitorScreen(
                state = monitorState,
                onStart = monitorVm::start,
                onStop = monitorVm::stop,
            )
        }
        composable(Routes.SETTINGS) {
            val settingsFactory = remember(app) {
                SettingsViewModel.Factory(
                    app = app,
                    settingsStore = app.container.settingsStore,
                    db = app.container.database,
                    tokenVault = app.container.tokenVault,
                    modelManager = app.container.onDeviceModel,
                    voskModelStore = app.container.voskModel,
                )
            }
            val settingsVm: SettingsViewModel = viewModel(factory = settingsFactory)
            val settingsState by settingsVm.state.collectAsStateWithLifecycle()
            val appSettings by app.container.settingsStore.settings.collectAsStateWithLifecycle(initialValue = com.devaraj.maya.data.prefs.MayaSettings())
            val wakeRunning by com.devaraj.maya.service.WakeForegroundService.running.collectAsState()
            val phoneRemoteRunning by com.devaraj.maya.service.PhoneRemoteForegroundService.running.collectAsState()

            SettingsScreen(
                state = settingsState,
                themeMode = themeMode,
                onThemeChange = onThemeChange,
                connectionMode = appSettings.connectionMode,
                onConnectionModeChange = settingsVm::setConnectionMode,
                operatingMode = appSettings.operatingMode,
                onOperatingModeChange = settingsVm::setOperatingMode,
                controlEnabled = appSettings.controlEnabled,
                onControlEnabledChange = settingsVm::setControlEnabled,
                requireUnlock = appSettings.controlRequireUnlock,
                onRequireUnlockChange = settingsVm::setRequireUnlock,
                phoneRemoteEnabled = appSettings.phoneRemoteEnabled,
                onPhoneRemoteChange = settingsVm::setPhoneRemoteEnabled,
                screenSharing = settingsState.screenSharing,
                onStartScreenShare = settingsVm::startScreenShare,
                onStopScreenShare = settingsVm::stopScreenShare,
                onExport = settingsVm::exportData,
                onDeleteAll = settingsVm::deleteAllData,
                onConsumeExportStatus = settingsVm::consumeExportStatus,
                onConsumeDeleteStatus = settingsVm::consumeDeleteStatus,
                onImportModel = settingsVm::importModel,
                onDeleteModel = settingsVm::deleteModel,
                onUnloadModel = settingsVm::unloadModel,
                wakeRunning = wakeRunning,
                onWakeToggle = { enabled ->
                    if (enabled) com.devaraj.maya.service.WakeForegroundService.start(app)
                    else com.devaraj.maya.service.WakeForegroundService.stop(app)
                },
                wakeNameEnabled = appSettings.wakeNameEnabled,
                onWakeNameChange = settingsVm::setWakeName,
                voskStatus = settingsState.voskModel,
                voskBusy = settingsState.voskBusy,
                voskProgress = settingsState.voskProgress,
                voskMessage = settingsState.voskMessage,
                onImportVosk = settingsVm::importVoskModel,
                onDeleteVosk = settingsVm::deleteVoskModel,
                geminiApiKey = appSettings.geminiApiKey,
                onGeminiKeyChange = { key ->
                    CoroutineScope(Dispatchers.IO).launch {
                        settingsVm.setGeminiApiKey(key)
                    }
                },
            )
        }
    }
}

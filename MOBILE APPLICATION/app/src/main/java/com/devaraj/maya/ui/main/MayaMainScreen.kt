package com.devaraj.maya.ui.main

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.devaraj.maya.MayaApp
import com.devaraj.maya.R
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.data.remote.ConnectionState
import com.devaraj.maya.ui.laptop.ConnectionViewModel
import com.devaraj.maya.ui.navigation.MayaNavHost
import com.devaraj.maya.ui.navigation.Routes
import com.devaraj.maya.ui.navigation.bottomItems
import com.devaraj.maya.ui.pairing.PairingScreen
import com.devaraj.maya.ui.theme.MayaSuccess
import com.devaraj.maya.ui.theme.MayaWarning

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MayaMainScreen(
    themeMode: ThemeMode,
    onThemeChange: (ThemeMode) -> Unit,
    wakeRequest: Int = 0,
    onWakeConsumed: () -> Unit = {},
) {
    val context = LocalContext.current
    val app = context.applicationContext as MayaApp
    val connectionViewModel: ConnectionViewModel = viewModel(
        factory = remember(app) {
            ConnectionViewModel.Factory(
                connectionRepository = app.container.connectionRepository,
                pairingRepository = app.container.pairingRepository,
                settingsStore = app.container.settingsStore,
            )
        },
    )
    val connectionState by connectionViewModel.connection.collectAsStateWithLifecycle()
    val devices by connectionViewModel.devices.collectAsStateWithLifecycle()

    val navController = rememberNavController()
    var showPairing by rememberSaveable { mutableStateOf(false) }

    BackHandler(enabled = showPairing) { showPairing = false }

    if (showPairing) {
        PairingScreen(
            onBack = { showPairing = false },
            onDone = {
                showPairing = false
                navController.navigate(Routes.CHAT) {
                    popUpTo(navController.graph.findStartDestination().id) {
                        saveState = true
                    }
                    launchSingleTop = true
                    restoreState = true
                }
            },
        )
        return
    }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route ?: Routes.CHAT

    LaunchedEffect(wakeRequest) {
        if (wakeRequest > 0 && currentRoute != Routes.VOICE) {
            navController.navigate(Routes.VOICE) {
                popUpTo(navController.graph.findStartDestination().id) {
                    saveState = true
                }
                launchSingleTop = true
                restoreState = true
            }
        }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = { Text(text = stringResource(R.string.app_name)) },
                actions = { ConnectionChip(state = connectionState) },
            )
        },
        bottomBar = {
            NavigationBar {
                bottomItems.forEach { item ->
                    NavigationBarItem(
                        selected = currentRoute == item.route,
                        onClick = {
                            if (currentRoute != item.route) {
                                navController.navigate(item.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            }
                        },
                        icon = {
                            Icon(
                                imageVector = item.icon,
                                contentDescription = stringResource(item.label),
                            )
                        },
                        label = { Text(text = stringResource(item.label)) },
                    )
                }
            }
        },
    ) { padding ->
        MayaNavHost(
            navController = navController,
            themeMode = themeMode,
            onThemeChange = onThemeChange,
            connectionState = connectionState,
            devices = devices,
            onPair = { showPairing = true },
            onConnect = connectionViewModel::connect,
            onForget = connectionViewModel::forgetLaptop,
            onToggleAutoConnect = connectionViewModel::setAutoConnect,
            wakeRequest = wakeRequest,
            onWakeConsumed = onWakeConsumed,
            modifier = Modifier.padding(padding),
        )
    }
}

@Composable
private fun ConnectionChip(state: ConnectionState) {
    val connected = state is ConnectionState.Connected
    val checking = state is ConnectionState.Checking
    val dotColor = when {
        connected -> MayaSuccess
        checking -> MayaWarning
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    val label = when {
        connected -> R.string.connection_online
        checking -> R.string.connection_checking
        else -> R.string.connection_offline
    }

    Surface(
        shape = RoundedCornerShape(50),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier.padding(end = 12.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(color = dotColor, shape = CircleShape),
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = stringResource(label),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

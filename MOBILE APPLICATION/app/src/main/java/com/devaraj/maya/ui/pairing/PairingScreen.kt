package com.devaraj.maya.ui.pairing

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.Computer
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.devaraj.maya.MayaApp
import com.devaraj.maya.R
import com.devaraj.maya.data.discovery.DiscoveredLaptop
import com.devaraj.maya.data.discovery.LaptopDiscovery
import com.devaraj.maya.ui.connection.reasonText
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

@Composable
fun PairingScreen(
    onDone: () -> Unit,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val app = context.applicationContext as MayaApp
    val factory = remember(app) {
        PairingViewModel.Factory(
            pairingRepository = app.container.pairingRepository,
            connectionRepository = app.container.connectionRepository,
            deviceIdentity = app.container.deviceIdentity,
            discovery = LaptopDiscovery(app),
            settingsStore = app.container.settingsStore,
        )
    }
    val viewModel: PairingViewModel = viewModel(factory = factory)
    val state by viewModel.state.collectAsStateWithLifecycle()

    val scanLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        contract = ScanContract(),
    ) { result -> result.contents?.let(viewModel::claimQr) }

    LaunchedEffect(Unit) {
        viewModel.startDiscovery()
    }

    LaunchedEffect(state.pin, state.step) {
        if (state.step == PairingStep.PIN && state.pin.length == PairingViewModel.PIN_LENGTH) {
            viewModel.submitPin()
        }
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .padding(horizontal = 20.dp, vertical = 12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (state.step != PairingStep.CLAIMING) {
                    IconButton(
                        onClick = {
                            viewModel.reset()
                            onBack()
                        },
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Outlined.ArrowBack,
                            contentDescription = stringResource(R.string.pairing_back),
                        )
                    }
                }
                Text(
                    text = stringResource(R.string.pairing_title),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(start = 4.dp),
                )
            }

            when (state.step) {
                PairingStep.FIND -> FindLaptopSection(
                    state = state,
                    onHostChange = viewModel::onHostChange,
                    onPortChange = viewModel::onPortChange,
                    onSelect = viewModel::selectLaptop,
                    onContinue = viewModel::continueWithManualHost,
                    onScan = {
                        scanLauncher.launch(
                            ScanOptions().apply {
                                setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                setPrompt("Scan the Maya QR code")
                                setBeepEnabled(false)
                                setOrientationLocked(false)
                            },
                        )
                    },
                )

                PairingStep.PIN -> PinSection(
                    state = state,
                    onPinChange = viewModel::onPinChange,
                    onPair = viewModel::submitPin,
                    onBack = viewModel::backToFind,
                )

                PairingStep.CLAIMING -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Text(
                            text = stringResource(R.string.pairing_pairing),
                            style = MaterialTheme.typography.bodyLarge,
                            modifier = Modifier.padding(top = 16.dp),
                        )
                    }
                }

                PairingStep.SUCCESS -> SuccessSection(
                    laptopName = state.paired?.name.orEmpty(),
                    onDone = {
                        viewModel.reset()
                        onDone()
                    },
                )
            }
        }
    }
}

@Composable
private fun FindLaptopSection(
    state: PairingUiState,
    onHostChange: (String) -> Unit,
    onPortChange: (String) -> Unit,
    onSelect: (DiscoveredLaptop) -> Unit,
    onContinue: () -> Unit,
    onScan: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize()) {
        Text(
            text = stringResource(R.string.pairing_find_title),
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(top = 12.dp),
        )
        Text(
            text = stringResource(R.string.pairing_find_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )

        if (state.discovering) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(top = 16.dp),
            ) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                Text(
                    text = stringResource(R.string.pairing_searching),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(start = 10.dp),
                )
            }
        }

        LazyColumn(modifier = Modifier.weight(1f).padding(top = 8.dp)) {
            items(state.laptops, key = { "${it.host}:${it.port}" }) { laptop ->
                LaptopRow(laptop = laptop, onClick = { onSelect(laptop) })
            }
            if (state.laptops.isEmpty() && !state.discovering) {
                item {
                    Text(
                        text = stringResource(R.string.pairing_no_laptops),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 12.dp),
                    )
                }
            }
        }

        state.errorMessage?.let { message ->
            ErrorCard(
                message = state.errorReason?.let { reasonText(it) } ?: message,
                detail = state.errorMessage,
            )
        }

        Text(
            text = stringResource(R.string.pairing_manual_title),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(top = 12.dp),
        )
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
        ) {
            OutlinedTextField(
                value = state.host,
                onValueChange = onHostChange,
                label = { Text(stringResource(R.string.pairing_host)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = state.port,
                onValueChange = onPortChange,
                label = { Text(stringResource(R.string.pairing_port)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.width(110.dp),
            )
        }

        Button(
            onClick = onContinue,
            enabled = state.host.isNotBlank(),
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 12.dp),
        ) {
            Text(text = stringResource(R.string.pairing_continue))
        }

        OutlinedButton(
            onClick = onScan,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp)
                .padding(bottom = 8.dp),
        ) {
            Icon(
                imageVector = Icons.Outlined.QrCodeScanner,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(text = stringResource(R.string.pairing_scan_qr))
        }
    }
}

@Composable
private fun LaptopRow(laptop: DiscoveredLaptop, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = MaterialTheme.shapes.small,
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
        ) {
            Icon(
                imageVector = Icons.Outlined.Computer,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
            Column(modifier = Modifier.padding(start = 12.dp)) {
                Text(text = laptop.name, style = MaterialTheme.typography.titleMedium)
                Text(
                    text = "${laptop.host}:${laptop.port}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun PinSection(
    state: PairingUiState,
    onPinChange: (String) -> Unit,
    onPair: () -> Unit,
    onBack: () -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(R.string.pairing_pin_title),
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(top = 24.dp),
        )
        Text(
            text = "${state.host}:${state.port}",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp),
        )
        Text(
            text = stringResource(R.string.pairing_pin_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 12.dp, bottom = 24.dp),
        )

        PinInput(pin = state.pin, onPinChange = onPinChange)

        state.errorMessage?.let { message ->
            ErrorCard(
                message = state.errorReason?.let { reasonText(it) } ?: message,
                detail = state.errorMessage,
            )
        }

        Button(
            onClick = onPair,
            enabled = state.pin.length == PairingViewModel.PIN_LENGTH,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 24.dp),
        ) {
            Text(text = stringResource(R.string.pairing_pair))
        }
        TextButton(onClick = onBack) {
            Text(text = stringResource(R.string.pairing_back))
        }
    }
}

@Composable
private fun SuccessSection(laptopName: String, onDone: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Filled.CheckCircle,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(72.dp),
        )
        Text(
            text = stringResource(R.string.pairing_success_title, laptopName),
            style = MaterialTheme.typography.headlineMedium,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 24.dp),
        )
        Button(
            onClick = onDone,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 32.dp),
        ) {
            Text(text = stringResource(R.string.pairing_start_chat))
        }
    }
}

@Composable
private fun ErrorCard(message: String, detail: String?) {
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 16.dp),
    ) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
            if (!detail.isNullOrBlank() && detail != message) {
                Text(
                    text = detail,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
    }
}

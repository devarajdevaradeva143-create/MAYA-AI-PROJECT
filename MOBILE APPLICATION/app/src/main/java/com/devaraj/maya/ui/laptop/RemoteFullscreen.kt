package com.devaraj.maya.ui.laptop

import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import android.view.WindowManager
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlin.math.min

/**
 * Maps a touch inside [boxSize] to normalized image coordinates, accounting for
 * the letterbox bars added by ContentScale.Fit. Returns null for bar touches.
 */
internal fun mapTouchToImage(offset: Offset, boxSize: IntSize, imageSize: IntSize): Offset? {
    if (boxSize.width <= 0 || boxSize.height <= 0) return null
    if (imageSize.width <= 0 || imageSize.height <= 0) return null
    val scale = min(
        boxSize.width.toFloat() / imageSize.width,
        boxSize.height.toFloat() / imageSize.height,
    )
    val drawWidth = imageSize.width * scale
    val drawHeight = imageSize.height * scale
    val left = (boxSize.width - drawWidth) / 2f
    val top = (boxSize.height - drawHeight) / 2f
    if (offset.x < left || offset.x > left + drawWidth) return null
    if (offset.y < top || offset.y > top + drawHeight) return null
    return Offset(
        ((offset.x - left) / drawWidth).coerceIn(0f, 1f),
        ((offset.y - top) / drawHeight).coerceIn(0f, 1f),
    )
}

/**
 * Live laptop screen with normalized touch callbacks. VM-free so the preview
 * and the fullscreen viewer share the same letterbox-accurate mapping.
 */
@Composable
fun RemoteScreen(
    bitmap: Bitmap?,
    loading: Boolean,
    error: String?,
    onTap: (Offset) -> Unit,
    onLongPress: (Offset) -> Unit,
    onDrag: (Offset) -> Unit,
    modifier: Modifier = Modifier,
) {
    var boxSize by remember { mutableStateOf(IntSize.Zero) }
    val imageSize = bitmap?.let { IntSize(it.width, it.height) } ?: IntSize.Zero

    Box(
        modifier = modifier
            .onSizeChanged { boxSize = it }
            .pointerInput(imageSize) {
                detectTapGestures(
                    onTap = { off -> mapTouchToImage(off, boxSize, imageSize)?.let(onTap) },
                    onLongPress = { off ->
                        mapTouchToImage(off, boxSize, imageSize)?.let(onLongPress)
                    },
                )
            }
            .pointerInput(imageSize) {
                detectDragGestures { change, _ ->
                    mapTouchToImage(change.position, boxSize, imageSize)?.let(onDrag)
                    change.consume()
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = "Laptop screen",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Fit,
            )
        } else if (loading) {
            CircularProgressIndicator()
        } else {
            Text(
                text = error ?: "No frame yet",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Fullscreen landscape viewer. Forces the activity orientation while open,
 * hides system bars, polls a sharper frame and restores everything on close.
 */
@Composable
fun FullscreenScreenDialog(
    state: RemoteUiState,
    vm: RemoteViewModel,
    onClose: () -> Unit,
) {
    val activity = LocalActivity.current
    var portrait by rememberSaveable { mutableStateOf(false) }
    var keysExpanded by rememberSaveable { mutableStateOf(false) }

    DisposableEffect(activity) {
        val originalOrientation = activity?.requestedOrientation
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        vm.setHighResScreen(true)
        onDispose {
            vm.setHighResScreen(false)
            activity?.requestedOrientation =
                originalOrientation ?: ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
        }
    }

    Dialog(
        onDismissRequest = onClose,
        properties = DialogProperties(
            usePlatformDefaultWidth = false,
            decorFitsSystemWindows = false,
        ),
    ) {
        val view = LocalView.current
        val dialogWindow = (view.parent as? DialogWindowProvider)?.window ?: activity?.window

        DisposableEffect(dialogWindow, view) {
            val controller = dialogWindow?.let { WindowCompat.getInsetsController(it, view) }
            controller?.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            controller?.hide(WindowInsetsCompat.Type.systemBars())
            dialogWindow?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            onDispose {
                dialogWindow?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                controller?.show(WindowInsetsCompat.Type.systemBars())
            }
        }

        MaterialTheme(colorScheme = darkColorScheme()) {
            Surface(modifier = Modifier.fillMaxSize(), color = Color.Black) {
                Box(modifier = Modifier.fillMaxSize()) {
                    RemoteScreen(
                        bitmap = state.screenBitmap,
                        loading = state.screenLoading,
                        error = state.screenError,
                        onTap = { p ->
                            vm.sendMove(p.x, p.y)
                            vm.click("left")
                        },
                        onLongPress = { p ->
                            vm.sendMove(p.x, p.y)
                            vm.click("right")
                        },
                        onDrag = { p -> vm.sendMove(p.x, p.y) },
                        modifier = Modifier.fillMaxSize(),
                    )

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(12.dp),
                    ) {
                        Text(
                            text = if (state.sessionActive) {
                                "${state.sessionExpiresIn}s"
                            } else {
                                "Session ended"
                            },
                            style = MaterialTheme.typography.labelMedium,
                            color = Color.White,
                        )
                        FilledTonalButton(
                            onClick = {
                                portrait = !portrait
                                activity?.requestedOrientation = if (portrait) {
                                    ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
                                } else {
                                    ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                                }
                            },
                        ) {
                            Text(if (portrait) "↔" else "↕")
                        }
                        FilledTonalButton(onClick = onClose) { Text("✕") }
                    }

                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .padding(12.dp),
                    ) {
                        if (keysExpanded) {
                            RemoteKeypad(
                                onKey = vm::sendKey,
                                modifier = Modifier
                                    .background(Color.Black.copy(alpha = 0.65f))
                                    .padding(6.dp),
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = { vm.sendKey("esc") }) { Text("Esc") }
                            OutlinedButton(onClick = { vm.sendKey("enter") }) { Text("Enter") }
                            OutlinedButton(onClick = { vm.sendKey("backspace") }) { Text("Bksp") }
                            OutlinedButton(onClick = { vm.sendKey("tab") }) { Text("Tab") }
                            TextButton(onClick = { keysExpanded = !keysExpanded }) {
                                Text(if (keysExpanded) "Hide keys" else "Keys")
                            }
                        }
                    }
                }
            }
        }
    }
}

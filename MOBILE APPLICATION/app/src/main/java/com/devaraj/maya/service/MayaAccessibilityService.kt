package com.devaraj.maya.service

import android.accessibilityservice.AccessibilityService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Rect
import android.os.Build
import android.provider.Settings
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction
import com.devaraj.maya.MayaApp
import com.devaraj.maya.R
import com.devaraj.maya.data.remote.InputEventDto
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Optional Accessibility service used only for local phone screen actions.
 * Nothing captured here ever leaves the device.
 */
class MayaAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile
        var instance: MayaAccessibilityService? = null
            private set

        fun componentName(context: Context): ComponentName =
            ComponentName(context, MayaAccessibilityService::class.java)

        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            ) ?: return false
            val target = componentName(context).flattenToString()
            return enabled.split(':').any { it.equals(target, ignoreCase = true) }
        }

        fun openSettings(context: Context) {
            runCatching {
                context.startActivity(
                    Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
    }

    private val handlerJob = SupervisorJob()
    private val handlerScope = CoroutineScope(Dispatchers.Main + handlerJob)

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        startPhoneRemoteIfEnabled()
    }

    /** Phone remote may have been enabled before this service was bound. */
    private fun startPhoneRemoteIfEnabled() {
        val app = applicationContext as? MayaApp ?: return
        handlerScope.launch {
            val settings = runCatching { app.container.settingsStore.settings.first() }.getOrNull() ?: return@launch
            if (!settings.phoneRemoteEnabled) return@launch
            PhoneRemoteForegroundService.start(this@MayaAccessibilityService)
            PhoneRemoteHttpServer.start(
                this@MayaAccessibilityService,
                this@MayaAccessibilityService,
                ScreenCaptureService.getInstance(),
            )
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Screen content is read on demand from the UI; no background capture.
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        instance = null
        handlerJob.cancel()
        super.onDestroy()
    }

    /** Reads visible text from the active window. Local only. */
    fun readVisibleText(maxChars: Int = 4000): String {
        val root = rootInActiveWindow ?: return ""
        val out = StringBuilder()
        collectText(root, out, maxChars, mutableSetOf())
        return out.toString().trim()
    }

    private fun collectText(
        node: AccessibilityNodeInfo?,
        out: StringBuilder,
        maxChars: Int,
        visited: MutableSet<String>,
    ) {
        if (node == null || out.length >= maxChars) return
        val key = "${node.viewIdResourceName}|${node.className}|${node.text}"
        if (!visited.add(key)) return
        val text = node.text?.toString()?.trim().orEmpty()
        val desc = node.contentDescription?.toString()?.trim().orEmpty()
        val value = text.ifBlank { desc }
        if (value.isNotBlank() && out.length + value.length + 1 <= maxChars) {
            if (out.isNotEmpty()) out.append('\n')
            out.append(value)
        }
        for (i in 0 until node.childCount) {
            collectText(node.getChild(i), out, maxChars, visited)
        }
    }

    /** Clicks the first node whose text or content description matches. */
    fun clickByText(query: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val needle = query.trim().lowercase()
        if (needle.isBlank()) return false
        val match = findClickable(root, needle, mutableSetOf()) ?: return false
        return match.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    private fun findClickable(
        node: AccessibilityNodeInfo?,
        needle: String,
        visited: MutableSet<String>,
    ): AccessibilityNodeInfo? {
        if (node == null) return null
        val key = "${node.viewIdResourceName}|${node.className}|${node.text}"
        if (!visited.add(key)) return null
        val text = node.text?.toString()?.trim()?.lowercase().orEmpty()
        val desc = node.contentDescription?.toString()?.trim()?.lowercase().orEmpty()
        if ((text.contains(needle) || desc.contains(needle)) && node.isClickable && node.isEnabled) {
            return node
        }
        for (i in 0 until node.childCount) {
            findClickable(node.getChild(i), needle, visited)?.let { return it }
        }
        return null
    }

    fun goBack() = performGlobalAction(GLOBAL_ACTION_BACK)
    fun goHome() = performGlobalAction(GLOBAL_ACTION_HOME)
    fun openRecents() = performGlobalAction(GLOBAL_ACTION_RECENTS)

    /** Injects an input event from the remote session. */
    fun injectInput(event: InputEventDto): Boolean {
        return when (event.type) {
            "click" -> injectClick(event.x, event.y)
            "swipe" -> injectSwipe(event.x, event.y, event.button?.toFloat() ?: 0f, event.dy?.toFloat() ?: 0f)
            "text" -> injectText(event.text ?: "")
            "key" -> injectKey(event.key ?: "")
            "scroll" -> injectScroll(0, event.dy ?: 0)
            else -> false
        }
    }

    private fun injectClick(x: Float?, y: Float?): Boolean {
        val root = rootInActiveWindow ?: return false
        val bounds = android.graphics.Rect()
        root.getBoundsInScreen(bounds)
        val pointX = (x ?: 0f) * bounds.width()
        val pointY = (y ?: 0f) * bounds.height()
        return performGestureAt(pointX, pointY)
    }

    private fun performGestureAt(x: Float, y: Float): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val gesture = android.accessibilityservice.GestureDescription.Builder()
        val path = android.graphics.Path()
        path.moveTo(x, y)
        path.lineTo(x, y)
        gesture.addStroke(android.accessibilityservice.GestureDescription.StrokeDescription(
            path, 0, 50
        ))
        return dispatchGesture(gesture.build(), object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: android.accessibilityservice.GestureDescription) {}
            override fun onCancelled(gestureDescription: android.accessibilityservice.GestureDescription) {}
        }, null)
    }

    private fun injectSwipe(x1: Float?, y1: Float?, x2: Float?, y2: Float?): Boolean {
        val root = rootInActiveWindow ?: return false
        val bounds = android.graphics.Rect()
        root.getBoundsInScreen(bounds)
        val startX = (x1 ?: 0f) * bounds.width()
        val startY = (y1 ?: 0f) * bounds.height()
        val endX = (x2 ?: 0f) * bounds.width()
        val endY = (y2 ?: 0f) * bounds.height()

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return false
        val gesture = android.accessibilityservice.GestureDescription.Builder()
        val path = android.graphics.Path()
        path.moveTo(startX, startY)
        path.lineTo(endX, endY)
        gesture.addStroke(android.accessibilityservice.GestureDescription.StrokeDescription(
            path, 0, 300
        ))
        return dispatchGesture(gesture.build(), object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: android.accessibilityservice.GestureDescription) {}
            override fun onCancelled(gestureDescription: android.accessibilityservice.GestureDescription) {}
        }, null)
    }

    private fun injectText(text: String): Boolean {
        if (text.isBlank()) return false
        val root = rootInActiveWindow ?: return false
        val focused = findFocusedEditable(root) ?: return false
        val args = android.os.Bundle()
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        return focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findFocusedEditable(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isFocused && node.isEditable) return node
        for (i in 0 until node.childCount) {
            findFocusedEditable(node.getChild(i))?.let { return it }
        }
        return null
    }

    private fun injectKey(key: String): Boolean {
        val keyCode = when (key.lowercase()) {
            "back" -> KeyEvent.KEYCODE_BACK
            "home" -> KeyEvent.KEYCODE_HOME
            "recents" -> KeyEvent.KEYCODE_APP_SWITCH
            "enter" -> KeyEvent.KEYCODE_ENTER
            "escape" -> KeyEvent.KEYCODE_ESCAPE
            "tab" -> KeyEvent.KEYCODE_TAB
            "space" -> KeyEvent.KEYCODE_SPACE
            "delete" -> KeyEvent.KEYCODE_DEL
            else -> return false
        }
        return performGlobalAction(when (keyCode) {
            KeyEvent.KEYCODE_BACK -> GLOBAL_ACTION_BACK
            KeyEvent.KEYCODE_HOME -> GLOBAL_ACTION_HOME
            KeyEvent.KEYCODE_APP_SWITCH -> GLOBAL_ACTION_RECENTS
            else -> return false
        })
    }

    private fun injectScroll(dx: Int, dy: Int): Boolean {
        val root = rootInActiveWindow ?: return false
        return findScrollableNode(root)?.let { node ->
            val action = when {
                dy > 0 -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                dy < 0 -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                dx > 0 -> 0x8000 // ACTION_SCROLL_RIGHT
                dx < 0 -> 0x4000 // ACTION_SCROLL_LEFT
                else -> return@let false
            }
            node.performAction(action)
        } ?: false
    }

    private fun findScrollableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        val actions = node.getActionList() ?: return null
        val isScrollable = actions.any { it.id in setOf(
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD,
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD,
            0x8000, // ACTION_SCROLL_RIGHT
            0x4000, // ACTION_SCROLL_LEFT
        ) }
        if (isScrollable) return node
        for (i in 0 until node.childCount) {
            findScrollableNode(node.getChild(i))?.let { return it }
        }
        return null
    }

    fun description(): String = getString(R.string.accessibility_service_description)
}

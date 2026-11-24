package com.devaraj.maya.control.hybrid

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

/**
 * HYBRID mode control bus (mirrors JARVIS/custom/tools/hybrid_controller.py).
 *
 * Coordinates who currently "owns" control (USER vs AI) and queues AI tasks
 * so they never fight the user for input. User always wins conflicts.
 */
class HybridController {

    enum class Controller { NONE, USER, AI }

    enum class TaskStatus { QUEUED, RUNNING, DONE, CANCELLED, FAILED }

    data class Task(
        val id: String,
        val description: String,
        val status: TaskStatus = TaskStatus.QUEUED,
        val createdAt: Long = System.currentTimeMillis(),
        val startedAt: Long? = null,
        val finishedAt: Long? = null,
        val result: String = "",
        val error: String = "",
    )

    data class Status(
        val controller: Controller,
        val aiBusy: Boolean,
        val queuedTasks: Int,
        val runningTask: String?,
        val conflicts: Int,
        val lastTakeover: Long?,
    )

    private val lock = Any()
    private var controller: Controller = Controller.NONE
    private val tasks = LinkedHashMap<String, Task>()
    private val taskOrder = mutableListOf<String>()
    private var running: String? = null
    private var conflicts: Int = 0
    private var lastTakeover: Long? = null
    private var aiPaused: Boolean = false

    private val _status = MutableStateFlow(
        Status(Controller.NONE, false, 0, null, 0, null)
    )
    val status: StateFlow<Status> = _status.asStateFlow()

    private fun emit() {
        val snap = Status(
            controller = controller,
            aiBusy = running != null,
            queuedTasks = tasks.values.count { it.status == TaskStatus.QUEUED },
            runningTask = running,
            conflicts = conflicts,
            lastTakeover = lastTakeover,
        )
        _status.value = snap
    }

    /** Request control. Returns true if granted. User always wins. */
    fun acquire(ctrl: Controller): Boolean {
        synchronized(lock) {
            if (ctrl == Controller.NONE) return false
            if (ctrl == Controller.USER) {
                if (controller == Controller.AI) {
                    conflicts++
                    aiPaused = true
                    running?.let { id ->
                        tasks[id] = tasks[id]!!.copy(
                            status = TaskStatus.CANCELLED,
                            finishedAt = System.currentTimeMillis(),
                        )
                        running = null
                    }
                }
                controller = Controller.USER
                lastTakeover = System.currentTimeMillis()
                emit()
                return true
            }
            // AI requests control
            if (controller == Controller.NONE) {
                controller = Controller.AI
                aiPaused = false
                emit()
                return true
            }
            if (controller == Controller.AI) return true
            // user holds control -> AI cannot acquire
            conflicts++
            return false
        }
    }

    fun release(ctrl: Controller): Boolean {
        synchronized(lock) {
            if (controller != ctrl) return false
            controller = Controller.NONE
            if (ctrl == Controller.AI) aiPaused = false
            emit()
            return true
        }
    }

    fun takeover(ctrl: Controller = Controller.USER): Boolean = acquire(ctrl)

    fun currentController(): Controller = synchronized(lock) { controller }

    fun isControlledBy(ctrl: Controller): Boolean = synchronized(lock) { controller == ctrl }

    fun queueTask(description: String): String {
        val id = "t_" + UUID.randomUUID().toString().replace("-", "").take(8)
        synchronized(lock) {
            tasks[id] = Task(id = id, description = description)
            taskOrder.add(id)
        }
        emit()
        return id
    }

    fun nextTask(): Task? {
        synchronized(lock) {
            if (controller != Controller.AI || aiPaused) return null
            if (running != null) return null
            for (id in taskOrder) {
                val t = tasks[id]
                if (t != null && t.status == TaskStatus.QUEUED) {
                    tasks[id] = t.copy(status = TaskStatus.RUNNING, startedAt = System.currentTimeMillis())
                    running = id
                    emit()
                    return tasks[id]
                }
            }
            return null
        }
    }

    fun completeTask(taskId: String, result: String = "", ok: Boolean = true): Boolean {
        synchronized(lock) {
            val t = tasks[taskId] ?: return false
            tasks[taskId] = t.copy(
                status = if (ok) TaskStatus.DONE else TaskStatus.FAILED,
                result = if (ok) result else t.result,
                error = if (ok) t.error else result,
                finishedAt = System.currentTimeMillis(),
            )
            if (running == taskId) running = null
            emit()
            return true
        }
    }

    fun cancelTask(taskId: String): Boolean {
        synchronized(lock) {
            val t = tasks[taskId] ?: return false
            if (t.status == TaskStatus.DONE || t.status == TaskStatus.FAILED ||
                t.status == TaskStatus.CANCELLED
            ) return false
            tasks[taskId] = t.copy(status = TaskStatus.CANCELLED, finishedAt = System.currentTimeMillis())
            if (running == taskId) running = null
            emit()
            return true
        }
    }

    fun cancelAllAi(): Int {
        var n = 0
        synchronized(lock) {
            for (id in tasks.keys.toList()) {
                val t = tasks[id] ?: continue
                if (t.status == TaskStatus.QUEUED || t.status == TaskStatus.RUNNING) {
                    tasks[id] = t.copy(status = TaskStatus.CANCELLED, finishedAt = System.currentTimeMillis())
                    n++
                }
            }
            running = null
            aiPaused = true
        }
        emit()
        return n
    }

    fun listTasks(): List<Task> = synchronized(lock) {
        taskOrder.mapNotNull { tasks[it] }
    }

    fun getTask(taskId: String): Task? = synchronized(lock) { tasks[taskId] }

    fun aiCanAct(): Boolean = synchronized(lock) {
        if (aiPaused) return false
        if (controller == Controller.USER) return false
        return true
    }

    fun reset() {
        synchronized(lock) {
            controller = Controller.NONE
            tasks.clear()
            taskOrder.clear()
            running = null
            conflicts = 0
            aiPaused = false
            lastTakeover = null
        }
        emit()
    }
}

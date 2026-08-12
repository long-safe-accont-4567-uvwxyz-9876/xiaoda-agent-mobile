package com.xiaoda.agent

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Owns the in-process Python backend for the lifetime of the Android app process. */
object LocalBackendRuntime {
    private const val PORT = 8765
    val endpoint: String = "http://127.0.0.1:$PORT"

    sealed interface State {
        data object Starting : State
        data object Ready : State
        data class Failed(val detail: String) : State
    }

    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "xiaoda-backend-launcher").apply { isDaemon = true }
    }
    private val launchStarted = AtomicBoolean(false)
    private val listeners = CopyOnWriteArrayList<(State) -> Unit>()
    @Volatile private var state: State = State.Starting

    fun start(context: Context, listener: (State) -> Unit) {
        listeners += listener
        listener(state)
        if (!launchStarted.compareAndSet(false, true)) return
        executor.execute {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
                val python = Python.getInstance()
                val module = python.getModule("xiaoda_mobile_runtime")
                python.getModule("tools.android_browser_tools").callAttr(
                    "set_android_browser_bridge",
                    PyObject.fromJava(AndroidBrowserAutomation),
                )
                module.callAttr(
                    "start_server",
                    context.filesDir.absolutePath,
                    context.noBackupFilesDir.absolutePath,
                    context.cacheDir.absolutePath,
                    PORT,
                )
                waitUntilListening(module)
            } catch (error: Throwable) {
                publish(State.Failed(error.stackTraceToString().take(12_000)))
            }
        }
    }

    private fun waitUntilListening(module: com.chaquo.python.PyObject) {
        repeat(240) {
            try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress("127.0.0.1", PORT), 250)
                }
                publish(State.Ready)
                return
            } catch (_: Exception) {
                Thread.sleep(250)
            }
        }
        val pythonError = runCatching { module.callAttr("startup_error").toString() }.getOrDefault("")
        publish(State.Failed(pythonError.ifBlank { "本地后端在 60 秒内未能启动" }))
    }

    private fun publish(next: State) {
        state = next
        listeners.forEach { listener -> listener(next) }
        if (next !is State.Starting) listeners.clear()
    }
}

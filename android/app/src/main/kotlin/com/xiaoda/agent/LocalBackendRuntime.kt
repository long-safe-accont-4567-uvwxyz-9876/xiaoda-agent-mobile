package com.xiaoda.agent

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
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
                val bundledConfigDir = extractConfigAssets(context)
                if (!Python.isStarted()) Python.start(AndroidPlatform(context.applicationContext))
                val python = Python.getInstance()
                val module = python.getModule("xiaoda_mobile_runtime")
                // Configure HOME / data dirs BEFORE importing tools.android_browser_tools:
                // that module transitively imports config.py, which resolves Path.home()-based
                // paths at import time. If HOME is still Chaquopy's default (app files dir),
                // the backend would write to files/.ai-agent/ instead of files/xiaoda/.ai-agent/.
                module.callAttr(
                    "configure_environment",
                    context.filesDir.absolutePath,
                    context.noBackupFilesDir.absolutePath,
                    context.cacheDir.absolutePath,
                    bundledConfigDir.absolutePath,
                )
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
                    bundledConfigDir.absolutePath,
                )
                waitUntilListening(module)
            } catch (error: Throwable) {
                publish(State.Failed(error.stackTraceToString().take(12_000)))
            }
        }
    }

    /**
     * Copies the bundled config/ resources (agent.json5, security_patterns.yaml,
     * agents/, workspace/, ...) from APK assets into app-private storage so the
     * Python backend's config._init_user_resources can seed the user config dir.
     * Returns the destination directory (guaranteed to exist).
     */
    private fun extractConfigAssets(context: Context): File {
        val dest = File(context.filesDir, "xiaoda/bundled_config")
        copyAssetTree(context, "config", dest)
        return dest
    }

    private fun copyAssetTree(context: Context, assetPath: String, dest: File) {
        val children = try {
            context.assets.list(assetPath) ?: return
        } catch (_: Exception) {
            return
        }
        if (children.isEmpty()) return
        dest.mkdirs()
        for (child in children) {
            val childAsset = if (assetPath.isEmpty()) child else "$assetPath/$child"
            val childDest = File(dest, child)
            val grandChildren = try {
                context.assets.list(childAsset) ?: emptyArray()
            } catch (_: Exception) {
                emptyArray()
            }
            if (grandChildren.isNotEmpty()) {
                copyAssetTree(context, childAsset, childDest)
            } else {
                context.assets.open(childAsset).use { input ->
                    childDest.outputStream().use { output -> input.copyTo(output) }
                }
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

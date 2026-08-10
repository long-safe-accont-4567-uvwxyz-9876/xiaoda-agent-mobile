package com.xiaoda.agent.terminal

import android.system.Os
import android.system.OsConstants
import com.termux.terminal.TerminalSession
import com.termux.terminal.TerminalSessionClient
import java.io.File

object TermuxRuntimeComponent {
    const val NAME = "termux/terminal-emulator"
    const val VERSION = "0.118.3"
    const val COMMIT = "5b657c6adf4304e5198951ce815fe0205dcac29c"
    const val LICENSE = "Apache-2.0"
    val supportedAbis = setOf("arm64-v8a", "x86_64")
}

data class TermuxCommand(
    val executable: String,
    val workingDirectory: String,
    val arguments: List<String>,
    val environment: Map<String, String>,
)

object TermuxCommandPolicy {
    private val environmentName = Regex("[A-Z][A-Z0-9_]{0,63}")

    fun isAllowed(command: TermuxCommand, allowedRoots: Collection<File>): Boolean {
        val executable = canonical(command.executable) ?: return false
        val cwd = canonical(command.workingDirectory) ?: return false
        val roots = allowedRoots.mapNotNull { canonical(it.path) }
        if (roots.isEmpty() || roots.none { executable.isInside(it) } || roots.none { cwd.isInside(it) }) return false
        if (command.arguments.isEmpty() || command.arguments.first() != executable.path) return false
        if (command.arguments.size > 64 || command.arguments.any { it.isBlank() || it.length > 4096 || it.any(Char::isISOControl) }) return false
        if (!RemoteCliPolicy.environmentIsSafe(command.environment)) return false
        return command.environment.all { (name, value) ->
            environmentName.matches(name) && value.length <= 8192 && value.none(Char::isISOControl)
        }
    }

    private fun canonical(path: String): File? = runCatching { File(path).canonicalFile }.getOrNull()
    private fun File.isInside(root: File): Boolean = path == root.path || path.startsWith(root.path + File.separator)
}

fun interface ProcessGroupSignalSender {
    fun send(processGroupId: Int, signal: Int)
}

class ProcessTreeTerminator(
    private val signalSender: ProcessGroupSignalSender,
    private val sleeper: (Long) -> Unit = Thread::sleep,
) {
    fun terminate(process: RuntimeProcessControl, graceMillis: Long = 750) {
        if (!process.isRunning()) return
        signalSender.send(process.pid, OsConstants.SIGTERM)
        if (graceMillis > 0) sleeper(graceMillis)
        if (process.isRunning()) signalSender.send(process.pid, OsConstants.SIGKILL)
    }
}

interface RuntimeProcessControl {
    val pid: Int
    fun isRunning(): Boolean
    fun stop()
}

interface TermuxRuntimeListener {
    fun onOutputChanged() = Unit
    fun onExited(exitStatus: Int) = Unit
}

class TermuxPtyRuntime(
    private val allowedRoots: Collection<File>,
    private val signalSender: ProcessGroupSignalSender = ProcessGroupSignalSender { processGroupId, signal ->
        Os.kill(-processGroupId, signal)
    },
) : RuntimeLauncher {
    fun launch(command: TermuxCommand): RuntimeProcessControl = launch(command, object : TermuxRuntimeListener {})

    override fun launch(command: TermuxCommand, listener: TermuxRuntimeListener): RuntimeProcessControl {
        require(TermuxCommandPolicy.isAllowed(command, allowedRoots)) { "termux command rejected by policy" }
        val session = TerminalSession(
            command.executable,
            command.workingDirectory,
            command.arguments.toTypedArray(),
            command.environment.map { (key, value) -> "$key=$value" }.toTypedArray(),
            2_000,
            RuntimeSessionClient(listener) { session ->
                listener.onExited(session.exitStatus)
            },
        )
        val handle = TermuxProcessHandle(session, ProcessTreeTerminator(signalSender))
        session.updateSize(80, 24, 0, 0)
        return handle
    }

    private class RuntimeSessionClient(
        private val listener: TermuxRuntimeListener,
        private val finished: (TerminalSession) -> Unit,
    ) : TerminalSessionClient {
        override fun onTextChanged(changedSession: TerminalSession) = listener.onOutputChanged()
        override fun onTitleChanged(changedSession: TerminalSession) = Unit
        override fun onSessionFinished(finishedSession: TerminalSession) = finished(finishedSession)
        override fun onCopyTextToClipboard(session: TerminalSession, text: String) = Unit
        override fun onPasteTextFromClipboard(session: TerminalSession) = Unit
        override fun onBell(session: TerminalSession) = Unit
        override fun onColorsChanged(session: TerminalSession) = Unit
        override fun onTerminalCursorStateChange(state: Boolean) = Unit
        override fun getTerminalCursorStyle(): Int? = null
        override fun logError(tag: String, message: String) = Unit
        override fun logWarn(tag: String, message: String) = Unit
        override fun logInfo(tag: String, message: String) = Unit
        override fun logDebug(tag: String, message: String) = Unit
        override fun logVerbose(tag: String, message: String) = Unit
        override fun logStackTraceWithMessage(tag: String, message: String, e: Exception) = Unit
        override fun logStackTrace(tag: String, e: Exception) = Unit
    }
}

private class TermuxProcessHandle(
    private val session: TerminalSession,
    private val terminator: ProcessTreeTerminator,
) : RuntimeProcessControl {
    override val pid: Int get() = session.pid
    override fun isRunning(): Boolean = session.isRunning
    override fun stop() = terminator.terminate(this)
}

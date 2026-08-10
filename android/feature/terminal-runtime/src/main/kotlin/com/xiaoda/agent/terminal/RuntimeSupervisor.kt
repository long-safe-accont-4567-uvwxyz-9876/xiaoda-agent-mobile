package com.xiaoda.agent.terminal

import java.net.URI


data class RemoteCliConfig(val httpsEndpoint: String, val wssEndpoint: String, val protocolVersion: String)
data class RuntimeHandshake(val instanceNonce: String, val protocolVersion: String)
enum class RuntimeState { DISABLED, STOPPED, RUNNING, BACKOFF, FAILED }
data class RuntimeSnapshot(
    val state: RuntimeState,
    val restartAllowed: Boolean,
    val pid: Int? = null,
    val nextRestartDelayMillis: Long? = null,
    val lastExitStatus: Int? = null,
)

object RemoteCliPolicy {
    private val forbiddenKeys = Regex("(?i)(provider|openai|anthropic|mimo|api)[_-]?key")
    fun isAllowed(config: RemoteCliConfig): Boolean = secureRemote(config.httpsEndpoint, "https") && secureRemote(config.wssEndpoint, "wss")
    fun environmentIsSafe(environment: Map<String, String>): Boolean = environment.keys.none { forbiddenKeys.containsMatchIn(it) }
    private fun secureRemote(value: String, scheme: String): Boolean {
        val uri = runCatching { URI(value) }.getOrNull() ?: return false
        val host = uri.host?.lowercase()?.trimEnd('.')?.trim('[', ']') ?: return false
        return uri.scheme == scheme &&
            !isLocalOrPrivateHost(host) &&
            uri.userInfo == null &&
            uri.rawQuery == null &&
            uri.rawFragment == null
    }

    private fun isLocalOrPrivateHost(host: String): Boolean {
        if (host in setOf("localhost", "10.0.2.2") || host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal") || host.endsWith(".lan") || host.endsWith(".home.arpa")) return true
        val ipv4 = host.split('.').mapNotNull(String::toIntOrNull)
        if (ipv4.size == 4 && ipv4.all { it in 0..255 }) {
            val (a, b) = ipv4
            return a == 0 || a == 10 || a == 127 ||
                a == 100 && b in 64..127 ||
                a == 169 && b == 254 ||
                a == 172 && b in 16..31 ||
                a == 192 && b == 168 ||
                a == 198 && b in 18..19 ||
                a >= 224
        }
        if (':' in host) {
            val normalized = host.lowercase()
            return normalized == "::" || normalized == "::1" || normalized.startsWith("fc") || normalized.startsWith("fd") || normalized.startsWith("fe8") || normalized.startsWith("fe9") || normalized.startsWith("fea") || normalized.startsWith("feb")
        }
        return '.' !in host
    }
}

class CrashBackoff(private val maxRestarts: Int, private val baseDelayMillis: Long) {
    private var crashes = 0
    fun recordCrash(): Long? {
        if (crashes >= maxRestarts) return null
        return baseDelayMillis * (1L shl crashes++)
    }
}

fun interface RuntimeLauncher {
    fun launch(command: TermuxCommand, listener: TermuxRuntimeListener): RuntimeProcessControl
}

fun interface RuntimeScheduler {
    fun schedule(delayMillis: Long, task: () -> Unit)
}

object RemoteCliCommandFactory {
    fun create(
        executable: String,
        workingDirectory: String,
        config: RemoteCliConfig,
        handshake: RuntimeHandshake,
        baseEnvironment: Map<String, String>,
    ): TermuxCommand {
        val environment = baseEnvironment + mapOf(
            "XIAODA_HTTPS_ENDPOINT" to config.httpsEndpoint,
            "XIAODA_WSS_ENDPOINT" to config.wssEndpoint,
            "XIAODA_PROTOCOL_VERSION" to handshake.protocolVersion,
            "XIAODA_INSTANCE_NONCE" to handshake.instanceNonce,
        )
        return TermuxCommand(
            executable = executable,
            workingDirectory = workingDirectory,
            arguments = listOf(
                executable,
                "--https-endpoint", config.httpsEndpoint,
                "--wss-endpoint", config.wssEndpoint,
                "--protocol-version", handshake.protocolVersion,
                "--instance-nonce", handshake.instanceNonce,
            ),
            environment = environment,
        )
    }
}

class RuntimeSupervisor(
    private val instanceNonce: String,
    private val backoff: CrashBackoff = CrashBackoff(maxRestarts = 3, baseDelayMillis = 1_000),
    private val scheduler: RuntimeScheduler = RuntimeScheduler { delayMillis, task ->
        Thread {
            Thread.sleep(delayMillis)
            task()
        }.start()
    },
) {
    private var state = RuntimeState.STOPPED
    private var process: RuntimeProcessControl? = null
    private var request: LaunchRequest? = null
    private var userStopped = false
    private var nextRestartDelayMillis: Long? = null
    private var lastExitStatus: Int? = null

    fun start(
        config: RemoteCliConfig,
        executable: String,
        workingDirectory: String,
        environment: Map<String, String>,
        launcher: RuntimeLauncher,
    ): Boolean = synchronized(this) {
        if (state == RuntimeState.RUNNING || state == RuntimeState.BACKOFF) return false
        if (!hasValidHandshake(config) || !RemoteCliPolicy.isAllowed(config) || !RemoteCliPolicy.environmentIsSafe(environment)) return false
        request = LaunchRequest(config, executable, workingDirectory, environment, launcher)
        userStopped = false
        lastExitStatus = null
        launchLocked()
    }

    fun stop() {
        val running = synchronized(this) {
            userStopped = true
            nextRestartDelayMillis = null
            state = RuntimeState.STOPPED
            process.also { process = null }
        }
        running?.stop()
    }

    @Synchronized
    fun status() = RuntimeSnapshot(
        state = state,
        restartAllowed = !userStopped && state != RuntimeState.RUNNING && state != RuntimeState.FAILED,
        pid = process?.pid,
        nextRestartDelayMillis = nextRestartDelayMillis,
        lastExitStatus = lastExitStatus,
    )

    @Synchronized
    fun handshake() = RuntimeHandshake(instanceNonce, requireNotNull(request).config.protocolVersion)

    private fun launchLocked(): Boolean {
        val current = request ?: return false
        val handshake = RuntimeHandshake(instanceNonce, current.config.protocolVersion)
        val command = RemoteCliCommandFactory.create(
            current.executable,
            current.workingDirectory,
            current.config,
            handshake,
            current.environment,
        )
        return runCatching {
            current.launcher.launch(command, object : TermuxRuntimeListener {
                override fun onExited(exitStatus: Int) = processExited(exitStatus)
            })
        }.fold(
            onSuccess = {
                process = it
                state = RuntimeState.RUNNING
                nextRestartDelayMillis = null
                true
            },
            onFailure = {
                process = null
                state = RuntimeState.FAILED
                false
            },
        )
    }

    private fun processExited(exitStatus: Int) {
        val restartDelay = synchronized(this) {
            process = null
            lastExitStatus = exitStatus
            if (userStopped) {
                state = RuntimeState.STOPPED
                nextRestartDelayMillis = null
                return
            }
            val delay = backoff.recordCrash()
            if (delay == null) {
                state = RuntimeState.FAILED
                nextRestartDelayMillis = null
                return
            }
            state = RuntimeState.BACKOFF
            nextRestartDelayMillis = delay
            delay
        }
        scheduler.schedule(restartDelay) { restartAfterBackoff() }
    }

    private fun restartAfterBackoff() = synchronized(this) {
        if (!userStopped && state == RuntimeState.BACKOFF) launchLocked()
        Unit
    }

    private fun hasValidHandshake(config: RemoteCliConfig): Boolean =
        instanceNonce.length in 8..128 &&
            instanceNonce.none(Char::isISOControl) &&
            config.protocolVersion.matches(Regex("[A-Za-z0-9._-]{1,32}"))

    private data class LaunchRequest(
        val config: RemoteCliConfig,
        val executable: String,
        val workingDirectory: String,
        val environment: Map<String, String>,
        val launcher: RuntimeLauncher,
    )
}

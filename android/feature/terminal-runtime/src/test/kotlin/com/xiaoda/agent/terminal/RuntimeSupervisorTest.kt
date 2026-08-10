package com.xiaoda.agent.terminal

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RuntimeSupervisorTest {
    private val config = RemoteCliConfig("https://server.example", "wss://server.example/ws", "1")

    @Test
    fun `supervisor launches one real process contract and user stop kills it`() {
        val process = FakeProcess(4242)
        var launchedCommand: TermuxCommand? = null
        val launcher = RuntimeLauncher { command, _ ->
            launchedCommand = command
            process
        }
        val supervisor = RuntimeSupervisor("instance-nonce")

        assertTrue(supervisor.start(config, "/app/bin/xiaoda-cli", "/app", mapOf("HOME" to "/app"), launcher))
        assertFalse(supervisor.start(config, "/app/bin/xiaoda-cli", "/app", emptyMap(), launcher))
        assertEquals(RuntimeState.RUNNING, supervisor.status().state)
        assertEquals(4242, supervisor.status().pid)
        assertEquals("instance-nonce", supervisor.handshake().instanceNonce)
        assertEquals("/app/bin/xiaoda-cli", launchedCommand?.arguments?.first())
        assertTrue(launchedCommand?.arguments?.containsAll(listOf(config.httpsEndpoint, config.wssEndpoint, "instance-nonce")) == true)

        supervisor.stop()

        assertTrue(process.stopped)
        assertEquals(RuntimeState.STOPPED, supervisor.status().state)
        assertFalse(supervisor.status().restartAllowed)
    }

    @Test
    fun `crashes use finite exponential backoff and then fail closed`() {
        val scheduled = ArrayDeque<Pair<Long, () -> Unit>>()
        val listeners = mutableListOf<TermuxRuntimeListener>()
        var pid = 100
        val launcher = RuntimeLauncher { _, listener ->
            listeners += listener
            FakeProcess(pid++)
        }
        val supervisor = RuntimeSupervisor(
            "instance-nonce",
            CrashBackoff(maxRestarts = 2, baseDelayMillis = 100),
            RuntimeScheduler { delay, task -> scheduled.addLast(delay to task) },
        )

        assertTrue(supervisor.start(config, "/app/bin/xiaoda-cli", "/app", emptyMap(), launcher))
        listeners.last().onExited(7)
        assertEquals(RuntimeState.BACKOFF, supervisor.status().state)
        assertEquals(100L, supervisor.status().nextRestartDelayMillis)
        assertEquals(7, supervisor.status().lastExitStatus)
        assertEquals(100L, scheduled.removeFirst().first)
        scheduled.addFirst(100L to { }) // preserve a task handle for the explicit restart below
        scheduled.removeFirst()

        // Replay the scheduled restart captured by a fresh crash.
        val tasks = mutableListOf<() -> Unit>()
        val secondSupervisor = RuntimeSupervisor(
            "instance-nonce",
            CrashBackoff(maxRestarts = 1, baseDelayMillis = 50),
            RuntimeScheduler { _, task -> tasks += task },
        )
        val secondListeners = mutableListOf<TermuxRuntimeListener>()
        val secondLauncher = RuntimeLauncher { _, listener ->
            secondListeners += listener
            FakeProcess(200 + secondListeners.size)
        }
        assertTrue(secondSupervisor.start(config, "/app/bin/xiaoda-cli", "/app", emptyMap(), secondLauncher))
        secondListeners.last().onExited(1)
        tasks.removeAt(0).invoke()
        assertEquals(RuntimeState.RUNNING, secondSupervisor.status().state)
        secondListeners.last().onExited(2)
        assertEquals(RuntimeState.FAILED, secondSupervisor.status().state)
        assertFalse(secondSupervisor.status().restartAllowed)
    }

    @Test
    fun `remote cli rejects local services provider keys and unbounded restarts`() {
        assertFalse(RemoteCliPolicy.isAllowed(RemoteCliConfig("http://127.0.0.1:8080", "ws://127.0.0.1/ws", "1")))
        assertFalse(RemoteCliPolicy.environmentIsSafe(mapOf("OPENAI_API_KEY" to "secret")))
        assertTrue(RemoteCliPolicy.environmentIsSafe(mapOf("XIAODA_SESSION_HANDLE" to "opaque")))

        val backoff = CrashBackoff(maxRestarts = 3, baseDelayMillis = 1000)
        assertEquals(1000L, backoff.recordCrash())
        assertEquals(2000L, backoff.recordCrash())
        assertEquals(4000L, backoff.recordCrash())
        assertEquals(null, backoff.recordCrash())
    }

    @Test
    fun `remote cli rejects ambiguous endpoints and invalid handshake input`() {
        assertFalse(RemoteCliPolicy.isAllowed(RemoteCliConfig("https://server.example?token=secret", "wss://server.example/ws", "1")))
        assertFalse(RemoteCliPolicy.isAllowed(RemoteCliConfig("https://10.0.0.8", "wss://10.0.0.8/ws", "1")))
        assertFalse(RemoteCliPolicy.isAllowed(RemoteCliConfig("https://console.local", "wss://console.local/ws", "1")))
        assertTrue(RemoteCliPolicy.isAllowed(config))
        val launcher = RuntimeLauncher { _, _ -> FakeProcess(1) }
        assertFalse(RuntimeSupervisor("short").start(config, "/app/bin/cli", "/app", emptyMap(), launcher))
        assertFalse(RuntimeSupervisor("1234567890123456").start(config.copy(protocolVersion = ""), "/app/bin/cli", "/app", emptyMap(), launcher))
    }

    @Test
    fun `remote cli command factory injects nonce protocol and only remote endpoints`() {
        val command = RemoteCliCommandFactory.create(
            "/app/bin/xiaoda-cli",
            "/app",
            config,
            RuntimeHandshake("instance-nonce", "1"),
            mapOf("HOME" to "/app"),
        )

        assertEquals("https://server.example", command.environment["XIAODA_HTTPS_ENDPOINT"])
        assertEquals("wss://server.example/ws", command.environment["XIAODA_WSS_ENDPOINT"])
        assertEquals("instance-nonce", command.environment["XIAODA_INSTANCE_NONCE"])
        assertFalse(command.arguments.any { it.contains("127.0.0.1") || it.contains("localhost") })
    }

    private class FakeProcess(override val pid: Int) : RuntimeProcessControl {
        var stopped = false
        override fun isRunning() = !stopped
        override fun stop() { stopped = true }
    }
}

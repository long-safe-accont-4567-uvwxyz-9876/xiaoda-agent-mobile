package com.xiaoda.agent.terminal

import android.system.OsConstants
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TermuxPtyRuntimeTest {
    @Test
    fun `component provenance is frozen to official upstream`() {
        assertEquals("termux/terminal-emulator", TermuxRuntimeComponent.NAME)
        assertEquals("0.118.3", TermuxRuntimeComponent.VERSION)
        assertEquals("Apache-2.0", TermuxRuntimeComponent.LICENSE)
        assertEquals(setOf("arm64-v8a", "x86_64"), TermuxRuntimeComponent.supportedAbis)
    }

    @Test
    fun `command policy allows only app private executable and safe environment`() {
        val root = File("build/runtime-root").canonicalFile
        val executable = File(root, "bin/xiaoda-cli").canonicalFile
        val command = TermuxCommand(
            executable.path,
            root.path,
            listOf(executable.path, "--remote", "https://server.example"),
            mapOf("XIAODA_INSTANCE_NONCE" to "nonce-12345678"),
        )

        assertTrue(TermuxCommandPolicy.isAllowed(command, listOf(root)))
        assertFalse(TermuxCommandPolicy.isAllowed(command.copy(executable = File(root.parentFile, "escape").path), listOf(root)))
        assertFalse(TermuxCommandPolicy.isAllowed(command.copy(environment = mapOf("OPENAI_API_KEY" to "secret")), listOf(root)))
        assertFalse(TermuxCommandPolicy.isAllowed(command.copy(arguments = listOf("different-argv-zero")), listOf(root)))
    }

    @Test
    fun `process tree terminator uses process group term then kill`() {
        val signals = mutableListOf<Pair<Int, Int>>()
        var running = true
        val process = object : RuntimeProcessControl {
            override val pid = 4242
            override fun isRunning() = running
            override fun stop() = Unit
        }
        val terminator = ProcessTreeTerminator(
            ProcessGroupSignalSender { pid, signal -> signals += pid to signal },
            sleeper = { running = true },
        )

        terminator.terminate(process, graceMillis = 1)

        assertEquals(listOf(4242 to OsConstants.SIGTERM, 4242 to OsConstants.SIGKILL), signals)
    }

    @Test
    fun `process tree terminator avoids kill after graceful exit`() {
        val signals = mutableListOf<Pair<Int, Int>>()
        var running = true
        val process = object : RuntimeProcessControl {
            override val pid = 7
            override fun isRunning() = running
            override fun stop() = Unit
        }
        val terminator = ProcessTreeTerminator(
            ProcessGroupSignalSender { pid, signal -> signals += pid to signal },
            sleeper = { running = false },
        )

        terminator.terminate(process, graceMillis = 1)

        assertEquals(listOf(7 to OsConstants.SIGTERM), signals)
    }
}

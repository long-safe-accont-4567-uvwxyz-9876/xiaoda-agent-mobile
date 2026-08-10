package com.xiaoda.agent.terminal

import android.os.SystemClock
import android.system.Os
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class TermuxRuntimeIntegrationTest {
    @Test
    fun termuxPtyStartsAndReclaimsTheRealProcessGroup() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val childPidFile = File(context.cacheDir, "termux-child-${System.nanoTime()}.pid")
        val finished = CountDownLatch(1)
        lateinit var process: RuntimeProcessControl
        val command = TermuxCommand(
            executable = "/system/bin/sh",
            workingDirectory = context.filesDir.absolutePath,
            arguments = listOf(
                "/system/bin/sh",
                "-c",
                "/system/bin/sleep 30 & child=$!; echo ${'$'}child > '${childPidFile.absolutePath}'; wait",
            ),
            environment = mapOf(
                "HOME" to context.filesDir.absolutePath,
                "PATH" to "/system/bin",
                "TERM" to "xterm-256color",
                "XIAODA_INSTANCE_NONCE" to "instrumented-nonce",
            ),
        )

        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            process = TermuxPtyRuntime(listOf(File("/system/bin"), context.filesDir)).launch(
                command,
                object : TermuxRuntimeListener {
                    override fun onExited(exitStatus: Int) = finished.countDown()
                },
            )
        }

        val deadline = SystemClock.elapsedRealtime() + 5_000
        while (!childPidFile.isFile && SystemClock.elapsedRealtime() < deadline) SystemClock.sleep(25)
        assertTrue("child pid was not reported", childPidFile.isFile)
        val childPid = childPidFile.readText().trim().toInt()
        val rootPid = process.pid
        assertTrue(rootPid > 0)
        assertTrue(childPid > 0)

        process.stop()

        assertTrue("PTY process did not exit", finished.await(5, TimeUnit.SECONDS))
        assertFalse(processExists(rootPid))
        assertFalse(processExists(childPid))
    }

    private fun processExists(pid: Int): Boolean = runCatching {
        Os.kill(pid, 0)
        true
    }.getOrDefault(false)
}

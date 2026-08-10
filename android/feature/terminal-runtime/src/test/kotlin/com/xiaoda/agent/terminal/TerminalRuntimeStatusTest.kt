package com.xiaoda.agent.terminal

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class TerminalRuntimeStatusTest {
    @Test
    fun runtimeIsDisabledUntilTheG5LegalAndPolicyGatePasses() {
        val status = TerminalRuntimeStatus.current

        assertEquals("disabled", status.state)
        assertFalse(status.canStart)
        assertFalse(TerminalRuntimeStatus.legalReview.releaseEnabled)
        assertFalse(TerminalRuntimeStatus.legalReview.componentFrozen)
        assertFalse(TerminalRuntimeStatus.legalReview.legalApproved)
        assertFalse(TerminalRuntimeStatus.legalReview.storeApproved)
        assertEquals(true, TerminalRuntimeStatus.legalReview.bomGenerated)
        assertEquals(true, TerminalRuntimeStatus.legalReview.sbomGenerated)
        assertEquals(true, TerminalRuntimeStatus.legalReview.noticeGenerated)
    }

    @Test
    fun publicContractDoesNotExposeAProcessStartOperation() {
        val methodNames = TerminalRuntimeStatus::class.java.methods.map { it.name }.toSet()

        assertFalse("start" in methodNames)
        assertFalse("runCommand" in methodNames)
    }
}

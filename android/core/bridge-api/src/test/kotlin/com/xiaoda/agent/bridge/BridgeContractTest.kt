package com.xiaoda.agent.bridge

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BridgeContractTest {
    @Test
    fun approvedBridgeSurfaceMatchesTheArchitectureAllowlist() {
        val methods = BridgeContract.allowedMethods

        assertTrue(methods.containsAll(setOf("getInsets", "getNetworkStatus", "authenticate", "restoreSession", "clearSession", "pickFile", "shareText")))
        assertTrue(methods.size == 7)
    }

    @Test
    fun genericCommandFileAndIntentCapabilitiesCannotBeExposed() {
        val methods = BridgeContract.allowedMethods

        assertFalse("runCommand" in methods)
        assertFalse("readFile" in methods)
        assertFalse("openIntent" in methods)
        assertFalse("setSecureToken" in methods)
        assertFalse("setSheetOpen" in methods)
        assertFalse("openTerminal" in methods)
        assertFalse("getRuntimeStatus" in methods)
        assertFalse("stopRuntime" in methods)
    }
}

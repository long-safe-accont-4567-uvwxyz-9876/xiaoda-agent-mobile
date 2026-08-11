package com.xiaoda.agent.bridge

import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Test

class BridgeContractTest {
    @Test
    fun approvedBridgeSurfaceMatchesTheLocalMobileArchitecture() {
        assertEquals(
            setOf(
                "getInsets",
                "getNetworkStatus",
                "pickFile",
                "shareText",
                "local.bootstrap",
                "local.saveProvider",
                "local.deleteProvider",
                "local.listModels",
                "local.saveAgent",
                "local.listSessions",
                "local.createSession",
                "local.getMessages",
                "local.deleteSession",
                "local.chat",
                "local.abort",
                "local.pickAttachment",
            ),
            BridgeContract.allowedMethods,
        )
    }

    @Test
    fun remoteAuthenticationAndGenericRuntimeCapabilitiesCannotBeExposed() {
        val methods = BridgeContract.allowedMethods
        for (method in setOf("authenticate", "restoreSession", "clearSession", "setSecureToken", "runCommand", "readFile", "openIntent", "openTerminal", "getRuntimeStatus", "stopRuntime")) {
            assertFalse(method in methods)
        }
    }
}

package com.xiaoda.agent.bridge

object BridgeContract {
    val allowedMethods: Set<String> = setOf(
        "getInsets",
        "getNetworkStatus",
        "authenticate",
        "restoreSession",
        "clearSession",
        "pickFile",
        "shareText",
        "openTerminal",
        "getRuntimeStatus",
        "stopRuntime",
    )
}

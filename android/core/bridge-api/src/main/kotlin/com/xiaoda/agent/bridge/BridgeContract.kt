package com.xiaoda.agent.bridge

object BridgeContract {
    val allowedMethods: Set<String> = setOf(
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
    )
}

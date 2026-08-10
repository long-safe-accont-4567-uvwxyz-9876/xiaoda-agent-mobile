package com.xiaoda.agent.webcontainer

import java.net.URI

class EndpointPolicy(private val allowDevelopmentEndpoints: Boolean) {
    fun isAllowed(endpoint: String): Boolean {
        val uri = runCatching { URI(endpoint) }.getOrNull() ?: return false
        val scheme = uri.scheme?.lowercase() ?: return false
        val host = uri.host?.lowercase() ?: return false
        if (uri.userInfo != null || uri.rawQuery != null || uri.rawFragment != null) return false
        if (scheme == "https" || scheme == "wss") return true
        return allowDevelopmentEndpoints &&
            (scheme == "http" || scheme == "ws") &&
            (host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "10.0.2.2")
    }
}

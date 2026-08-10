package com.xiaoda.agent.webcontainer

import java.net.URI

class TrustedNavigationPolicy(private val trustedOrigin: String) {
    fun isBundledResource(url: String): Boolean = origin(url) == trustedOrigin

    fun isExternalLink(url: String): Boolean {
        val uri = runCatching { URI(url) }.getOrNull() ?: return false
        return uri.scheme?.lowercase() in setOf("https", "mailto") && uri.userInfo == null
    }

    private fun origin(url: String): String? {
        val uri = runCatching { URI(url) }.getOrNull() ?: return null
        val port = if (uri.port == -1) "" else ":${uri.port}"
        return uri.host?.let { "${uri.scheme}://$it$port" }
    }
}

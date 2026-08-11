package com.xiaoda.agent.local

import java.net.URI

class ProviderConfigValidator(private val allowDevelopmentEndpoints: Boolean) {
    fun validate(provider: LocalProvider): String? {
        if (!provider.id.matches(Regex("[a-z0-9][a-z0-9._-]{0,63}"))) return "invalid_provider_id"
        if (provider.label.isBlank() || provider.label.length > 80) return "invalid_provider_label"
        if (provider.format !in setOf("openai", "anthropic")) return "unsupported_provider_format"
        if (provider.defaultModel.isBlank() || provider.defaultModel.length > 160) return "invalid_default_model"
        val uri = runCatching { URI(provider.baseUrl) }.getOrNull() ?: return "invalid_base_url"
        if (uri.userInfo != null || uri.rawQuery != null || uri.rawFragment != null) return "invalid_base_url"
        val host = uri.host?.lowercase() ?: return "invalid_base_url"
        val scheme = uri.scheme?.lowercase() ?: return "invalid_base_url"
        if (scheme == "https") return null
        if (allowDevelopmentEndpoints && scheme == "http" && host in setOf("localhost", "127.0.0.1", "10.0.2.2")) return null
        return "insecure_base_url"
    }
}

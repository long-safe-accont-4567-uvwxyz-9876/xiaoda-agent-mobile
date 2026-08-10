package com.xiaoda.agent.security

object SecretRedactor {
    private val sensitiveKeys = setOf("token", "apikey", "api_key", "authorization", "password", "secret")

    fun redact(value: String): String = when {
        value.isEmpty() -> ""
        value.length <= 8 -> "••••"
        else -> "${value.take(3)}…${value.takeLast(4)}"
    }

    fun redactFields(fields: Map<String, String>): Map<String, String> =
        fields.mapValues { (key, value) ->
            if (key.lowercase() in sensitiveKeys) redact(value) else value
        }
}

package com.xiaoda.agent.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SecretRedactorTest {
    @Test
    fun longSecretsExposeOnlyShortPrefixAndSuffix() {
        val secret = "demo-example-super-secret-value"
        val redacted = SecretRedactor.redact(secret)

        assertEquals("dem…alue", redacted)
        assertFalse(redacted.contains(secret))
        assertFalse(redacted.contains("super-secret"))
    }

    @Test
    fun shortSecretsAreFullyMasked() {
        assertEquals("••••", SecretRedactor.redact("token"))
        assertEquals("", SecretRedactor.redact(""))
    }

    @Test
    fun diagnosticFieldsRedactTokenAndApiKeyValues() {
        val fields = SecretRedactor.redactFields(
            mapOf("token" to "bearer-secret", "apiKey" to "provider-secret", "stage" to "tls"),
        )

        assertFalse(fields.toString().contains("bearer-secret"))
        assertFalse(fields.toString().contains("provider-secret"))
        assertEquals("tls", fields["stage"])
    }
}

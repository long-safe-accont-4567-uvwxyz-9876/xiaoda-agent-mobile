package com.xiaoda.agent.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProviderConfigValidatorTest {
    @Test
    fun releaseAcceptsOnlyCredentialFreeHttpsEndpoints() {
        val validator = ProviderConfigValidator(allowDevelopmentEndpoints = false)
        assertNull(validator.validate(LocalProvider("openai", "OpenAI", "openai", "https://api.openai.com/v1", "model")))
        assertEquals("insecure_base_url", validator.validate(LocalProvider("local", "Local", "openai", "http://127.0.0.1:8000/v1", "model")))
        assertEquals("invalid_base_url", validator.validate(LocalProvider("bad", "Bad", "openai", "https://user:secret@example.com/v1", "model")))
    }

    @Test
    fun debugAllowsOnlyExplicitLoopbackDevelopmentEndpoints() {
        val validator = ProviderConfigValidator(allowDevelopmentEndpoints = true)
        assertNull(validator.validate(LocalProvider("local", "Local", "openai", "http://10.0.2.2:8000/v1", "model")))
        assertEquals("insecure_base_url", validator.validate(LocalProvider("lan", "LAN", "openai", "http://192.168.1.5:8000/v1", "model")))
    }
}

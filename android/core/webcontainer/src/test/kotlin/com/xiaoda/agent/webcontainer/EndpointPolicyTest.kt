package com.xiaoda.agent.webcontainer

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EndpointPolicyTest {
    @Test
    fun debugAllowsLoopbackHttpOnlyWhenDevelopmentEndpointsAreEnabled() {
        val policy = EndpointPolicy(allowDevelopmentEndpoints = true)

        assertTrue(policy.isAllowed("http://127.0.0.1:8000"))
        assertTrue(policy.isAllowed("ws://localhost:8000/ws"))
        assertTrue(policy.isAllowed("http://10.0.2.2:8000"))
        assertFalse(policy.isAllowed("http://example.com"))
    }

    @Test
    fun stagingAndReleaseAllowOnlySecureRemoteSchemes() {
        val policy = EndpointPolicy(allowDevelopmentEndpoints = false)

        assertTrue(policy.isAllowed("https://agent.example.com"))
        assertTrue(policy.isAllowed("wss://agent.example.com/ws"))
        assertFalse(policy.isAllowed("http://agent.example.com"))
        assertFalse(policy.isAllowed("http://10.0.2.2:8000"))
        assertFalse(policy.isAllowed("ws://agent.example.com/ws"))
        assertFalse(policy.isAllowed("file:///data/local/tmp/index.html"))
    }

    @Test
    fun malformedOrCredentialBearingEndpointsAreRejected() {
        val policy = EndpointPolicy(allowDevelopmentEndpoints = true)

        assertFalse(policy.isAllowed("not a url"))
        assertFalse(policy.isAllowed("https://user:password@agent.example.com"))
        assertFalse(policy.isAllowed("https://agent.example.com?token=secret"))
        assertFalse(policy.isAllowed("https://agent.example.com/#fragment"))
        assertFalse(policy.isAllowed("javascript:alert(1)"))
    }
}

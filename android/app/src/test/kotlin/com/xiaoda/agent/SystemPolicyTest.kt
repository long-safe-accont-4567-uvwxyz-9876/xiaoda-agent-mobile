package com.xiaoda.agent

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SystemPolicyTest {
    @Test
    fun `back navigation prioritizes sheet then web history then activity`() {
        assertEquals(BackAction.CLOSE_SHEET, BackNavigationPolicy.decide(true, true))
        assertEquals(BackAction.GO_BACK, BackNavigationPolicy.decide(false, true))
        assertEquals(BackAction.FINISH, BackNavigationPolicy.decide(false, false))
    }

    @Test
    fun `connection runs only while foreground and network available`() {
        val policy = ConnectionLifecyclePolicy()
        assertFalse(policy.shouldConnect)
        policy.onNetworkChanged(true)
        assertFalse(policy.shouldConnect)
        policy.onForegroundChanged(true)
        assertTrue(policy.shouldConnect)
        policy.onForegroundChanged(false)
        assertFalse(policy.shouldConnect)
    }

    @Test
    fun `connection policy restores foreground and network state`() {
        val restored = ConnectionLifecyclePolicy(ConnectionLifecycleState(foreground = true, networkAvailable = true))

        assertTrue(restored.shouldConnect)
        assertEquals(ConnectionLifecycleState(true, true), restored.snapshot())
    }

    @Test
    fun `connection lifecycle emits only effective state changes`() {
        val policy = ConnectionLifecyclePolicy()

        assertEquals(null, policy.onNetworkChanged(true))
        assertEquals(true, policy.onForegroundChanged(true))
        assertEquals(null, policy.onNetworkChanged(true))
        assertEquals(false, policy.onNetworkChanged(false))
        assertEquals(null, policy.onForegroundChanged(false))
    }

    @Test
    fun `current network observation replaces stale restored snapshot`() {
        val restored = ConnectionLifecyclePolicy(ConnectionLifecycleState(foreground = false, networkAvailable = true))

        assertEquals(null, restored.onNetworkChanged(false))
        assertFalse(restored.snapshot().networkAvailable)
        assertEquals(null, restored.onForegroundChanged(true))
        assertFalse(restored.shouldConnect)
    }

    @Test
    fun `network callback generations ignore callbacks from an unregistered observer`() {
        val generations = NetworkCallbackGeneration()
        val first = generations.register()
        generations.unregister(first)
        val second = generations.register()

        assertFalse(generations.isCurrent(first))
        assertTrue(generations.isCurrent(second))
    }

    @Test
    fun `deep links accept only xiaoda routes without authority confusion`() {
        assertEquals("/settings/system", DeepLinkPolicy.route("xiaoda://app/settings/system"))
        assertEquals("/", DeepLinkPolicy.route("xiaoda://app"))
        assertEquals(null, DeepLinkPolicy.route("xiaoda://evil/settings/system"))
        assertEquals(null, DeepLinkPolicy.route("https://example.com"))
    }
}

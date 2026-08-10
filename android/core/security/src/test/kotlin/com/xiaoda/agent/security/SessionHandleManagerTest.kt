package com.xiaoda.agent.security

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionHandleManagerTest {
    @Test
    fun `web session receives an expiring opaque handle instead of token`() {
        var now = 1_000L
        val store = InMemorySecureTokenStore()
        val manager = SessionHandleManager(store, { now }, { "opaque-handle" }, 60_000L)

        val handle = manager.create("secret-bearer-token")

        assertEquals("opaque-handle", handle)
        assertEquals("secret-bearer-token", manager.resolve(handle))
        assertTrue(handle.contains("secret-bearer-token").not())
        now += 60_001L
        assertNull(manager.resolve(handle))
        assertNull(store.read())
    }

    @Test
    fun `stale handle cannot clear the current token`() {
        val store = InMemorySecureTokenStore()
        var nextHandle = 0
        val manager = SessionHandleManager(store, handleFactory = { "handle-${++nextHandle}" })

        val staleHandle = manager.create("old-token")
        val currentHandle = manager.create("current-token")

        assertNull(manager.resolve(staleHandle))
        assertEquals("current-token", manager.resolve(currentHandle))
    }
    @Test
    fun `stored token can be restored as a new opaque handle`() {
        val store = InMemorySecureTokenStore().apply { write("persisted-token") }
        val manager = SessionHandleManager(store, handleFactory = { "restored-handle" })

        val handle = manager.restore()

        assertEquals("restored-handle", handle)
        assertEquals("persisted-token", manager.resolve(requireNotNull(handle)))
    }

}

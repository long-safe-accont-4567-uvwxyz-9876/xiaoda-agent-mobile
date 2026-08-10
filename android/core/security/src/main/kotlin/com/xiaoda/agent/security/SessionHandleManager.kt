package com.xiaoda.agent.security

import java.util.UUID

class SessionHandleManager(
    private val store: SecureTokenStore,
    private val clock: () -> Long = System::currentTimeMillis,
    private val handleFactory: () -> String = { UUID.randomUUID().toString() },
    private val lifetimeMillis: Long = 5 * 60 * 1000L,
) {
    private var activeHandle: String? = null
    private var expiresAt = 0L

    fun create(token: String): String {
        store.write(token)
        return issueHandle()
    }

    fun restore(): String? = store.read()?.takeIf(String::isNotEmpty)?.let { issueHandle() }

    fun resolve(handle: String): String? {
        if (handle != activeHandle) return null
        if (clock() >= expiresAt) {
            clear()
            return null
        }
        return store.read()
    }

    private fun issueHandle(): String = handleFactory().also {
        activeHandle = it
        expiresAt = clock() + lifetimeMillis
    }

    fun clear() {
        activeHandle = null
        expiresAt = 0L
        store.clear()
    }
}

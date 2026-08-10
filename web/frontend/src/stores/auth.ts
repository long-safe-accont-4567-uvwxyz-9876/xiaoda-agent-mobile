import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import { getWsClient } from '../api/ws'
import { authenticate, bearerToken, clearSession, hasSession, restoreSession, sessionExpiry, storeBrowserSession } from '../platform/authSession'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(bearerToken())
  const expiresAt = ref(sessionExpiry())

  const isLoggedIn = computed(() => hasSession() || !!token.value && Date.now() / 1000 < expiresAt.value)

  async function restore() {
    try {
      const native = await restoreSession()
      if (!native) return false
      token.value = native.handle
      expiresAt.value = native.expiresAt
      getWsClient().connect()
      return true
    } catch {
      token.value = ''
      expiresAt.value = 0
      return false
    }
  }

  async function login(password: string) {
    const native = await authenticate(password)
    if (native) {
      token.value = native.handle
      expiresAt.value = native.expiresAt
      getWsClient().connect()
      return
    }
    const data = await api.login(password)
    token.value = data.token
    expiresAt.value = data.expires_at
    storeBrowserSession(data.token, data.expires_at)
    // Connect WebSocket
    getWsClient().connect(data.token)
  }

  async function logout() {
    token.value = ''
    expiresAt.value = 0
    await clearSession()
    getWsClient().disconnect()
  }

  return { token, expiresAt, isLoggedIn, restore, login, logout }
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

const restoreSession = vi.fn()
vi.mock('../platform/authSession', () => ({
  bearerToken: () => 'expired-handle',
  ensureNativeSession: restoreSession,
}))
vi.mock('../platform/nativeBridge', () => ({ isAndroidWebView: () => true }))
vi.mock('../platform/runtimeConfig', () => ({ runtimeWebSocketUrl: () => 'wss://agent.example/ws' }))

describe('Android WebSocket 会话续签', () => {
  beforeEach(() => {
    vi.resetModules()
    restoreSession.mockReset()
  })

  it('每次连接前续签短句柄并使用新句柄握手', async () => {
    restoreSession.mockResolvedValue({ handle: 'renewed-handle', expiresAt: Date.now() / 1000 + 300 })
    const sockets: any[] = []
    vi.stubGlobal('WebSocket', class {
      static OPEN = 1
      readyState = 0
      close = vi.fn()
      send = vi.fn()
      constructor(public url: string, public protocols: string[]) { sockets.push(this) }
    })
    const { WsClient } = await import('./ws')

    new WsClient('wss://agent.example/ws').connect()
    await vi.waitFor(() => expect(sockets).toHaveLength(1))

    expect(restoreSession).toHaveBeenCalledOnce()
    expect(sockets[0].protocols).toEqual(['xiaoda-session', 'renewed-handle'])
  })
})

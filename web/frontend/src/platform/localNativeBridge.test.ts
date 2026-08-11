import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createLocalNativeBridge } from './localNativeBridge'

describe('local Android bridge', () => {
  beforeEach(() => { delete (window as any).XiaodaNative })

  it('sends only local capability calls', async () => {
    const postMessage = vi.fn()
    const port: any = { postMessage, onmessage: null }
    ;(window as any).XiaodaNative = port
    const bridge = createLocalNativeBridge()
    const pending = bridge.localBootstrap()
    const request = JSON.parse(postMessage.mock.calls[0][0])
    expect(request.method).toBe('local.bootstrap')
    port.onmessage(new MessageEvent('message', { data: JSON.stringify({ id: request.id, result: { providers: [] } }) }))
    await expect(pending).resolves.toEqual({ providers: [] })
  })

  it('dispatches streaming events independently from replies', () => {
    const port: any = { postMessage: vi.fn(), onmessage: null }
    ;(window as any).XiaodaNative = port
    const bridge = createLocalNativeBridge()
    const listener = vi.fn()
    bridge.on('local.chat.delta', listener)
    port.onmessage(new MessageEvent('message', { data: JSON.stringify({ event: 'local.chat.delta', data: { delta: 'token' } }) }))
    expect(listener).toHaveBeenCalledWith({ delta: 'token' })
  })
})

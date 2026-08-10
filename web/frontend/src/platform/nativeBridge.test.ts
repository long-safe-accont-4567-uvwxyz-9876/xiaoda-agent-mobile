import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createNativeBridge, isAndroidWebView } from './nativeBridge'

describe('Android Bridge adapter', () => {
  beforeEach(() => {
    delete (window as any).XiaodaNative
  })

  it('detects only the injected WebMessage bridge', () => {
    expect(isAndroidWebView()).toBe(false)
    ;(window as any).XiaodaNative = { postMessage: vi.fn() }
    expect(isAndroidWebView()).toBe(true)
  })

  it('correlates native replies without exposing bearer tokens', async () => {
    const postMessage = vi.fn()
    const nativePort: any = { postMessage, onmessage: null }
    ;(window as any).XiaodaNative = nativePort
    const bridge = createNativeBridge()
    const pending = bridge.authenticate('password')
    const request = JSON.parse(postMessage.mock.calls[0][0])

    expect(request.method).toBe('authenticate')
    expect(request.args.password).toBe('password')
    nativePort.onmessage(new MessageEvent('message', {
      data: JSON.stringify({ id: request.id, result: { handle: 'opaque', expiresAt: 123 } }),
    }))

    await expect(pending).resolves.toEqual({ handle: 'opaque', expiresAt: 123 })
    expect(JSON.stringify(await pending)).not.toContain('token')
  })

  it('returns verified picked bytes as a File', async () => {
    const postMessage = vi.fn()
    const nativePort: any = { postMessage, onmessage: null }
    ;(window as any).XiaodaNative = nativePort
    const bridge = createNativeBridge()
    const pending = bridge.pickFile('image/*', 1024)
    const request = JSON.parse(postMessage.mock.calls[0][0])
    nativePort.onmessage(new MessageEvent('message', {
      data: JSON.stringify({ id: request.id, result: { dataBase64: 'iVBORw0KGgo=', mimeType: 'image/png', sizeBytes: 8, name: 'upload.png' } }),
    }))

    const file = await pending
    expect(file).toBeInstanceOf(File)
    expect(file?.type).toBe('image/png')
    expect(file?.size).toBe(8)
  })

  it('forwards wildcard file requests for the upload router', async () => {
    const postMessage = vi.fn()
    const nativePort: any = { postMessage, onmessage: null }
    ;(window as any).XiaodaNative = nativePort
    const pending = createNativeBridge().pickFile('*/*', 20 * 1024 * 1024)
    const request = JSON.parse(postMessage.mock.calls[0][0])

    expect(request.args.accept).toBe('*/*')
    nativePort.onmessage(new MessageEvent('message', {
      data: JSON.stringify({ id: request.id, result: { cancelled: true } }),
    }))
    await expect(pending).resolves.toBeNull()
  })
})

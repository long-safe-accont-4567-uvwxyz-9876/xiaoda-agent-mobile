type NativeReply = { id: string; result?: any; error?: string }

interface NativePort {
  postMessage(message: string): void
  onmessage?: ((event: MessageEvent) => void) | null
}

declare global {
  interface Window {
    XiaodaNative?: NativePort
  }
}

export interface NativeSession {
  handle: string
  expiresAt: number
}

export function isAndroidWebView(): boolean {
  return typeof window !== 'undefined' && typeof window.XiaodaNative?.postMessage === 'function'
}

export function createNativeBridge() {
  let sequence = 0
  let attachedPort: NativePort | null = null
  const pending = new Map<string, {
    resolve: (value: any) => void
    reject: (reason: Error) => void
    timeout: number
  }>()
  const onMessage = (event: MessageEvent) => {
    if (typeof event.data !== 'string') return
    let reply: NativeReply
    try { reply = JSON.parse(event.data) } catch { return }
    const request = pending.get(reply.id)
    if (!request) return
    pending.delete(reply.id)
    window.clearTimeout(request.timeout)
    if (reply.error) request.reject(new Error(reply.error))
    else request.resolve(reply.result)
  }
  const nativePort = (): NativePort | null => {
    const port = window.XiaodaNative || null
    if (port && port !== attachedPort) {
      port.onmessage = onMessage
      attachedPort = port
    }
    return port
  }

  function invoke<T>(method: string, args: Record<string, unknown> = {}): Promise<T> {
    const port = nativePort()
    if (!port) return Promise.reject(new Error('native_bridge_unavailable'))
    const id = `native-${Date.now()}-${++sequence}`
    return new Promise<T>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        pending.delete(id)
        reject(new Error('native_bridge_timeout'))
      }, 15_000)
      pending.set(id, { resolve, reject, timeout })
      port.postMessage(JSON.stringify({ id, method, args }))
    })
  }

  return {
    authenticate: (password: string) => invoke<NativeSession>('authenticate', { password }),
    restoreSession: () => invoke<NativeSession | null>('restoreSession'),
    clearSession: () => invoke<void>('clearSession'),
    pickFile: async (accept: string, maxBytes: number): Promise<File | null> => {
      const value = await invoke<{ dataBase64?: string; mimeType?: string; sizeBytes?: number; name?: string; cancelled?: boolean }>('pickFile', { accept, maxBytes })
      if (value.cancelled) return null
      if (!value.dataBase64 || !value.mimeType || value.sizeBytes === undefined) throw new Error('invalid_native_file')
      const binary = atob(value.dataBase64)
      const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
      if (bytes.byteLength !== value.sizeBytes) throw new Error('native_file_size_mismatch')
      return new File([bytes], value.name || 'upload', { type: value.mimeType })
    },
  }
}

let bridge: ReturnType<typeof createNativeBridge> | null = null

export function getNativeBridge() {
  if (!bridge) bridge = createNativeBridge()
  return bridge
}

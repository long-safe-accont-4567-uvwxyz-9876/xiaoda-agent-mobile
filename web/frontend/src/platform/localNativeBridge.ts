type NativeMessage = { id?: string; result?: any; error?: string; event?: string; data?: any }

interface NativePort {
  postMessage(message: string): void
  onmessage?: ((event: MessageEvent) => void) | null
}

declare global {
  interface Window {
    XiaodaNative?: NativePort
  }
}

export function createLocalNativeBridge() {
  let sequence = 0
  let attachedPort: NativePort | null = null
  const pending = new Map<string, {
    resolve: (value: any) => void
    reject: (reason: Error) => void
    timeout: number
  }>()
  const listeners = new Map<string, Set<(data: any) => void>>()

  const onMessage = (event: MessageEvent) => {
    if (typeof event.data !== 'string') return
    let message: NativeMessage
    try { message = JSON.parse(event.data) } catch { return }
    if (message.event) {
      listeners.get(message.event)?.forEach(listener => listener(message.data))
      return
    }
    if (!message.id) return
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id)
    window.clearTimeout(request.timeout)
    if (message.error) request.reject(new Error(message.error))
    else request.resolve(message.result)
  }

  const nativePort = (): NativePort | null => {
    const port = window.XiaodaNative || null
    if (port && port !== attachedPort) {
      port.onmessage = onMessage
      attachedPort = port
    }
    return port
  }

  function invoke<T>(method: string, args: Record<string, unknown> = {}, timeoutMs = 15_000): Promise<T> {
    const port = nativePort()
    if (!port) return Promise.reject(new Error('native_bridge_unavailable'))
    const id = `local-${Date.now()}-${++sequence}`
    return new Promise<T>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        pending.delete(id)
        reject(new Error('native_bridge_timeout'))
      }, timeoutMs)
      pending.set(id, { resolve, reject, timeout })
      port.postMessage(JSON.stringify({ id, method, args }))
    })
  }

  const on = (event: string, listener: (data: any) => void) => {
    nativePort()
    const eventListeners = listeners.get(event) || new Set<(data: any) => void>()
    eventListeners.add(listener)
    listeners.set(event, eventListeners)
    return () => {
      eventListeners.delete(listener)
      if (eventListeners.size === 0) listeners.delete(event)
    }
  }

  return {
    localBootstrap: () => invoke<any>('local.bootstrap'),
    saveLocalProvider: (provider: Record<string, unknown>) => invoke<any>('local.saveProvider', provider, 60_000),
    deleteLocalProvider: (providerId: string) => invoke<any>('local.deleteProvider', { providerId }),
    listLocalModels: (providerId: string) => invoke<{ models: string[] }>('local.listModels', { providerId }, 60_000),
    saveLocalAgent: (agent: Record<string, unknown>) => invoke<any>('local.saveAgent', agent),
    listLocalSessions: () => invoke<{ sessions: any[] }>('local.listSessions'),
    createLocalSession: () => invoke<any>('local.createSession'),
    getLocalMessages: (sessionId: string) => invoke<any>('local.getMessages', { sessionId }),
    deleteLocalSession: (sessionId: string) => invoke<any>('local.deleteSession', { sessionId }),
    startLocalChat: (request: Record<string, unknown>) => invoke<{ started: boolean; requestId: string }>('local.chat', request),
    abortLocalChat: (requestId: string) => invoke<{ cancelled: boolean }>('local.abort', { requestId }),
    pickLocalAttachment: (accept = '*/*', maxBytes = 10 * 1024 * 1024) => invoke<any>('local.pickAttachment', { accept, maxBytes }, 120_000),
    on,
  }
}

let bridge: ReturnType<typeof createLocalNativeBridge> | null = null

export function getLocalNativeBridge() {
  if (!bridge) bridge = createLocalNativeBridge()
  return bridge
}

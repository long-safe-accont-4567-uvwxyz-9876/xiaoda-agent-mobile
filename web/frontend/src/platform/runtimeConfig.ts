export interface RuntimeConfig {
  apiBase: string
  wsUrl: string
  maxUploadBytes: number
}

declare global {
  interface Window {
    __XIAODA_RUNTIME_CONFIG__?: Partial<RuntimeConfig>
  }
}

function safeConfiguredUrl(value: unknown, schemes: string[]): string | null {
  if (typeof value !== 'string' || !value) return null
  try {
    const parsed = new URL(value, location.href)
    if (!schemes.includes(parsed.protocol) || parsed.username || parsed.password) return null
    return parsed.toString().replace(/\/$/, '')
  } catch {
    return null
  }
}

export function runtimeApiBase(): string {
  return safeConfiguredUrl(window.__XIAODA_RUNTIME_CONFIG__?.apiBase, ['http:', 'https:']) || '/api/v1'
}

export function runtimeWebSocketUrl(): string {
  const configured = safeConfiguredUrl(window.__XIAODA_RUNTIME_CONFIG__?.wsUrl, ['ws:', 'wss:'])
  if (configured) return configured
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws`
}

export function runtimeMaxUploadBytes(): number {
  const configured = window.__XIAODA_RUNTIME_CONFIG__?.maxUploadBytes
  return typeof configured === 'number' && Number.isSafeInteger(configured) && configured > 0 && configured <= 100 * 1024 * 1024
    ? configured
    : 20 * 1024 * 1024
}

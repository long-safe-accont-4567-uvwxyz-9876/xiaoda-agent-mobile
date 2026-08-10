import { getNativeBridge, isAndroidWebView } from './nativeBridge'

let nativeSession: { handle: string; expiresAt: number } | null = null

export function bearerToken(): string {
  return isAndroidWebView() ? nativeSession?.handle || '' : localStorage.getItem('token') || ''
}

export function sessionExpiry(): number {
  return isAndroidWebView() ? nativeSession?.expiresAt || 0 : Number(localStorage.getItem('expires_at')) || 0
}

export function hasSession(): boolean {
  return sessionExpiry() > Date.now() / 1000
}

export async function authenticate(password: string) {
  if (isAndroidWebView()) {
    nativeSession = await getNativeBridge().authenticate(password)
    return nativeSession
  }
  return null
}

export async function restoreSession() {
  if (isAndroidWebView()) nativeSession = await getNativeBridge().restoreSession()
  return nativeSession
}

export async function clearSession() {
  nativeSession = null
  if (isAndroidWebView()) await getNativeBridge().clearSession()
  else {
    localStorage.removeItem('token')
    localStorage.removeItem('expires_at')
  }
}

export function storeBrowserSession(token: string, expiresAt: number) {
  if (isAndroidWebView()) return
  localStorage.setItem('token', token)
  localStorage.setItem('expires_at', String(expiresAt))
}

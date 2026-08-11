import { beforeEach, describe, expect, it } from 'vitest'
import { runtimeApiBase, runtimeMaxUploadBytes, runtimeWebSocketUrl } from './runtimeConfig'

describe('runtime endpoint configuration', () => {
  beforeEach(() => {
    delete window.__XIAODA_RUNTIME_CONFIG__
  })

  it('uses browser-relative defaults outside Android', () => {
    expect(runtimeApiBase()).toBe('/api/v1')
    expect(runtimeWebSocketUrl()).toContain('/ws')
  })

  it('accepts the trusted document-start endpoint configuration', () => {
    window.__XIAODA_RUNTIME_CONFIG__ = {
      apiBase: 'https://agent.example.com/api/v1/',
      wsUrl: 'wss://agent.example.com/ws/',
      maxUploadBytes: 10 * 1024 * 1024,
    }

    expect(runtimeApiBase()).toBe('https://agent.example.com/api/v1')
    expect(runtimeWebSocketUrl()).toBe('wss://agent.example.com/ws')
  })

  it('uses the native upload limit and rejects unsafe values', () => {
    expect(runtimeMaxUploadBytes()).toBe(20 * 1024 * 1024)
    window.__XIAODA_RUNTIME_CONFIG__ = { maxUploadBytes: 7 * 1024 * 1024 }
    expect(runtimeMaxUploadBytes()).toBe(7 * 1024 * 1024)
    window.__XIAODA_RUNTIME_CONFIG__ = { maxUploadBytes: -1 }
    expect(runtimeMaxUploadBytes()).toBe(20 * 1024 * 1024)
  })

  it('rejects credential-bearing or wrong-scheme endpoint overrides', () => {
    window.__XIAODA_RUNTIME_CONFIG__ = {
      apiBase: 'https://user:password@agent.example.com/api/v1',
      wsUrl: 'https://agent.example.com/ws',
    }

    expect(runtimeApiBase()).toBe('/api/v1')
    expect(runtimeWebSocketUrl()).toContain('/ws')
  })
})

import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatTerminal from './ChatTerminal.vue'

const handlers = new Map<string, (event: { type: string }) => void>()
const send = vi.fn()
const fit = vi.fn()
const confirm = vi.fn()
let resizeObserverCallback: ResizeObserverCallback | undefined

vi.mock('../../api/ws', () => ({
  getWsClient: () => ({
    on: (type: string, handler: (event: { type: string }) => void) => handlers.set(type, handler),
    off: (type: string) => handlers.delete(type),
    send,
  }),
}))

vi.mock('../../api', () => ({
  get: () => Promise.resolve({ os: 'linux', shell: 'bash' }),
}))

vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    loadAddon() {}
    onData() {}
    open() {}
    focus() {}
    write() {}
    writeln() {}
    dispose() {}
  },
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() { fit() }
    proposeDimensions() { return { cols: 80, rows: 24 } }
  },
}))

vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

describe('ChatTerminal', () => {
  function mountTerminal() {
    return mount(ChatTerminal, {
      attachTo: document.body,
      global: { plugins: [createPinia()], stubs: { teleport: true } },
    })
  }

  beforeEach(() => {
    handlers.clear()
    send.mockClear()
    fit.mockClear()
    confirm.mockReset()
    confirm.mockReturnValue(true)
    vi.stubGlobal('confirm', confirm)
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
    resizeObserverCallback = undefined
    Object.defineProperty(window, 'ResizeObserver', {
      configurable: true,
      value: class {
        constructor(callback: ResizeObserverCallback) { resizeObserverCallback = callback }
        observe() {}
        disconnect() {}
      },
    })
    vi.stubGlobal('ResizeObserver', window.ResizeObserver)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('opens as a trapped dialog and restores focus on Escape', async () => {
    const wrapper = mountTerminal()
    const opener = wrapper.get('.term-fab')
    ;(opener.element as HTMLElement).focus()
    await opener.trigger('click')
    await nextTick()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.element.contains(document.activeElement)).toBe(true)
    await dialog.trigger('keydown', { key: 'Escape' })
    await nextTick()
    expect(document.activeElement).toBe(wrapper.get('.term-fab').element)
    wrapper.unmount()
  })

  it('marks terminal sessions disconnected when the socket drops', async () => {
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()
    handlers.get('ws_disconnected')?.({ type: 'ws_disconnected' })
    await nextTick()
    expect(wrapper.get('[role="status"]').text()).toContain('disconnected')
    expect(wrapper.get('[role="tab"]').attributes('aria-selected')).toBe('true')
    wrapper.unmount()
  })

  it('removes disconnected sessions when the socket reconnects', async () => {
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()

    handlers.get('ws_disconnected')?.({ type: 'ws_disconnected' })
    await nextTick()
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(1)

    handlers.get('ws_connected')?.({ type: 'ws_connected' })
    await nextTick()

    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('resizes the existing desktop session without generating another sid', async () => {
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()
    const start = send.mock.calls.find(call => call[0].type === 'terminal_start')?.[0]
    send.mockClear()

    resizeObserverCallback?.([] as ResizeObserverEntry[], {} as ResizeObserver)
    await nextTick()

    expect(send).toHaveBeenCalledWith({
      type: 'terminal_resize',
      term_sid: start.term_sid,
      cols: 80,
      rows: 24,
    })
    expect(send.mock.calls.some(call => call[0].type === 'terminal_start')).toBe(false)
    wrapper.unmount()
  })

  it('keeps a live session when close confirmation is rejected', async () => {
    confirm.mockReturnValue(false)
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()
    send.mockClear()

    await wrapper.get('.tab-close').trigger('click')

    expect(confirm).toHaveBeenCalledOnce()
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(1)
    expect(send.mock.calls.some(call => call[0].type === 'terminal_kill')).toBe(false)
    wrapper.unmount()
  })

  it('kills and disposes live sessions before the component unmounts', async () => {
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()
    const start = send.mock.calls.find(call => call[0].type === 'terminal_start')?.[0]
    expect(start?.term_sid).toBeTruthy()

    wrapper.unmount()

    expect(send).toHaveBeenCalledWith({ type: 'terminal_kill', term_sid: start.term_sid })
  })

  it('exposes shell selection and session close controls to assistive technology', async () => {
    const wrapper = mountTerminal()
    await wrapper.get('.term-fab').trigger('click')
    await wrapper.get('.empty-btn').trigger('click')
    const shellOptions = wrapper.findAll('[role="radio"]')
    expect(shellOptions.length).toBeGreaterThan(0)
    expect(shellOptions.some(option => option.attributes('aria-checked') === 'true')).toBe(true)
    await wrapper.get('.create-btn').trigger('click')
    await nextTick()
    expect(wrapper.get('.tab-close').attributes('aria-label')).toContain('bash #1')
    wrapper.unmount()
  })
})

import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from './AppLayout.vue'
import { capabilities } from '../../navigation/capabilities'

const connectWs = vi.fn()
const disconnectWs = vi.fn()
vi.mock('../../api/ws', () => ({
  getWsClient: () => ({ connected: false, reconnecting: false, connect: connectWs, disconnect: disconnectWs, on: vi.fn(), off: vi.fn() }),
}))

describe('应用壳生命周期', () => {
  beforeEach(() => {
    connectWs.mockClear()
    disconnectWs.mockClear()
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('expires_at', String(Date.now() / 1000 + 3600))
  })

  it('消费原生连接策略并在恢复时重新建立连接', async () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: AppLayout, children: [{ path: '', component: { template: '<div />' } }] }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })
    await nextTick()
    connectWs.mockClear()

    window.dispatchEvent(new CustomEvent('xiaoda:connection-policy', { detail: { connect: false } }))
    expect(disconnectWs).toHaveBeenCalledOnce()
    window.dispatchEvent(new CustomEvent('xiaoda:connection-policy', { detail: { connect: true } }))
    expect(connectWs).toHaveBeenCalledOnce()
    expect(connectWs).toHaveBeenCalledWith()
    wrapper.unmount()
  })

  it('断点切换不重建业务页面并保留页面状态', async () => {
    let listener: ((event: MediaQueryListEvent) => void) | undefined
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: vi.fn((_name, callback) => { listener = callback }),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    let setupCount = 0
    const Page = defineComponent({
      setup() {
        setupCount += 1
        const value = ref('保留状态')
        return { value }
      },
      template: '<input data-page-state v-model="value" />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: AppLayout, children: [{ path: '', component: Page }] },
        ...capabilities.filter(item => item.path !== '/').map(item => ({
          path: item.path,
          component: { template: '<div />' },
        })),
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })
    await nextTick()
    await wrapper.find('[data-page-state]').setValue('用户输入')
    listener?.({ matches: true } as MediaQueryListEvent)
    await nextTick()
    expect(setupCount).toBe(1)
    expect(wrapper.find<HTMLInputElement>('[data-page-state]').element.value).toBe('用户输入')
  })

  it('仅缓存 ChatView，其他路由页面离开后卸载', async () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    const chatUnmounted = vi.fn()
    const settingsUnmounted = vi.fn()
    const ChatView = defineComponent({
      name: 'ChatView',
      unmounted: chatUnmounted,
      template: '<div data-chat-page />',
    })
    const SettingsView = defineComponent({
      name: 'SettingsView',
      unmounted: settingsUnmounted,
      template: '<div data-settings-page />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: AppLayout, children: [
          { path: '', component: ChatView },
          { path: 'settings/system', component: SettingsView },
          ...capabilities.filter(item => item.path !== '/' && item.path !== '/settings/system').map(item => ({
            path: item.path.slice(1),
            component: { template: '<div />' },
          })),
        ] },
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })
    await nextTick()
    await router.push('/settings/system')
    await nextTick()
    expect(chatUnmounted).not.toHaveBeenCalled()
    await router.push('/')
    await nextTick()
    expect(settingsUnmounted).toHaveBeenCalledOnce()
    expect(wrapper.find('[data-chat-page]').exists()).toBe(true)
  })

  it('卸载应用壳时释放断点监听并卸载业务页面', async () => {
    const removeEventListener = vi.fn()
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener,
    } as unknown as MediaQueryList)
    const onUnmounted = vi.fn()
    const Page = defineComponent({
      unmounted: onUnmounted,
      template: '<div data-lifecycle-page />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: AppLayout, children: [{ path: '', component: Page }] },
        ...capabilities.filter(item => item.path !== '/').map(item => ({ path: item.path, component: { template: '<div />' } })),
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })
    await nextTick()
    wrapper.unmount()
    expect(removeEventListener).toHaveBeenCalledTimes(2)
    expect(onUnmounted).toHaveBeenCalledOnce()
  })
})

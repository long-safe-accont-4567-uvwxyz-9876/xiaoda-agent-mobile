import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, nextTick, onActivated, onDeactivated, onUnmounted } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from './AppLayout.vue'

vi.mock('../../api/ws', () => ({
  getWsClient: () => ({ connected: true, connect: vi.fn() }),
}))

vi.mock('./SideBar.vue', () => ({ default: { template: '<nav />' } }))
vi.mock('./TopBar.vue', () => ({ default: { template: '<header />' } }))
vi.mock('./AgentBackdrop.vue', () => ({ default: { template: '<div />' } }))

describe('AppLayout 路由缓存', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('expires_at', String(Date.now() / 1000 + 3600))
  })

  it('仅缓存 ChatView，其他路由离开后卸载', async () => {
    const chatDeactivated = vi.fn()
    const chatUnmounted = vi.fn()
    const otherUnmounted = vi.fn()
    const ChatView = defineComponent({
      name: 'ChatView',
      setup() {
        onDeactivated(chatDeactivated)
        onUnmounted(chatUnmounted)
      },
      template: '<div data-chat />',
    })
    const OtherView = defineComponent({
      name: 'OtherView',
      setup() {
        onUnmounted(otherUnmounted)
      },
      template: '<div data-other />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/',
        component: AppLayout,
        children: [
          { path: '', component: ChatView },
          { path: 'other', component: OtherView },
        ],
      }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })

    await router.push('/other')
    await nextTick()
    expect(chatDeactivated).toHaveBeenCalledOnce()
    expect(chatUnmounted).not.toHaveBeenCalled()

    await router.push('/')
    await nextTick()
    expect(otherUnmounted).toHaveBeenCalledOnce()
    expect(wrapper.find('[data-chat]').exists()).toBe(true)
  })

  it('ChatView 失活后不响应遗留副作用，激活后恢复', async () => {
    const effect = vi.fn()
    const listener = () => effect()
    const ChatView = defineComponent({
      name: 'ChatView',
      setup() {
        onActivated(() => document.addEventListener('review-effect', listener))
        onDeactivated(() => document.removeEventListener('review-effect', listener))
        onUnmounted(() => document.removeEventListener('review-effect', listener))
      },
      template: '<div data-chat />',
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{
        path: '/',
        component: AppLayout,
        children: [
          { path: '', component: ChatView },
          { path: 'other', component: { template: '<div />' } },
        ],
      }],
    })
    await router.push('/')
    await router.isReady()
    mount({ template: '<router-view />' }, { global: { plugins: [createPinia(), router] } })
    document.dispatchEvent(new Event('review-effect'))
    expect(effect).toHaveBeenCalledOnce()

    await router.push('/other')
    await nextTick()
    document.dispatchEvent(new Event('review-effect'))
    expect(effect).toHaveBeenCalledOnce()

    await router.push('/')
    await nextTick()
    document.dispatchEvent(new Event('review-effect'))
    expect(effect).toHaveBeenCalledTimes(2)
  })
})

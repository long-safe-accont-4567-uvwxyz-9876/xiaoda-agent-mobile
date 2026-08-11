import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import CapabilityDrawer from './CapabilityDrawer.vue'
import MobileBottomNav from './MobileBottomNav.vue'
import QuickStatusSheet from './QuickStatusSheet.vue'
import { capabilities } from '../../navigation/capabilities'
import { useAgentsStore } from '../../stores/agents'
import { useChatStore } from '../../stores/chat'

async function mountWithRouter(component: object, props: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: capabilities.map(capability => ({
      path: capability.path,
      name: capability.routeName,
      component: { template: '<div />' },
    })),
  })
  await router.push('/')
  await router.isReady()
  return mount(component, { props, attachTo: document.body, global: { plugins: [router] } })
}

describe('移动导航', () => {
  it('能力抽屉将 Tab 焦点限制在对话框中', async () => {
    const wrapper = mount(CapabilityDrawer, {
      props: { open: true },
      global: { stubs: { RouterLink: { template: '<a href="#"><slot /></a>' }, SumeruIcon: true } },
      attachTo: document.body,
    })
    await nextTick()
    const dialog = wrapper.find<HTMLElement>('[role="dialog"]')
    const focusable = dialog.element.querySelectorAll<HTMLElement>('button, input, a[href]')
    const last = focusable[focusable.length - 1]
    last.focus()
    await dialog.trigger('keydown', { key: 'Tab' })
    expect(dialog.element.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).toBe(focusable[0])
    wrapper.unmount()
  })

  it('快捷状态将 Shift+Tab 焦点限制在对话框中', async () => {
    const pinia = createPinia()
    const wrapper = mount(QuickStatusSheet, {
      props: { open: true },
      global: { plugins: [pinia], stubs: { RouterLink: { template: '<a href="#"><slot /></a>' } } },
      attachTo: document.body,
    })
    await nextTick()
    const dialog = wrapper.find<HTMLElement>('[role="dialog"]')
    const focusable = dialog.element.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]')
    focusable[0].focus()
    await dialog.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(focusable[focusable.length - 1])
    wrapper.unmount()
  })

  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => { document.body.innerHTML = '' })

  it('底栏提供五个可辨识且不少于 48dp 的入口', async () => {
    const wrapper = await mountWithRouter(MobileBottomNav)
    const links = wrapper.findAll('[data-bottom-capability]')
    expect(links).toHaveLength(5)
    expect(links.every(link => Boolean(link.attributes('aria-label')))).toBe(true)
    expect(wrapper.text()).toContain('当前')
    expect(wrapper.html()).toContain('min-height: 48px')
  })

  it('抽屉搜索、高亮当前路由并在跳转后关闭', async () => {
    const wrapper = await mountWithRouter(CapabilityDrawer, { open: true })
    expect(wrapper.findAll('[data-capability-group]')).toHaveLength(4)
    await wrapper.find('input[type="search"]').setValue('邮箱')
    expect(wrapper.text()).toContain('邮箱管理')
    expect(wrapper.text()).not.toContain('媒体工坊')
    await wrapper.find('[data-capability-link]').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('快捷状态使用 Agent、连接与模型真实状态', async () => {
    const agents = useAgentsStore()
    agents.agents = [{
      name: 'xiaoda', display_name: '小妲', display_name_en: 'Xiaoda', builtin: true,
      is_main: true, enabled: true, provider: 'mimo', model: 'mimo-v2.5', tool_count: 8,
      mcp_servers: [],
    }]
    const chat = useChatStore()
    chat.wsConnected = false
    chat.notifications.push({ id: 'warning', content: '请求失败', timestamp: Date.now(), read: false })
    const wrapper = await mountWithRouter(QuickStatusSheet, { open: true })
    expect(wrapper.text()).toContain('小妲')
    expect(wrapper.text()).toContain('mimo')
    expect(wrapper.text()).toContain('mimo-v2.5')
    expect(wrapper.text()).toContain('离线')
    expect(wrapper.text()).toContain('1 条未读')
  })

  it('快捷状态展示真实降级与模型未配置状态', async () => {
    const agents = useAgentsStore()
    agents.agents = [{
      name: 'xiaoda', display_name: '小妲', display_name_en: 'Xiaoda', builtin: true,
      is_main: true, enabled: true, provider: '', model: '', degraded: true, tool_count: 8,
      mcp_servers: [],
    }]
    const wrapper = await mountWithRouter(QuickStatusSheet, { open: true })
    expect(wrapper.text()).toContain('降级运行')
    expect(wrapper.text()).toContain('模型未配置')
  })

  it('历史系统消息不冒充通知且通知支持已读语义', async () => {
    const chat = useChatStore()
    chat.messages.push({ id: 'history', role: 'system', content: '历史状态', timestamp: Date.now() })
    chat.notifications.push({ id: 'notice', content: '连接失败', timestamp: Date.now(), read: false })
    const wrapper = await mountWithRouter(QuickStatusSheet, { open: true })
    expect(wrapper.text()).toContain('1 条未读')
    await wrapper.get('[data-mark-notifications-read]').trigger('click')
    expect(wrapper.text()).toContain('0 条未读')
  })

  it.each([
    ['全部能力', CapabilityDrawer],
    ['快捷状态', QuickStatusSheet],
  ])('%s 对话框打开后获得焦点并支持 Escape 关闭', async (_name, component) => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const wrapper = await mountWithRouter(component, { open: true })
    await wrapper.vm.$nextTick()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.element.contains(document.activeElement)).toBe(true)
    await dialog.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('update:open')).toContainEqual([false])
    await wrapper.setProps({ open: false } as never)
    wrapper.unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('连接状态同时提供文字与机器可读状态', async () => {
    const chat = useChatStore()
    chat.wsConnected = false
    chat.wsReconnecting = true
    const wrapper = await mountWithRouter(QuickStatusSheet, { open: true })
    const status = wrapper.get('[data-connection-status]')
    expect(status.text()).toBe('重连中')
    expect(status.attributes('data-state')).toBe('reconnecting')
    expect(status.attributes('aria-label')).toContain('重连中')
  })

  it('通知集合保持有界', () => {
    const chat = useChatStore()
    for (let index = 0; index < 120; index += 1) chat.addNotification(`通知 ${index}`)
    expect(chat.notifications).toHaveLength(100)
    expect(chat.notifications[0].content).toBe('通知 20')
  })
})

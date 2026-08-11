export type CapabilityGroup = 'primary' | 'orchestration' | 'extensions' | 'operations' | 'models'
export type MobilePlacement = 'bottom' | 'drawer' | 'settings'

export interface CapabilityEntry {
  routeName: string
  path: string
  labelKey: string
  icon: string
  group: CapabilityGroup
  mobilePlacement: MobilePlacement
  order: number
  enabled: boolean
  searchTerms: string[]
}

export const capabilities: CapabilityEntry[] = [
  { routeName: 'chat', path: '/', labelKey: 'nav.chat', icon: 'chat', group: 'primary', mobilePlacement: 'bottom', order: 10, enabled: true, searchTerms: ['聊天', '对话', 'chat'] },
  { routeName: 'insight', path: '/insight', labelKey: 'nav.insight', icon: 'insight', group: 'orchestration', mobilePlacement: 'bottom', order: 30, enabled: true, searchTerms: ['记忆', '洞察', 'insight'] },
  { routeName: 'schedule', path: '/schedule', labelKey: 'nav.schedule', icon: 'schedule', group: 'orchestration', mobilePlacement: 'drawer', order: 40, enabled: true, searchTerms: ['计划', '定时', 'schedule'] },
  { routeName: 'media', path: '/media', labelKey: 'nav.media', icon: 'media', group: 'extensions', mobilePlacement: 'drawer', order: 40, enabled: true, searchTerms: ['媒体', 'media'] },
  { routeName: 'health', path: '/health', labelKey: 'nav.health', icon: 'health', group: 'operations', mobilePlacement: 'drawer', order: 10, enabled: true, searchTerms: ['健康', '测试', 'health'] },
  { routeName: 'dashboard', path: '/dashboard', labelKey: 'nav.dashboard', icon: 'dashboard', group: 'operations', mobilePlacement: 'drawer', order: 20, enabled: true, searchTerms: ['仪表盘', 'dashboard'] },
  { routeName: 'agents', path: '/settings/agents', labelKey: 'nav.agents', icon: 'agents', group: 'orchestration', mobilePlacement: 'bottom', order: 20, enabled: true, searchTerms: ['智能体', 'agent'] },
  { routeName: 'models', path: '/settings/models', labelKey: 'nav.models', icon: 'models', group: 'models', mobilePlacement: 'drawer', order: 10, enabled: true, searchTerms: ['模型', '服务商', 'provider', 'model'] },
  { routeName: 'tools', path: '/settings/tools', labelKey: 'nav.tools', icon: 'tools', group: 'primary', mobilePlacement: 'bottom', order: 40, enabled: true, searchTerms: ['工具', 'skills', 'tools'] },
  { routeName: 'mcp', path: '/settings/mcp', labelKey: 'nav.mcp', icon: 'mcp', group: 'extensions', mobilePlacement: 'drawer', order: 10, enabled: true, searchTerms: ['mcp', '服务'] },
  { routeName: 'plugins', path: '/settings/plugins', labelKey: 'nav.plugins', icon: 'plugins', group: 'extensions', mobilePlacement: 'drawer', order: 20, enabled: true, searchTerms: ['插件', 'plugins'] },
  { routeName: 'mail', path: '/settings/mail', labelKey: 'nav.mail', icon: 'mail', group: 'extensions', mobilePlacement: 'drawer', order: 30, enabled: true, searchTerms: ['邮箱', '邮件', 'mail'] },
  { routeName: 'settings', path: '/settings/system', labelKey: 'nav.settings', icon: 'settings', group: 'primary', mobilePlacement: 'bottom', order: 50, enabled: true, searchTerms: ['设置', '系统', 'settings'] },
  { routeName: 'workflows', path: '/workflows', labelKey: 'nav.workflows', icon: 'flow', group: 'orchestration', mobilePlacement: 'drawer', order: 10, enabled: true, searchTerms: ['工作流', 'workflow'] },
  { routeName: 'disclaimer', path: '/disclaimer', labelKey: 'nav.disclaimer', icon: 'alert', group: 'operations', mobilePlacement: 'drawer', order: 30, enabled: true, searchTerms: ['免责声明', 'disclaimer'] },
  { routeName: 'sponsor', path: '/sponsor', labelKey: 'sponsor.navTitle', icon: 'tea', group: 'operations', mobilePlacement: 'drawer', order: 40, enabled: true, searchTerms: ['赞助', '支持', 'sponsor'] },
]

export const desktopCapabilities = capabilities.filter(item => item.enabled)

export const bottomCapabilities = capabilities
  .filter(item => item.enabled && item.mobilePlacement === 'bottom')
  .sort((left, right) => left.order - right.order)

const groupDefinitions = [
  { id: 'orchestration' as const, label: '智能体与编排' },
  { id: 'extensions' as const, label: '扩展与连接' },
  { id: 'operations' as const, label: '运维与信息' },
  { id: 'models' as const, label: '模型与服务商' },
]

export const capabilityGroups = groupDefinitions.map(group => ({
  ...group,
  items: capabilities
    .filter(item => item.enabled && item.mobilePlacement !== 'bottom' && item.group === group.id)
    .sort((left, right) => left.order - right.order),
}))

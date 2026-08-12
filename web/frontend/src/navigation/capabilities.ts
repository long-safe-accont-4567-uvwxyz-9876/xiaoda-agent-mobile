/**
 * 导航与能力事实源（Capability Registry）
 *
 * 这里是桌面侧栏、移动端底部导航、全部能力抽屉的唯一数据来源。
 * 任何新增/删除/改名生产路由，都必须同步维护本表；
 * 否则 `capabilities.test.ts` 的一致性测试会失败。
 *
 * 字段约定：
 * - `id`        能力唯一 ID，也是路由的 `name`。
 * - `route`     完整路由路径（vue-router path）。
 * - `routeName` vue-router 路由 `name`，用于精确匹配与高亮。
 * - `labelKey`  i18n 标签键，用于桌面/移动共享文案。
 * - `icon`      SumeruIcon 图标名。
 * - `group`     能力分组（四类，见 capabilityGroups）。
 * - `sort`      组内展示顺序（升序）。
 * - `mobile`    移动端底部导航槽位（1~5），`null` 表示仅存在于全部能力抽屉。
 */
export type CapabilityGroup = 'conversation' | 'agents' | 'content' | 'system'

export interface Capability {
  id: string
  route: string
  routeName: string
  labelKey: string
  icon: string
  group: CapabilityGroup
  sort: number
  mobile: number | null
}

/** 能力分组（抽屉与移动导航的分组标题来源） */
export const capabilityGroups: ReadonlyArray<{
  id: CapabilityGroup
  labelKey: string
}> = [
  { id: 'conversation', labelKey: 'nav.group.conversation' },
  { id: 'agents', labelKey: 'nav.group.agents' },
  { id: 'content', labelKey: 'nav.group.content' },
  { id: 'system', labelKey: 'nav.group.system' },
]

/** 全部现有生产路由能力表（与 routes.ts 保持一致） */
export const capabilities: ReadonlyArray<Capability> = [
  // ── conversation 对话 ──────────────────────────────
  { id: 'chat', route: '/', routeName: 'chat', labelKey: 'nav.chat', icon: 'chat', group: 'conversation', sort: 10, mobile: 1 },

  // ── agents Agent 与工具 ────────────────────────────
  { id: 'agents', route: '/settings/agents', routeName: 'agents', labelKey: 'nav.agents', icon: 'agents', group: 'agents', sort: 10, mobile: 2 },
  { id: 'insight', route: '/insight', routeName: 'insight', labelKey: 'nav.insight', icon: 'insight', group: 'agents', sort: 20, mobile: 3 },
  { id: 'models', route: '/settings/models', routeName: 'models', labelKey: 'nav.models', icon: 'models', group: 'agents', sort: 30, mobile: null },
  { id: 'tools', route: '/settings/tools', routeName: 'tools', labelKey: 'nav.tools', icon: 'tools', group: 'agents', sort: 40, mobile: 4 },
  { id: 'mcp', route: '/settings/mcp', routeName: 'mcp', labelKey: 'nav.mcp', icon: 'mcp', group: 'agents', sort: 50, mobile: null },
  { id: 'workflows', route: '/workflows', routeName: 'workflows', labelKey: 'nav.workflows', icon: 'flow', group: 'agents', sort: 60, mobile: null },
  { id: 'plugins', route: '/settings/plugins', routeName: 'plugins', labelKey: 'nav.plugins', icon: 'plugins', group: 'agents', sort: 70, mobile: null },

  // ── content 内容与感知 ─────────────────────────────
  { id: 'schedule', route: '/schedule', routeName: 'schedule', labelKey: 'nav.schedule', icon: 'schedule', group: 'content', sort: 10, mobile: null },
  { id: 'mail', route: '/settings/mail', routeName: 'mail', labelKey: 'nav.mail', icon: 'mail', group: 'content', sort: 20, mobile: null },
  { id: 'media', route: '/media', routeName: 'media', labelKey: 'nav.media', icon: 'media', group: 'content', sort: 30, mobile: null },
  { id: 'health', route: '/health', routeName: 'health', labelKey: 'nav.health', icon: 'health', group: 'content', sort: 40, mobile: null },
  { id: 'dashboard', route: '/dashboard', routeName: 'dashboard', labelKey: 'nav.dashboard', icon: 'dashboard', group: 'content', sort: 50, mobile: null },

  // ── system 系统与账号 ──────────────────────────────
  { id: 'settings', route: '/settings/system', routeName: 'settings', labelKey: 'nav.settings', icon: 'settings', group: 'system', sort: 10, mobile: 5 },
  { id: 'disclaimer', route: '/disclaimer', routeName: 'disclaimer', labelKey: 'nav.disclaimer', icon: 'alert', group: 'system', sort: 20, mobile: null },
  { id: 'sponsor', route: '/sponsor', routeName: 'sponsor', labelKey: 'sponsor.navTitle', icon: 'tea', group: 'system', sort: 30, mobile: null },
]

/** 底部导航槽位（1~5）对应的能力，按槽位排序 */
export const bottomNavCapabilities: ReadonlyArray<Capability> = capabilities
  .filter((c) => c.mobile !== null)
  .sort((a, b) => (a.mobile! - b.mobile!))

/** 按分组聚合并保持组内 sort 顺序 */
export function capabilitiesByGroup(group: CapabilityGroup): ReadonlyArray<Capability> {
  return capabilities
    .filter((c) => c.group === group)
    .sort((a, b) => a.sort - b.sort)
}

/** 按 ID 查找能力 */
export function getCapability(id: string): Capability | undefined {
  return capabilities.find((c) => c.id === id)
}
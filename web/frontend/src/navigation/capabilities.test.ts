import { describe, expect, it } from 'vitest'
import { capabilities, capabilityGroups, bottomNavCapabilities } from './capabilities'
import { routes } from '../routes'

/** 收集 AppLayout 下全部生产子路由（普通路由对象） */
function collectProductionRoutes() {
  const layout = routes.find((r) => r.path === '/')
  if (!layout || !layout.children) return []
  return layout.children.filter((c) => typeof c.path === 'string')
}

describe('G3-01 导航事实源一致性', () => {
  it('每条生产路由都有对应能力条目', () => {
    const capIds = new Set(capabilities.map((c) => c.id))
    const capRoutes = new Set(capabilities.map((c) => c.route))
    const childRoutes = collectProductionRoutes()

    for (const child of childRoutes) {
      const fullPath = `/${child.path}`
      // / 与空 path 归一化
      const normalized = fullPath === '/' ? '/' : fullPath.replace(/\/$/, '')
      expect(capRoutes.has(normalized), `路由 ${normalized} 缺少能力条目`).toBe(true)
      // 每个 child 的 name 必须存在且唯一
      expect(child.name, `路由 ${normalized} 缺少 name`).toBeTruthy()
      const name = String(child.name!)
      expect(capIds.has(name), `能力 ID ${name} 未在能力表中声明`).toBe(true)
    }
  })

  it('每条能力条目都对应一条真实路由', () => {
    const childRoutes = collectProductionRoutes()
    const routeMap = new Map<string, string | symbol>()
    for (const child of childRoutes) {
      const fullPath = `/${child.path}`
      const normalized = fullPath === '/' ? '/' : fullPath.replace(/\/$/, '')
      routeMap.set(normalized, child.name ?? '')
    }

    for (const cap of capabilities) {
      expect(routeMap.has(cap.route), `能力 ${cap.id} 的路由 ${cap.route} 不存在`).toBe(true)
      expect(String(routeMap.get(cap.route)), `能力 ${cap.id} 路由名与路由表不一致`).toBe(cap.routeName)
    }
  })

  it('能力 ID 与路由名唯一', () => {
    const ids = capabilities.map((c) => c.id)
    const names = capabilities.map((c) => c.routeName)
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(names).size).toBe(names.length)
  })

  it('底部导航槽位唯一且不超过五个', () => {
    const slots = bottomNavCapabilities.map((c) => c.mobile)
    expect(new Set(slots).size).toBe(slots.length)
    expect(slots.length).toBeLessThanOrEqual(5)
    for (const s of slots) {
      expect(s).toBeGreaterThanOrEqual(1)
      expect(s).toBeLessThanOrEqual(5)
    }
  })

  it('分组声明完整且每条能力都归属已声明分组', () => {
    const groupIds = new Set(capabilityGroups.map((g) => g.id))
    for (const cap of capabilities) {
      expect(groupIds.has(cap.group), `能力 ${cap.id} 的分组 ${cap.group} 未声明`).toBe(true)
    }
  })

  it('每个分组内 sort 唯一', () => {
    for (const g of capabilityGroups) {
      const sorts = capabilities.filter((c) => c.group === g.id).map((c) => c.sort)
      expect(new Set(sorts).size, `分组 ${g.id} 存在重复 sort`).toBe(sorts.length)
    }
  })
})
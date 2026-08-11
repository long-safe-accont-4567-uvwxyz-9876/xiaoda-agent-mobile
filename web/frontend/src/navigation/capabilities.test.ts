import { describe, expect, it } from 'vitest'
import { productionRoutes } from '../routes'
import { bottomCapabilities, capabilities, capabilityGroups } from './capabilities'

describe('导航能力事实源', () => {
  it('覆盖全部生产路由且不包含重复入口', () => {
    const routeNames = productionRoutes.map(route => route.name)
    const capabilityNames = capabilities.map(capability => capability.routeName)
    expect(capabilityNames).toEqual(routeNames)
    expect(new Set(capabilityNames).size).toBe(capabilityNames.length)
    expect(capabilities.map(capability => capability.path)).toEqual(
      productionRoutes.map(route => `/${route.path}`.replace(/\/$/, '/')),
    )
    expect(productionRoutes.every(route => route.meta?.capabilityId === route.name)).toBe(true)
  })

  it('提供固定顺序的五个底栏入口', () => {
    expect(bottomCapabilities.map(capability => capability.routeName)).toEqual([
      'chat', 'agents', 'insight', 'tools', 'settings',
    ])
  })

  it('将抽屉能力归入四个可搜索分组', () => {
    expect(capabilityGroups.map(group => group.id)).toEqual([
      'orchestration', 'extensions', 'operations', 'models',
    ])
    expect(capabilityGroups.flatMap(group => group.items).map(item => item.routeName).sort())
      .toEqual(capabilities.filter(item => item.mobilePlacement !== 'bottom').map(item => item.routeName).sort())
  })

  it('每项能力提供可搜索文本与有效图标', () => {
    expect(capabilities.every(item => item.icon && item.searchTerms.length > 0)).toBe(true)
  })
})

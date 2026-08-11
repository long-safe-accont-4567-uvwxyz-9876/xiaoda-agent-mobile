import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { productionRoutes } from '../routes'

const mobileStylesPath = resolve(process.cwd(), 'src/styles/mobile-pages.css')

const productionPages: Record<string, { file: string; selector: string }> = {
  chat: { file: 'ChatView.vue', selector: '.chat-view' },
  insight: { file: 'InsightView.vue', selector: '.insight-view' },
  schedule: { file: 'ScheduleView.vue', selector: '.schedule-view' },
  media: { file: 'MediaView.vue', selector: '.media-view' },
  health: { file: 'HealthView.vue', selector: '.health-view' },
  dashboard: { file: 'DashboardView.vue', selector: '.dashboard-view' },
  agents: { file: 'AgentsView.vue', selector: '.agents-view' },
  models: { file: 'ModelsView.vue', selector: '.models-view' },
  tools: { file: 'ToolsView.vue', selector: '.tools-view' },
  mcp: { file: 'McpView.vue', selector: '.mcp-view' },
  plugins: { file: 'PluginsView.vue', selector: '.plugins-view' },
  mail: { file: 'MailView.vue', selector: '.mail-view' },
  settings: { file: 'SettingsView.vue', selector: '.settings-view' },
  workflows: { file: 'WorkflowView.vue', selector: '.workflows-view' },
  disclaimer: { file: 'DisclaimerView.vue', selector: '.disclaimer-page' },
  sponsor: { file: 'SponsorView.vue', selector: '.sponsor-page' },
}

const readPage = (file: string) => readFileSync(resolve(process.cwd(), 'src/views', file), 'utf8')

describe('生产页面移动适配契约', () => {
  it('覆盖能力表中的全部生产页面', () => {
    const routeIds = productionRoutes.map(route => String(route.meta?.capabilityId))
    expect(Object.keys(productionPages).sort()).toEqual(routeIds.sort())

    const css = readFileSync(mobileStylesPath, 'utf8')
    for (const page of Object.values(productionPages)) {
      expect(readPage(page.file)).toContain(`class="${page.selector.slice(1)}`)
      expect(css).toContain(page.selector)
    }
  })

  it('提供手机横竖屏、紧凑屏与桌面隔离规则', () => {
    const css = readFileSync(mobileStylesPath, 'utf8')
    const responsiveSource = readFileSync(resolve(process.cwd(), 'src/composables/useResponsiveShell.ts'), 'utf8')
    expect(css).toMatch(/@media\s*\(max-width:\s*767px\)/)
    expect(css).toMatch(/@media\s*\(max-width:\s*767px\)\s*and\s*\(orientation:\s*landscape\)/)
    expect(css).toMatch(/@media\s*\(min-width:\s*768px\)\s*and\s*\(max-width:\s*1023px\)/)
    expect(css).not.toMatch(/@media\s*\(min-width:\s*1024px\)/)
    expect(responsiveSource).toContain("'(max-width: 767px)'")
  })

  it('约束横向内容、触控热区、全屏编辑器和安全区', () => {
    const css = readFileSync(mobileStylesPath, 'utf8')
    expect(css).toContain('overflow-x: auto')
    expect(css).toContain('overflow-x: clip')
    const mobileRootBlock = css.match(/@media \(max-width: 767px\) \{([\s\S]*?):is\(\.view-header/)?.[1] || ''
    expect(mobileRootBlock).not.toContain('overflow-x: auto')
    expect(css).toContain('min-height: 48px')
    expect(css).toContain('min-width: 48px')
    expect(css).toContain('100dvh')
    expect(css).toContain('env(safe-area-inset-bottom)')
    expect(css).toContain('overscroll-behavior-x: contain')
  })

  it('逐页落实页面表中的移动交互重点', () => {
    const css = readFileSync(mobileStylesPath, 'utf8')
    const pageContracts = [
      '.chat-view .chat-toolbar',
      '.insight-view .kg-section',
      '.schedule-view .greeting-card',
      '.media-view .panel.side',
      '.health-view .probe-grid',
      '.dashboard-view .chart-row',
      '.agents-view .agent-grid',
      '.models-view .provider-ops',
      '.tools-view .tool-actions',
      '.mcp-view .server-ops',
      '.plugins-view .plugin-ops',
      '.mail-view .connect-step',
      '.settings-view .setting-row',
      '.workflows-view .editor-section',
      '.disclaimer-page .disclaimer-card',
      '.sponsor-page .sponsor-card',
    ]
    for (const contract of pageContracts) {
      expect(css).toContain(contract)
    }
  })

  it('为异步页面状态保留移动端可读布局', () => {
    const css = readFileSync(mobileStylesPath, 'utf8')
    for (const selector of [
      '.empty-state', '.empty-hint', '.n-empty', '.error-hint', '.plugin-error',
      '.server-error', '.task-error', '.error-cell', '.info-text.error', '.n-spin-container',
    ]) {
      expect(css).toContain(selector)
    }
  })

  it('扫描16个生产页的固定宽度与横向裁切风险', () => {
    const riskyPages = Object.values(productionPages).filter(({ file }) => {
      const source = readPage(file)
      return /(?:width|min-width)\s*:\s*(?:[3-9]\d{2}|\d{4,})px/.test(source)
        || /overflow-x\s*:\s*(?:hidden|clip)/.test(source)
    })
    const css = readFileSync(mobileStylesPath, 'utf8')
    for (const page of riskyPages) {
      expect(css).toContain(page.selector)
    }
    expect(css).toContain('overflow-wrap: anywhere')
  })
})

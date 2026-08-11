import { describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useResponsiveShell } from './useResponsiveShell'

describe('响应式壳', () => {
  it('随断点变化只切换壳状态', () => {
    let listener: ((event: MediaQueryListEvent) => void) | undefined
    const media = {
      matches: false,
      addEventListener: vi.fn((_name, callback) => { listener = callback }),
      removeEventListener: vi.fn(),
    }
    vi.spyOn(window, 'matchMedia').mockReturnValue(media as unknown as MediaQueryList)
    const scope = effectScope()
    const state = scope.run(() => useResponsiveShell())!
    expect(state.isMobile.value).toBe(false)
    listener?.({ matches: true } as MediaQueryListEvent)
    expect(state.isMobile.value).toBe(true)
    scope.stop()
    expect(media.removeEventListener).toHaveBeenCalledOnce()
  })
})

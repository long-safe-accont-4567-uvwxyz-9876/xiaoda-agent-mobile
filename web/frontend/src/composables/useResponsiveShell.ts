import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

/**
 * 响应式壳选择
 * - < 768px  → mobile（移动壳：底部导航 + 抽屉）
 * - 768–1023 → tablet（紧凑壳，当前按桌面壳处理）
 * - >= 1024  → desktop（桌面壳：侧栏）
 *
 * 断点只决定布局壳，绝不决定业务能力是否存在。
 */
export type ShellMode = 'mobile' | 'tablet' | 'desktop'

const MOBILE_QUERY = '(max-width: 767px)'
const TABLET_QUERY = '(min-width: 768px) and (max-width: 1023px)'

export function useResponsiveShell() {
  const mode = ref<ShellMode>('desktop')

  const isMobile = computed(() => mode.value === 'mobile')
  const isTablet = computed(() => mode.value === 'tablet')
  const isDesktop = computed(() => mode.value === 'desktop')

  // 移动壳：mobile（<768px 使用移动壳；tablet 也走移动壳以兼容竖屏紧凑宽）
  const useMobileShell = computed(() => mode.value !== 'desktop')

  let mqMobile: MediaQueryList
  let mqTablet: MediaQueryList

  function update() {
    if (mqMobile.matches) mode.value = 'mobile'
    else if (mqTablet.matches) mode.value = 'tablet'
    else mode.value = 'desktop'
  }

  onMounted(() => {
    mqMobile = window.matchMedia(MOBILE_QUERY)
    mqTablet = window.matchMedia(TABLET_QUERY)
    update()
    mqMobile.addEventListener('change', update)
    mqTablet.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    mqMobile?.removeEventListener('change', update)
    mqTablet?.removeEventListener('change', update)
  })

  return { mode, isMobile, isTablet, isDesktop, useMobileShell }
}
import { ref, onMounted, onBeforeUnmount } from 'vue'

export interface ViewportInsets {
  top: number
  right: number
  bottom: number
  left: number
  /** 虚拟键盘遮挡高度（px），无键盘为 0 */
  keyboard: number
}

/** 通过探针元素读取 CSS env(safe-area-inset-*) 实际像素值 */
function measureSafeArea(edge: 'top' | 'right' | 'bottom' | 'left'): number {
  const el = document.createElement('div')
  el.style.position = 'fixed'
  el.style.visibility = 'hidden'
  el.style.pointerEvents = 'none'
  ;(el.style as any)[`padding${edge.charAt(0).toUpperCase()}${edge.slice(1)}`] =
    `env(safe-area-inset-${edge})`
  document.body.appendChild(el)
  const v = parseFloat(getComputedStyle(el).getPropertyValue(`padding-${edge}`)) || 0
  el.remove()
  return v
}

/**
 * 视口安全区与键盘遮挡监听。
 * 用于移动壳的底栏、Sheet 与终端的 safe-area / 键盘自适应。
 */
export function useViewportInsets() {
  const insets = ref<ViewportInsets>({ top: 0, right: 0, bottom: 0, left: 0, keyboard: 0 })

  function update() {
    insets.value = {
      top: measureSafeArea('top'),
      right: measureSafeArea('right'),
      bottom: measureSafeArea('bottom'),
      left: measureSafeArea('left'),
      keyboard: 0,
    }
    const vv = window.visualViewport
    if (vv && window.innerHeight - vv.height > 0) {
      insets.value.keyboard = window.innerHeight - vv.height
    }
  }

  onMounted(() => {
    update()
    window.visualViewport?.addEventListener('resize', update)
    window.addEventListener('resize', update)
  })

  onBeforeUnmount(() => {
    window.visualViewport?.removeEventListener('resize', update)
    window.removeEventListener('resize', update)
  })

  return { insets }
}
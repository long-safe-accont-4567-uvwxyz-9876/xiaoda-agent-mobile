import { onScopeDispose, ref } from 'vue'

export const MOBILE_SHELL_QUERY = '(max-width: 767px)'

export function useResponsiveShell() {
  const media = window.matchMedia(MOBILE_SHELL_QUERY)
  const isMobile = ref(media.matches)
  const update = (event: MediaQueryListEvent) => { isMobile.value = event.matches }

  media.addEventListener('change', update)
  onScopeDispose(() => media.removeEventListener('change', update))

  return { isMobile }
}

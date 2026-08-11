import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import i18n from './i18n'

async function startMobileApp() {
  const { default: MobileApp } = await import('./MobileApp.vue')
  createApp(MobileApp).mount('#app')
}

async function startDesktopApp() {
  const [{ default: App }, { routes }, { useAuthStore }, { loadAgentNames }] = await Promise.all([
    import('./App.vue'),
    import('./routes'),
    import('./stores/auth'),
    import('./utils/agentNames'),
  ])
  const pinia = createPinia()
  const router = createRouter({ history: createWebHashHistory(), routes })

  router.beforeEach((to, _from, next) => {
    if (to.meta?.requiresAuth) {
      const auth = useAuthStore()
      if (!auth.isLoggedIn) {
        next({ name: 'login' })
        return
      }
    }
    next()
  })

  router.onError((error, to) => {
    const msg = String(error?.message || error)
    if (/failed to fetch dynamically imported module|loading.*chunk|import/i.test(msg)) {
      const key = 'chunk-reload-ts'
      const last = Number(sessionStorage.getItem(key) || 0)
      if (Date.now() - last > 10_000) {
        sessionStorage.setItem(key, String(Date.now()))
        location.href = location.origin + location.pathname + '#' + (to?.fullPath || '/')
        location.reload()
      }
    } else {
      console.error('[router]', error)
    }
  })

  const app = createApp(App)
  app.use(pinia)
  app.use(router)
  app.use(i18n)
  app.mount('#app')

  const auth = useAuthStore()
  if (auth.isLoggedIn) {
    loadAgentNames()
  } else {
    const unwatch = auth.$subscribe(() => {
      if (auth.isLoggedIn) {
        loadAgentNames()
        unwatch()
      }
    })
  }
}

if (import.meta.env.VITE_XIAODA_MOBILE_BUILD === '1') {
  void startMobileApp()
} else {
  void startDesktopApp()
}

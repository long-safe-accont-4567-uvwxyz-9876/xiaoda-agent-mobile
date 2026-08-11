<script setup lang="ts">
import { bottomCapabilities } from '../../navigation/capabilities'
import { t } from '../../i18n'
import SumeruIcon from '../fx/SumeruIcon.vue'
</script>

<template>
  <nav class="mobile-bottom-nav" aria-label="主要导航">
    <router-link v-for="item in bottomCapabilities" :key="item.routeName" :to="item.path"
      data-bottom-capability class="bottom-link" style="min-height: 48px" :aria-label="t(item.labelKey)">
      <span class="aurora-icon"><SumeruIcon :name="item.icon" :size="22" /></span>
      <span>{{ t(item.labelKey) }}</span>
      <span class="current-label">当前</span>
    </router-link>
  </nav>
</template>

<style scoped>
.mobile-bottom-nav { display: grid; grid-template-columns: repeat(5, 1fr); padding: 5px max(6px, env(safe-area-inset-right)) calc(5px + env(safe-area-inset-bottom)) max(6px, env(safe-area-inset-left)); background: rgba(10, 27, 21, 0.84); border-top: 1px solid rgba(184, 255, 133, 0.18); backdrop-filter: blur(20px) saturate(1.35); }
.bottom-link { position: relative; display: flex; min-width: 0; align-items: center; justify-content: center; flex-direction: column; gap: 2px; color: var(--moon-dim); text-decoration: none; font-size: 10px; border-radius: 15px; outline-offset: -2px; }
.aurora-icon { display: grid; place-items: center; width: 32px; height: 26px; border-radius: 14px; transition: transform .18s, background .18s, box-shadow .18s; }
.bottom-link:active .aurora-icon { transform: scale(.88); }
.bottom-link:focus-visible { outline: 2px solid var(--dendro-bright, #b8ff85); }
.bottom-link.router-link-exact-active { color: var(--dendro-bright, #b8ff85); font-weight: 700; }
.bottom-link.router-link-exact-active .aurora-icon { background: linear-gradient(135deg, rgba(184,255,133,.24), rgba(79,214,165,.13)); box-shadow: 0 0 18px rgba(127,214,80,.22), inset 0 0 10px rgba(255,255,255,.08); }
.current-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.bottom-link:not(.router-link-exact-active) .current-label { display: none; }
</style>

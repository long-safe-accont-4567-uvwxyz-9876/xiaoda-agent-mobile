<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SumeruIcon from '../fx/SumeruIcon.vue'
import { bottomNavCapabilities, type Capability } from '../../navigation/capabilities'
import { t } from '../../i18n'

const route = useRoute()

// 当前所在能力对应的底部槽位；不在五导航内时返回 null
const activeSlot = computed<number | null>(() => {
  const matched = bottomNavCapabilities.find(
    (c) => c.routeName === route.name || c.route === route.path,
  )
  return matched?.mobile ?? null
})

function isActive(item: Capability): boolean {
  return item.mobile === activeSlot.value
}
</script>

<template>
  <nav class="mobile-bottom-nav" aria-label="主导航">
    <!-- 极光玻璃背景 -->
    <svg class="aurora-bg" viewBox="0 0 400 64" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="bnav-aurora" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="rgba(143,229,96,0.30)" />
          <stop offset="50%" stop-color="rgba(79,214,165,0.22)" />
          <stop offset="100%" stop-color="rgba(184,255,133,0.28)" />
        </linearGradient>
        <filter id="bnav-blur" x="-40%" y="-200%" width="180%" height="500%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
      </defs>
      <g filter="url(#bnav-blur)">
        <ellipse cx="90" cy="30" rx="110" ry="42" fill="url(#bnav-aurora)" />
        <ellipse cx="310" cy="36" rx="130" ry="46" fill="rgba(232,213,163,0.18)" />
      </g>
    </svg>

    <div class="nav-inner">
      <router-link
        v-for="item in bottomNavCapabilities"
        :key="item.id"
        :to="item.route"
        class="nav-btn"
        :class="{ active: isActive(item) }"
        :aria-label="t(item.labelKey)"
        :aria-current="isActive(item) ? 'page' : undefined"
      >
        <span class="btn-icon"><SumeruIcon :name="item.icon" :size="24" /></span>
        <span class="btn-label">{{ t(item.labelKey) }}</span>
        <span class="btn-active-glow" aria-hidden="true"></span>
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.mobile-bottom-nav {
  position: relative;
  height: var(--bottom-nav-height, 64px);
  overflow: hidden;
  background: rgba(15, 31, 23, 0.72);
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
  border-top: 1px solid var(--glass-border);
  box-shadow: var(--glass-inner-glow);
}

.aurora-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  opacity: 0.9;
}

.nav-inner {
  position: relative;
  display: flex;
  align-items: stretch;
  height: 100%;
}

.nav-btn {
  flex: 1;
  min-width: var(--bottom-nav-touch, 48px);
  min-height: var(--bottom-nav-touch, 48px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: var(--moon-dim);
  text-decoration: none;
  position: relative;
  transition: color 0.25s var(--ease-smooth), transform 0.15s var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}

.nav-btn:focus-visible {
  outline: 2px solid var(--dendro);
  outline-offset: -3px;
  border-radius: 12px;
}

.nav-btn:active {
  transform: scale(0.92);
}

.nav-btn .btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.3s var(--ease-spring), filter 0.3s var(--ease-smooth);
}

.nav-btn .btn-label {
  font-size: 10px;
  line-height: 1;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

/* 选中态：不只靠颜色，图标上浮 + 光晕标记 */
.nav-btn.active {
  color: var(--dendro-bright);
}

.nav-btn.active .btn-icon {
  transform: translateY(-2px) scale(1.1);
  filter: drop-shadow(0 0 6px rgba(143, 229, 96, 0.6));
}

.nav-btn.active .btn-active-glow {
  position: absolute;
  top: 4px;
  width: 28px;
  height: 3px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--dendro-bright), var(--jade));
  box-shadow: 0 0 10px var(--dendro);
}
</style>
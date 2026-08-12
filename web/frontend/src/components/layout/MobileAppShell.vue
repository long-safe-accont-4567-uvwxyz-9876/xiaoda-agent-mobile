<script setup lang="ts">
// 移动壳：仅承载移动端导航/抽屉/状态浮层，不持有业务状态。
// - 能力入口（左上角） + 全部能力抽屉（G3-04）
// - 底部五导航（G3-03 MobileBottomNav）
// - 快捷状态（G3-05 QuickStatusSheet 挂载）
import { useViewportInsets } from '../../composables/useViewportInsets'
import MobileBottomNav from './MobileBottomNav.vue'
import CapabilityDrawer from './CapabilityDrawer.vue'
import QuickStatusSheet from './QuickStatusSheet.vue'
import { ref } from 'vue'
import SumeruIcon from '../fx/SumeruIcon.vue'
import { t } from '../../i18n'

const props = defineProps<{
  drawerOpen?: boolean
}>()

const emit = defineEmits<{
  'update:drawerOpen': [value: boolean]
}>()

const { insets } = useViewportInsets()
const statusOpen = ref(false)

function openDrawer() {
  emit('update:drawerOpen', true)
}

function onDrawerUpdate(open: boolean) {
  emit('update:drawerOpen', open)
}
</script>

<template>
  <div class="mobile-app-shell">
    <!-- G3-04 左上角能力入口 -->
    <button
      class="capability-entry"
      :style="{ top: `calc(env(safe-area-inset-top) + 8px)` }"
      :aria-label="t('nav.openDrawer')"
      @click="openDrawer"
    >
      <SumeruIcon name="menu" :size="22" />
    </button>

    <!-- G3-04 全部能力抽屉 -->
    <CapabilityDrawer :open="!!props.drawerOpen" @update:open="onDrawerUpdate" />

    <!-- G3-05 右上角快捷状态入口 -->
    <button
      class="status-entry"
      :style="{ top: `calc(env(safe-area-inset-top) + 8px)` }"
      :aria-label="t('nav.openStatus')"
      @click="statusOpen = true"
    >
      <SumeruIcon name="sprout" :size="22" />
    </button>

    <!-- G3-05 快捷状态 -->
    <QuickStatusSheet :open="statusOpen" @update:open="statusOpen = $event" />

    <!-- G3-03 底部五导航 -->
    <div
      class="mobile-dock"
      :style="{ paddingBottom: `${insets.bottom}px` }"
    >
      <MobileBottomNav />
    </div>

    <!-- G3-05 快捷状态挂载点 -->
  </div>
</template>

<style scoped>
.mobile-app-shell {
  position: fixed;
  inset: 0;
  z-index: var(--z-mobile-shell, 40);
  pointer-events: none;
}

.capability-entry {
  position: absolute;
  left: 8px;
  width: var(--bottom-nav-touch, 48px);
  height: var(--bottom-nav-touch, 48px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 31, 23, 0.6);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
  border-radius: 14px;
  color: var(--moon-dim);
  cursor: pointer;
  pointer-events: auto;
  z-index: var(--z-mobile-drawer, 50);
  transition: background 0.2s, color 0.2s, transform 0.2s var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}
.capability-entry:focus-visible { outline: 2px solid var(--dendro); outline-offset: 2px; }
.capability-entry:hover { background: rgba(143, 229, 96, 0.14); color: var(--moon); }
.capability-entry:active { transform: scale(0.9); }

.status-entry {
  position: absolute;
  right: 8px;
  width: var(--bottom-nav-touch, 48px);
  height: var(--bottom-nav-touch, 48px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 31, 23, 0.6);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  border: 1px solid var(--glass-border);
  border-radius: 14px;
  color: var(--moon-dim);
  cursor: pointer;
  pointer-events: auto;
  z-index: var(--z-mobile-sheet, 60);
  transition: background 0.2s, color 0.2s, transform 0.2s var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}
.status-entry:focus-visible { outline: 2px solid var(--dendro); outline-offset: 2px; }
.status-entry:hover { background: rgba(143, 229, 96, 0.14); color: var(--moon); }
.status-entry:active { transform: scale(0.9); }

.mobile-dock {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: auto;
}
</style>
<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useChatStore } from '../../stores/chat'
import { useAgentsStore } from '../../stores/agents'

const DEFAULT_BG = '/media/wallpapers/webui_background.jpg'

const chat = useChatStore()
const agentsStore = useAgentsStore()

const targetUrl = computed(() => {
  if (agentsStore.agents.length) {
    const a = agentsStore.agents.find(x => x.name === chat.currentAgent)
    if (a?.wallpaper) return a.wallpaper
  }
  return agentsStore.mainWallpaper || DEFAULT_BG
})

// G4-03/04：当前 Agent 的壁纸元数据（焦点/遮罩/动效），缺省向后兼容
const wallpaperMeta = computed(() => {
  const a = agentsStore.agents.find(x => x.name === chat.currentAgent)
  return {
    focus: a?.wallpaper_focus ?? [0.5, 0.35] as [number, number],
    overlay: a?.wallpaper_overlay ?? 0.28,
    motion: a?.wallpaper_motion ?? 'full',
  }
})
const bgPosition = computed(() => {
  const [x, y] = wallpaperMeta.value.focus
  return `${Math.round(x * 100)}% ${Math.round(y * 100)}%`
})
// 遮罩强度 = 用户 overlay，夹在 [0.15, 0.75]，保证文字可读
const tintOpacity = computed(() =>
  Math.min(0.75, Math.max(0.15, wallpaperMeta.value.overlay)),
)

interface Layer { url: string; key: number }
const layers = ref<Layer[]>([])
let seq = 0
let pendingUrl = ''
let pruneTimer: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  const initial = agentsStore.mainWallpaper || DEFAULT_BG
  pushLayer(initial)
})

onBeforeUnmount(() => {
  if (pruneTimer) { clearTimeout(pruneTimer); pruneTimer = null }
})

watch(targetUrl, (url) => {
  if (!url) return
  pendingUrl = url
  if (topUrl() === url) return
  const img = new Image()
  img.onload = () => { if (pendingUrl === url) pushLayer(url) }
  img.onerror = () => {
    if (pendingUrl !== url) return
    // 如果失败的 URL 本身就是 DEFAULT_BG，不再重试，直接显示 tint 底色
    if (url === DEFAULT_BG) return
    pushLayer(DEFAULT_BG)
  }
  img.src = url
})

function topUrl() {
  return layers.value[layers.value.length - 1]?.url
}

function sanitizeUrl(url: string): string {
  if (url.startsWith('/media/wallpapers/') || url.startsWith('/media/agents/')) return url
  if (url.startsWith('data:image/')) return url
  return DEFAULT_BG
}

function pushLayer(url: string) {
  url = sanitizeUrl(url)
  if (topUrl() === url) return
  layers.value.push({ url, key: ++seq })
  if (pruneTimer) clearTimeout(pruneTimer)
  pruneTimer = setTimeout(() => {
    if (layers.value.length > 1) layers.value.splice(0, layers.value.length - 1)
    pruneTimer = null
  }, 1400)
}
</script>

<template>
  <div class="agent-backdrop" :class="{ 'motion-reduced': wallpaperMeta.motion === 'reduced' }" aria-hidden="true">
    <transition-group name="bg-fade">
      <div
        v-for="l in layers"
        :key="l.key"
        class="backdrop-layer"
        :style="{ backgroundImage: `url('${l.url}')`, backgroundPosition: bgPosition }"
      />
    </transition-group>
    <div class="backdrop-tint" :style="{ opacity: tintOpacity }"></div>
  </div>
</template>

<style scoped>
.agent-backdrop {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  background: var(--forest-deep);
}

.backdrop-layer {
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
}

.bg-fade-enter-active {
  transition: opacity 1.1s var(--ease-smooth), transform 1.3s var(--ease-smooth);
}
.bg-fade-enter-from {
  opacity: 0;
  transform: scale(1.045);
}
.bg-fade-leave-active {
  transition: none;
}

.backdrop-tint {
  position: absolute;
  inset: 0;
  background: var(--backdrop-tint);
  pointer-events: none;
  opacity: calc(2 - var(--app-brightness, 1.05));
  transition: opacity 0.4s ease;
}

@media (prefers-reduced-motion: reduce) {
  .bg-fade-enter-from { transform: none; }
}

/* G4-04：Agent 显式请求 reduced 动效时，壁纸切换不做缩放/位移 */
.agent-backdrop.motion-reduced .bg-fade-enter-from { transform: none; }
.agent-backdrop.motion-reduced .bg-fade-enter-active { transition: opacity 0.6s ease; }
</style>
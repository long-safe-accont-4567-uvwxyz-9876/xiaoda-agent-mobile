<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useChatStore } from '../../stores/chat'
import { useAgentsStore, type AgentInfo } from '../../stores/agents'

const DEFAULT_BG = '/media/wallpapers/webui_background.jpg'
const DEFAULT_FOCUS = { x: 0.5, y: 0.5 }

const chat = useChatStore()
const agentsStore = useAgentsStore()
const prefersReducedMotion = ref(false)
const performanceTier = ref<'high' | 'medium' | 'low'>('high')

const activeAgent = computed<AgentInfo | undefined>(() =>
  agentsStore.agents.find(agent => agent.name === chat.currentAgent)
  || agentsStore.agents.find(agent => agent.is_main),
)

const targetUrl = computed(() =>
  activeAgent.value?.wallpaper || agentsStore.mainWallpaper || DEFAULT_BG,
)
const wallpaperFocus = computed(() => activeAgent.value?.wallpaper_focus || DEFAULT_FOCUS)
const wallpaperOverlay = computed(() => activeAgent.value?.wallpaper_overlay ?? 0.28)
const wallpaperMotion = computed(() => activeAgent.value?.wallpaper_motion || 'auto')
const motionEnabled = computed(() =>
  performanceTier.value === 'high'
  && wallpaperMotion.value === 'auto'
  && !prefersReducedMotion.value,
)
const backgroundPosition = computed(() => {
  const focus = wallpaperFocus.value
  return `${Math.round(focus.x * 100)}% ${Math.round(focus.y * 100)}%`
})
const backdropClass = computed(() => [
  `tier-${performanceTier.value}`,
  { 'motion-enabled': motionEnabled.value },
])
const overlayStyle = computed(() => ({
  '--wallpaper-overlay': String(Math.max(0, Math.min(1, wallpaperOverlay.value))),
}))

interface Layer { url: string; key: number }
const layers = ref<Layer[]>([])
let seq = 0
let pendingUrl = ''
let pruneTimer: ReturnType<typeof setTimeout> | null = null
let pendingImage: HTMLImageElement | null = null
let motionQuery: MediaQueryList | null = null

function detectPerformanceTier() {
  const memory = Number((navigator as Navigator & { deviceMemory?: number }).deviceMemory || 8)
  const cores = navigator.hardwareConcurrency || 8
  if (document.body.classList.contains('low-gpu') || memory <= 2 || cores <= 2) {
    performanceTier.value = 'low'
  } else if (memory <= 4 || cores <= 4) {
    performanceTier.value = 'medium'
  } else {
    performanceTier.value = 'high'
  }
}

function updateReducedMotion() {
  prefersReducedMotion.value = motionQuery?.matches ?? false
}

function releaseInactiveLayers() {
  pendingImage = null
  if (layers.value.length > 1) {
    layers.value.splice(0, layers.value.length - 1)
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') releaseInactiveLayers()
}

function onMemoryPressure() {
  performanceTier.value = 'low'
  releaseInactiveLayers()
}

onMounted(() => {
  detectPerformanceTier()
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  updateReducedMotion()
  motionQuery.addEventListener?.('change', updateReducedMotion)
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('pagehide', releaseInactiveLayers)
  window.addEventListener('memorypressure', onMemoryPressure as EventListener)
  pushLayer(targetUrl.value || DEFAULT_BG)
})

onBeforeUnmount(() => {
  if (pruneTimer) clearTimeout(pruneTimer)
  pendingImage = null
  motionQuery?.removeEventListener?.('change', updateReducedMotion)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('pagehide', releaseInactiveLayers)
  window.removeEventListener('memorypressure', onMemoryPressure as EventListener)
})

watch(targetUrl, (url) => {
  if (!url) return
  pendingUrl = url
  if (topUrl() === sanitizeUrl(url)) return
  const img = new Image()
  pendingImage = img
  img.decoding = 'async'
  img.onload = () => {
    if (pendingUrl === url) pushLayer(url)
    if (pendingImage === img) pendingImage = null
  }
  img.onerror = () => {
    if (pendingImage === img) pendingImage = null
    if (pendingUrl !== url || url === DEFAULT_BG) return
    pushLayer(DEFAULT_BG)
  }
  img.src = sanitizeUrl(url)
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
  if (performanceTier.value === 'low') {
    layers.value = [{ url, key: ++seq }]
    return
  }
  layers.value.push({ url, key: ++seq })
  if (pruneTimer) clearTimeout(pruneTimer)
  pruneTimer = setTimeout(() => {
    releaseInactiveLayers()
    pruneTimer = null
  }, motionEnabled.value ? 1400 : 250)
}
</script>

<template>
  <div class="agent-backdrop" :class="backdropClass" :style="overlayStyle" aria-hidden="true">
    <transition-group name="bg-fade">
      <div
        v-for="layer in layers"
        :key="layer.key"
        class="backdrop-layer"
        :style="{ backgroundImage: `url('${layer.url}')`, backgroundPosition }"
      />
    </transition-group>
    <div class="backdrop-tint"></div>
    <div class="backdrop-local-mask"></div>
  </div>
</template>

<style scoped>
.agent-backdrop {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100lvh;
  z-index: 0;
  overflow: hidden;
  contain: strict;
  background: var(--forest-deep);
}

.backdrop-layer {
  position: absolute;
  inset: -1px;
  background-size: cover;
  background-repeat: no-repeat;
  transform: translateZ(0) scale(1.001);
  will-change: opacity;
}

.motion-enabled .backdrop-layer {
  animation: wallpaper-drift 24s ease-in-out infinite alternate;
}

.bg-fade-enter-active {
  transition: opacity 1.1s var(--ease-smooth), transform 1.3s var(--ease-smooth);
}
.bg-fade-enter-from {
  opacity: 0;
  transform: translateZ(0) scale(1.035);
}
.bg-fade-leave-active { transition: none; }

.backdrop-tint {
  position: absolute;
  inset: 0;
  background: rgba(3, 10, 7, var(--wallpaper-overlay));
  pointer-events: none;
  transition: background-color 0.25s ease;
}

/* Local masks protect top navigation, message content and bottom controls without blurring the full image. */
.backdrop-local-mask {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(to bottom, rgba(3, 10, 7, 0.46), transparent 18%),
    linear-gradient(to top, rgba(3, 10, 7, 0.58), transparent 24%),
    radial-gradient(ellipse at center, transparent 20%, rgba(3, 10, 7, 0.2) 100%);
}

.backdrop-local-mask::before,
.backdrop-local-mask::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  pointer-events: none;
  backdrop-filter: blur(10px) saturate(0.9);
}
.backdrop-local-mask::before {
  top: 0;
  height: 18%;
  mask-image: linear-gradient(to bottom, #000 0%, transparent 100%);
}
.backdrop-local-mask::after {
  bottom: 0;
  height: 24%;
  mask-image: linear-gradient(to top, #000 0%, transparent 100%);
}

.tier-medium .backdrop-layer { animation: none; }
.tier-medium .bg-fade-enter-active { transition-duration: 0.45s; }
.tier-low .backdrop-layer { animation: none; filter: none; transform: none; }
.tier-low .bg-fade-enter-active { transition: none; }
.tier-low .backdrop-local-mask {
  background: linear-gradient(rgba(3, 10, 7, 0.38), rgba(3, 10, 7, 0.52));
}
.tier-low .backdrop-local-mask::before,
.tier-low .backdrop-local-mask::after { backdrop-filter: none; }

@keyframes wallpaper-drift {
  from { transform: translate3d(-0.35%, -0.2%, 0) scale(1.012); }
  to { transform: translate3d(0.35%, 0.2%, 0) scale(1.022); }
}

@media (prefers-reduced-motion: reduce) {
  .backdrop-layer { animation: none !important; transform: none !important; }
  .bg-fade-enter-active { transition-duration: 0.01ms; }
}
</style>

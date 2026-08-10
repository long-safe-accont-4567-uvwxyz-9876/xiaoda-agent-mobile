<script setup lang="ts">
import { ref } from 'vue'
import { useAgentsStore } from '../../stores/agents'
import { useChatStore } from '../../stores/chat'
import CapabilityDrawer from './CapabilityDrawer.vue'
import MobileBottomNav from './MobileBottomNav.vue'
import QuickStatusSheet from './QuickStatusSheet.vue'
import SideBar from './SideBar.vue'
import TopBar from './TopBar.vue'
import SumeruIcon from '../fx/SumeruIcon.vue'

defineProps<{ mobile: boolean }>()

const sidebarExpanded = ref(false)
const drawerOpen = ref(false)
const statusOpen = ref(false)
const agents = useAgentsStore()
const chat = useChatStore()
</script>

<template>
  <div class="responsive-shell" :class="{ mobile }">
    <template v-if="mobile">
      <header class="mobile-topbar">
        <button aria-label="打开全部能力" @click="drawerOpen = true"><SumeruIcon name="flow" :size="22" /></button>
        <button class="agent-status" aria-label="打开快捷状态" @click="statusOpen = true">
          <strong>{{ agents.agents.find(agent => agent.name === chat.currentAgent)?.display_name || chat.currentAgent }}</strong>
          <span>{{ chat.isProcessing ? '处理中' : '待命' }}</span>
        </button>
        <button :aria-label="`查看连接状态：${chat.wsConnected ? '已连接' : chat.wsReconnecting ? '重连中' : '离线'}`" @click="statusOpen = true"><span class="connection-indicator" :data-state="chat.wsConnected ? 'connected' : chat.wsReconnecting ? 'reconnecting' : 'offline'">{{ chat.wsConnected ? '✓' : chat.wsReconnecting ? '↻' : '!' }}</span></button>
      </header>
    </template>
    <template v-else>
      <SideBar :expanded="sidebarExpanded" @update:expanded="sidebarExpanded = $event" />
      <div class="desktop-main"><TopBar /></div>
    </template>
    <main class="shell-content"><slot /></main>
    <template v-if="mobile">
      <MobileBottomNav />
      <CapabilityDrawer :open="drawerOpen" @update:open="drawerOpen = $event" />
      <QuickStatusSheet :open="statusOpen" @update:open="statusOpen = $event" />
    </template>
  </div>
</template>

<style scoped>
.responsive-shell { display: flex; width: 100%; height: 100%; }
.desktop-main { position: relative; z-index: 1; display: flex; flex: 1; min-width: 0; flex-direction: column; overflow: hidden; }
.shell-content { position: absolute; z-index: 2; inset: var(--topbar-height, 64px) 0 0 var(--sidebar-width); overflow: auto; padding: 16px; contain: layout paint; transition: left .3s cubic-bezier(.4, 0, .2, 1); }
.responsive-shell:has(.sidebar.expanded) .shell-content { left: var(--sidebar-expanded); }
.responsive-shell.mobile { flex-direction: column; }
.mobile .shell-content { position: relative; inset: auto; flex: 1; min-height: 0; padding: 8px; }
.mobile-topbar { z-index: 5; display: grid; grid-template-columns: 48px 1fr 48px; align-items: center; padding: env(safe-area-inset-top) max(8px, env(safe-area-inset-right)) 0 max(8px, env(safe-area-inset-left)); min-height: calc(56px + env(safe-area-inset-top)); background: rgba(10,27,21,.72); border-bottom: 1px solid var(--glass-border); backdrop-filter: blur(18px); }
.mobile-topbar button { display: grid; place-items: center; min-width: 48px; min-height: 48px; padding: 0; color: var(--moon); background: transparent; border: 0; border-radius: 14px; }
.agent-status strong, .agent-status span { display: block; max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-status span { color: var(--moon-dim); font-size: 10px; }
.connection-indicator { display: grid; place-items: center; width: 22px; height: 22px; border: 2px solid currentColor; border-radius: 50%; color: var(--alert); font-size: 12px; font-weight: 800; }
.connection-indicator[data-state="connected"] { color: var(--dendro); }
.connection-indicator[data-state="reconnecting"] { color: var(--wisdom); }
</style>

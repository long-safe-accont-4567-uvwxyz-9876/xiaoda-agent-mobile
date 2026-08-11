<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useAgentsStore } from '../../stores/agents'
import { useChatStore } from '../../stores/chat'
import { trapFocus } from '../../utils/focusTrap'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
const dialog = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null
const agents = useAgentsStore()
const chat = useChatStore()
const currentAgent = computed(() => agents.agents.find(agent => agent.name === chat.currentAgent))
const connectionLabel = computed(() => chat.wsConnected ? '已连接' : chat.wsReconnecting ? '重连中' : '离线')
const notificationCount = computed(() => chat.notifications.filter(notification => !notification.read).length)
const modelConfigured = computed(() => Boolean(currentAgent.value?.provider && currentAgent.value?.model))
const degraded = computed(() => Boolean(currentAgent.value?.degraded))
const connectionState = computed(() => chat.wsConnected ? 'connected' : chat.wsReconnecting ? 'reconnecting' : 'offline')

function close() {
  emit('update:open', false)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
  else if (dialog.value) trapFocus(dialog.value, event)
}

watch(() => props.open, async (open) => {
  if (open) {
    opener = document.activeElement as HTMLElement | null
    await nextTick()
    dialog.value?.focus()
  } else if (opener) {
    opener.focus()
    opener = null
  }
}, { immediate: true })
</script>

<template>
  <div v-if="open" class="status-layer">
    <button class="status-scrim" aria-label="关闭快捷状态" @click="close" />
    <section ref="dialog" class="status-sheet" role="dialog" aria-modal="true" aria-label="快捷状态" tabindex="-1" @keydown="handleKeydown">
      <div class="sheet-handle" />
      <div class="status-heading"><div><span>实时状态</span><h2>{{ currentAgent?.display_name || chat.currentAgent }}</h2></div><strong data-connection-status :data-state="connectionState" :aria-label="`连接状态：${connectionLabel}`">{{ connectionLabel }}</strong></div>
      <dl>
        <div><dt>当前服务商</dt><dd>{{ currentAgent?.provider || '未配置' }}</dd></div>
        <div><dt>当前模型</dt><dd>{{ modelConfigured ? currentAgent?.model : '模型未配置' }}</dd></div>
        <div><dt>处理状态</dt><dd>{{ chat.isProcessing ? (chat.statusText || '处理中') : '待命' }}</dd></div>
        <div><dt>运行模式</dt><dd>{{ degraded ? '降级运行' : '正常' }}</dd></div>
        <div><dt>通知</dt><dd>{{ notificationCount }} 条未读 <button data-mark-notifications-read type="button" :disabled="notificationCount === 0" @click="chat.markNotificationsRead()">全部已读</button></dd></div>
      </dl>
      <router-link to="/settings/system" class="quick-settings" @click="close">打开快捷设置</router-link>
    </section>
  </div>
</template>

<style scoped>
.status-layer { position: fixed; z-index: 55; inset: 0; }
.status-scrim { position: absolute; inset: 0; width: 100%; border: 0; background: rgba(2,12,9,.62); }
.status-sheet { position: absolute; inset: auto 0 0; padding: 10px 20px calc(22px + env(safe-area-inset-bottom)); color: var(--moon); background: linear-gradient(155deg, rgba(24,52,39,.98), rgba(8,25,20,.98)); border-top: 1px solid rgba(184,255,133,.22); border-radius: 24px 24px 0 0; }
.sheet-handle { width: 42px; height: 4px; margin: 0 auto 18px; border-radius: 4px; background: rgba(255,255,255,.25); }
.status-heading { display: flex; align-items: center; justify-content: space-between; }
.status-heading span, dt { color: var(--moon-dim); font-size: 12px; }
.status-heading h2 { margin: 4px 0 14px; }
.status-heading strong::before { content: '● '; }.status-heading strong[data-state="connected"] { color: var(--dendro); }.status-heading strong[data-state="reconnecting"]::before { content: '↻ '; }
dl { display: grid; gap: 8px; } dl div { display: flex; justify-content: space-between; min-height: 42px; align-items: center; border-bottom: 1px solid var(--glass-border); } dd { margin: 0; } dd button { margin-left: 8px; color: var(--dendro-bright, #b8ff85); background: transparent; border: 0; } dd button:disabled { color: var(--moon-dim); }
.quick-settings { display: grid; place-items: center; min-height: 48px; margin-top: 18px; color: #102016; background: linear-gradient(135deg, #b8ff85, #4fd6a5); border-radius: 15px; font-weight: 700; text-decoration: none; }
</style>

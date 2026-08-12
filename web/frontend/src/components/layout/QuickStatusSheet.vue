<script setup lang="ts">
import { computed } from 'vue'
import SumeruIcon from '../fx/SumeruIcon.vue'
import { useChatStore } from '../../stores/chat'
import { useAgentsStore } from '../../stores/agents'
import { useUiStore } from '../../stores/ui'
import { t } from '../../i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const chat = useChatStore()
const agentsStore = useAgentsStore()
const ui = useUiStore()

// 当前 Agent 与其 Provider/Model（真实来源）
const currentAgent = computed(() =>
  agentsStore.agents.find((a) => a.name === chat.currentAgent),
)

const wsState = computed(() => {
  if (chat.wsConnected) return { key: 'connected', cls: 'green' }
  if (chat.wsReconnecting) return { key: 'reconnecting', cls: 'yellow' }
  return { key: 'offline', cls: 'red' }
})

const modelConfigured = computed(() =>
  !!currentAgent.value?.provider && !!currentAgent.value?.model,
)

function close() {
  emit('update:open', false)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="quick-status" @keydown.esc="close">
        <div class="sheet-backdrop" @click="close"></div>
        <section class="sheet-panel" role="dialog" aria-modal="true" :aria-label="t('nav.statusTitle')">
          <header class="sheet-head">
            <span class="sheet-title">{{ t('nav.statusTitle') }}</span>
            <button class="sheet-close" :aria-label="t('close')" @click="close">
              <SumeruIcon name="close" :size="18" />
            </button>
          </header>

          <div class="sheet-body">
            <!-- 连接状态 -->
            <div class="status-row">
              <span class="status-label">{{ t('nav.connection') }}</span>
              <span class="status-value">
                <span class="status-dot" :class="wsState.cls"></span>
                {{ t(`nav.status.${wsState.key}`) }}
              </span>
            </div>

            <!-- 当前 Agent -->
            <div class="status-row">
              <span class="status-label">{{ t('nav.currentAgent') }}</span>
              <span class="status-value">{{ currentAgent?.display_name || chat.currentAgent }}</span>
            </div>

            <!-- 当前 Provider / 模型 -->
            <div class="status-row">
              <span class="status-label">{{ t('nav.currentProvider') }}</span>
              <span class="status-value" :class="{ 'status-warn': !modelConfigured }">
                <template v-if="modelConfigured">
                  {{ currentAgent!.provider }} · {{ currentAgent!.model }}
                </template>
                <template v-else>{{ t('nav.modelNotConfigured') }}</template>
              </span>
            </div>

            <!-- 快捷设置 -->
            <h4 class="sheet-sub">{{ t('nav.quickSettings') }}</h4>

            <label class="setting-row">
              <span class="setting-label">{{ t('nav.soundFx') }}</span>
              <input type="checkbox" class="toggle" :checked="ui.soundFx" @change="ui.setSoundFx(($event.target as HTMLInputElement).checked)" />
            </label>

            <label class="setting-row">
              <span class="setting-label">{{ t('nav.autoSpeak') }}</span>
              <input type="checkbox" class="toggle" :checked="ui.autoSpeak" @change="ui.setAutoSpeak(($event.target as HTMLInputElement).checked)" />
            </label>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.quick-status {
  position: fixed;
  inset: 0;
  z-index: var(--z-mobile-sheet, 60);
}

.sheet-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(5, 12, 8, 0.5);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.sheet-panel {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 20px 20px 0 0;
  background: rgba(15, 31, 23, 0.95);
  -webkit-backdrop-filter: blur(24px) saturate(1.2);
  backdrop-filter: blur(24px) saturate(1.2);
  border-top: 1px solid var(--glass-border);
  box-shadow: 0 -8px 40px rgba(0, 0, 0, 0.4);
  padding: 14px 16px calc(env(safe-area-inset-bottom) + 16px);
}

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--glass-border);
}
.sheet-title {
  font-size: 15px;
  font-weight: 700;
  font-family: 'Noto Serif SC', serif;
  background: var(--gradient-dendro);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
}
.sheet-close {
  min-width: var(--bottom-nav-touch, 48px);
  min-height: var(--bottom-nav-touch, 48px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--moon-dim);
  cursor: pointer;
  border-radius: 12px;
  transition: color 0.2s, background 0.2s, transform 0.2s var(--ease-spring);
}
.sheet-close:focus-visible { outline: 2px solid var(--dendro); }
.sheet-close:active { transform: scale(0.9); }
.sheet-close:hover { color: var(--moon); background: rgba(143, 229, 96, 0.1); }

.sheet-body { padding-top: 6px; }

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 4px;
  border-bottom: 1px solid rgba(143, 229, 96, 0.08);
  font-size: 14px;
}
.status-label { color: var(--moon-dim); }
.status-value { color: var(--moon); display: flex; align-items: center; gap: 8px; }
.status-warn { color: var(--wisdom, #f0c05a); }

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.status-dot.green { background: var(--dendro); box-shadow: 0 0 8px var(--dendro); }
.status-dot.yellow { background: var(--wisdom, #f0c05a); box-shadow: 0 0 8px var(--wisdom, #f0c05a); animation: breathe 1.2s ease-in-out infinite; }
.status-dot.red { background: var(--alert); box-shadow: 0 0 8px var(--alert); }

.sheet-sub {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: rgba(232, 213, 163, 0.5);
  font-family: 'Noto Serif SC', serif;
  margin: 14px 4px 4px;
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--bottom-nav-touch, 48px);
  padding: 0 4px;
  font-size: 14px;
  color: var(--moon);
}
.setting-label { color: var(--moon-dim); }

.toggle {
  appearance: none;
  width: 46px;
  height: 26px;
  border-radius: 13px;
  background: rgba(143, 229, 96, 0.18);
  border: 1px solid var(--glass-border);
  position: relative;
  cursor: pointer;
  transition: background 0.25s, border-color 0.25s;
}
.toggle::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--moon-dim);
  transition: transform 0.25s var(--ease-spring), background 0.25s;
}
.toggle:checked {
  background: rgba(143, 229, 96, 0.4);
  border-color: var(--dendro);
}
.toggle:checked::after {
  transform: translateX(20px);
  background: var(--dendro-bright);
}
.toggle:focus-visible { outline: 2px solid var(--dendro); outline-offset: 2px; }

@keyframes breathe {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.sheet-enter-active, .sheet-leave-active { transition: opacity 0.28s var(--ease-smooth); }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform 0.32s var(--ease-spring); }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }
</style>
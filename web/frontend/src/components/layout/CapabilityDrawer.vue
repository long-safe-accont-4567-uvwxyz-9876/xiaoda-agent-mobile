<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SumeruIcon from '../fx/SumeruIcon.vue'
import { capabilityGroups, capabilitiesByGroup, type Capability } from '../../navigation/capabilities'
import { t } from '../../i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const route = useRoute()
const router = useRouter()
const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)

const allGroups = computed(() =>
  capabilityGroups
    .map((g) => ({ ...g, items: capabilitiesByGroup(g.id) }))
    .filter((g) => g.items.length > 0),
)

const filteredGroups = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return allGroups.value
  return allGroups.value
    .map((g) => ({ ...g, items: g.items.filter((c) => t(c.labelKey).toLowerCase().includes(q)) }))
    .filter((g) => g.items.length > 0)
})

function isActive(item: Capability): boolean {
  return item.routeName === route.name || item.route === route.path
}

function go(item: Capability) {
  if (route.path !== item.route) router.push(item.route)
  close()
}

function close() {
  query.value = ''
  emit('update:open', false)
}

// 打开时聚焦搜索框
watch(() => props.open, (open) => {
  if (open) {
    query.value = ''
    requestAnimationFrame(() => searchInput.value?.focus())
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="capability-drawer" @keydown.esc="close">
        <div class="drawer-backdrop" @click="close"></div>
        <aside class="drawer-panel" role="dialog" aria-modal="true" :aria-label="t('nav.drawerTitle')">
          <header class="drawer-head">
            <span class="drawer-title">{{ t('nav.drawerTitle') }}</span>
            <button class="drawer-close" :aria-label="t('close')" @click="close">
              <SumeruIcon name="close" :size="18" />
            </button>
          </header>

          <div class="drawer-search">
            <SumeruIcon name="search" :size="16" class="search-icon" />
            <input
              ref="searchInput"
              v-model="query"
              type="search"
              class="search-input"
              :placeholder="t('nav.searchPlaceholder')"
            />
          </div>

          <div class="drawer-body">
            <section v-for="group in filteredGroups" :key="group.id" class="group">
              <h3 class="group-title">{{ t(group.labelKey) }}</h3>
              <div class="group-items">
                <router-link
                  v-for="item in group.items"
                  :key="item.id"
                  :to="item.route"
                  class="group-item"
                  :class="{ active: isActive(item) }"
                  @click="go(item)"
                >
                  <span class="item-icon"><SumeruIcon :name="item.icon" :size="20" /></span>
                  <span class="item-label">{{ t(item.labelKey) }}</span>
                  <span v-if="isActive(item)" class="item-check" aria-hidden="true">🌿</span>
                </router-link>
              </div>
            </section>

            <p v-if="!filteredGroups.length" class="drawer-empty">{{ t('nav.noMatches') }}</p>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.capability-drawer {
  position: fixed;
  inset: 0;
  z-index: var(--z-mobile-drawer, 50);
}

.drawer-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(5, 12, 8, 0.5);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}

.drawer-panel {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: min(82vw, 340px);
  display: flex;
  flex-direction: column;
  background: rgba(15, 31, 23, 0.92);
  -webkit-backdrop-filter: blur(20px) saturate(1.2);
  backdrop-filter: blur(20px) saturate(1.2);
  border-right: 1px solid var(--glass-border);
  box-shadow: 12px 0 40px rgba(0, 0, 0, 0.35);
  padding: calc(env(safe-area-inset-top) + 10px) 12px env(safe-area-inset-bottom);
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 4px 12px;
}

.drawer-title {
  font-size: 16px;
  font-weight: 700;
  font-family: 'Noto Serif SC', serif;
  background: var(--gradient-dendro);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
}

.drawer-close {
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
.drawer-close:focus-visible { outline: 2px solid var(--dendro); }
.drawer-close:active { transform: scale(0.9); }
.drawer-close:hover { color: var(--moon); background: rgba(143, 229, 96, 0.1); }

.drawer-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 44px;
  background: rgba(20, 40, 28, 0.6);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  margin-bottom: 12px;
}
.search-icon { color: var(--moon-dim); flex-shrink: 0; }
.search-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--moon);
  font-size: 14px;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
}

.group { margin-bottom: 8px; }
.group-title {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: rgba(232, 213, 163, 0.5);
  font-family: 'Noto Serif SC', serif;
  padding: 10px 8px 4px;
  margin: 0;
}
.group-items { display: flex; flex-direction: column; gap: 2px; }

.group-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: var(--bottom-nav-touch, 48px);
  padding: 0 12px;
  border-radius: 12px;
  color: var(--moon-dim);
  text-decoration: none;
  transition: background 0.2s, color 0.2s, transform 0.15s var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}
.group-item:focus-visible { outline: 2px solid var(--dendro); outline-offset: -2px; }
.group-item:active { transform: scale(0.97); }
.group-item:hover { background: rgba(143, 229, 96, 0.08); color: var(--moon); }
.group-item.active {
  background: linear-gradient(90deg, rgba(143, 229, 96, 0.2), rgba(143, 229, 96, 0.05));
  color: var(--dendro-bright);
}
.group-item .item-icon { display: flex; flex-shrink: 0; }
.group-item .item-label { font-size: 14px; flex: 1; }
.group-item .item-check { font-size: 12px; }

.drawer-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--moon-dim);
  font-size: 13px;
}

.drawer-enter-active, .drawer-leave-active { transition: opacity 0.28s var(--ease-smooth); }
.drawer-enter-active .drawer-panel, .drawer-leave-active .drawer-panel { transition: transform 0.32s var(--ease-spring); }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer-panel, .drawer-leave-to .drawer-panel { transform: translateX(-100%); }
</style>
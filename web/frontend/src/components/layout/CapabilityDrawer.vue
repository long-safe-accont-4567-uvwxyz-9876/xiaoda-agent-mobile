<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { capabilityGroups } from '../../navigation/capabilities'
import { t } from '../../i18n'
import { trapFocus } from '../../utils/focusTrap'
import SumeruIcon from '../fx/SumeruIcon.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
const query = ref('')
const dialog = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

const filteredGroups = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return capabilityGroups
  return capabilityGroups.map(group => ({
    ...group,
    items: group.items.filter(item =>
      [t(item.labelKey), ...item.searchTerms].some(term => term.toLocaleLowerCase().includes(keyword))),
  })).filter(group => group.items.length)
})

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
  <div v-if="props.open" class="drawer-layer">
    <button class="drawer-scrim" aria-label="关闭全部能力" @click="close" />
    <aside ref="dialog" class="capability-drawer" role="dialog" aria-modal="true" aria-label="全部能力" tabindex="-1" @keydown="handleKeydown">
      <div class="drawer-head">
        <div><span class="eyebrow">XIAODA</span><h2>全部能力</h2></div>
        <button class="close-button" aria-label="关闭" @click="close">×</button>
      </div>
      <input v-model="query" type="search" class="capability-search" placeholder="搜索能力" aria-label="搜索能力" />
      <div class="group-list">
        <section v-for="group in filteredGroups" :key="group.id" data-capability-group class="capability-group">
          <h3>{{ group.label }}</h3>
          <router-link v-for="item in group.items" :key="item.routeName" :to="item.path"
            data-capability-link class="capability-link" @click="close">
            <SumeruIcon :name="item.icon" :size="20" /><span>{{ t(item.labelKey) }}</span>
          </router-link>
        </section>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.drawer-layer { position: fixed; z-index: 50; inset: 0; }
.drawer-scrim { position: absolute; inset: 0; width: 100%; border: 0; background: rgba(2, 12, 9, .62); }
.capability-drawer { position: absolute; inset: 0 auto 0 0; width: min(88vw, 360px); overflow-y: auto; padding: max(18px, env(safe-area-inset-top)) 18px calc(20px + env(safe-area-inset-bottom)); color: var(--moon); background: linear-gradient(160deg, rgba(21,48,35,.98), rgba(8,25,20,.96)); border-right: 1px solid rgba(184,255,133,.2); box-shadow: 24px 0 70px rgba(0,0,0,.4); }
.drawer-head { display: flex; align-items: center; justify-content: space-between; }
.drawer-head h2 { margin: 3px 0 14px; font-family: 'Noto Serif SC', serif; }
.eyebrow { color: var(--dendro); font-size: 10px; letter-spacing: .2em; }
.close-button { width: 48px; height: 48px; border: 0; border-radius: 50%; color: var(--moon); background: rgba(255,255,255,.06); font-size: 26px; }
.capability-search { box-sizing: border-box; width: 100%; height: 48px; padding: 0 16px; color: var(--moon); background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); border-radius: 15px; outline: none; }
.capability-search:focus { border-color: var(--dendro); box-shadow: 0 0 0 3px rgba(127,214,80,.12); }
.group-list { display: grid; gap: 18px; margin-top: 22px; }
.capability-group h3 { margin: 0 0 8px; color: var(--wisdom); font-size: 12px; letter-spacing: .08em; }
.capability-link { display: flex; align-items: center; gap: 12px; min-height: 48px; padding: 0 13px; color: var(--moon-dim); text-decoration: none; border-radius: 14px; }
.capability-link.router-link-exact-active { color: var(--dendro-bright, #b8ff85); background: linear-gradient(90deg, rgba(127,214,80,.2), rgba(79,214,165,.07)); box-shadow: inset 3px 0 var(--dendro); }
</style>

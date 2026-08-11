<script setup lang="ts">
import { computed } from 'vue'
import { NDynamicTags, NTag } from 'naive-ui'
const props = defineProps<{ modelValue: any[]; discovered?: any }>()
const emit = defineEmits<{ 'update:modelValue': [value: any[]] }>()
const ids = computed({
  get: () => (props.modelValue || []).map(item => typeof item === 'string' ? item : item.id),
  set: value => emit('update:modelValue', value),
})
</script>
<template>
  <div class="model-picker">
    <label>Manual model IDs</label>
    <n-dynamic-tags v-model:value="ids" />
    <div v-if="discovered" class="discovery-state">
      <n-tag size="small" :type="discovered.status === 'error' ? 'error' : 'success'">{{ discovered.status }}</n-tag>
      <span v-for="warning in discovered.warnings || []" :key="warning">{{ warning }}</span>
    </div>
    <div class="model-groups">
      <span v-for="model in discovered?.models || []" :key="model.id" class="model-chip">{{ model.id }} ? {{ model.category }} ? {{ model.capability_source }}</span>
    </div>
  </div>
</template>
<style scoped>
.model-picker{display:grid;gap:8px}.model-picker label{font-size:12px;color:var(--moon-dim)}.discovery-state,.model-groups{display:flex;gap:6px;flex-wrap:wrap}.model-chip{font-size:11px;padding:4px 7px;border-radius:7px;background:rgba(127,214,80,.08);color:var(--moon-dim)}
</style>

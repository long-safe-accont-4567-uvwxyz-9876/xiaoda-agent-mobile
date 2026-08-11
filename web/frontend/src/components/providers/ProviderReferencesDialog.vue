<script setup lang="ts">
import { NButton, NModal, NTag } from 'naive-ui'
defineProps<{ show: boolean; data?: any }>()
const emit = defineEmits<{ close: [] }>()
</script>
<template><n-modal :show="show" preset="card" title="Provider references" class="provider-references" @mask-click="emit('close')">
  <p v-if="!data?.references?.length">No references.</p>
  <div v-for="item in data?.references || []" :key="`${item.type}:${item.id}`" class="reference-row"><n-tag size="small">{{ item.type }}</n-tag><strong>{{ item.id }}</strong><span>{{ item.model || item.label }}</span></div>
  <p v-if="data?.references?.length" class="migration-help">Migrate these routes, chat model, and Agents to one of: {{ data.replacement_candidates?.join(', ') || 'no enabled replacement' }}.</p>
  <code v-for="operation in data?.migration_operations || []" :key="operation.action" class="migration-operation">{{ operation.action }}</code>
  <template #footer><n-button @click="emit('close')">Close</n-button></template>
</n-modal></template>
<style>.provider-references{width:min(560px,94vw)}.reference-row{display:grid;grid-template-columns:90px 1fr 1fr;gap:8px;padding:8px;border-bottom:1px solid var(--glass-border)}.migration-help{margin-top:12px;color:var(--wisdom)}.migration-operation{display:block;padding:6px;margin-top:4px;overflow-wrap:anywhere;background:rgba(127,214,80,.08)}@media(max-width:767px){.provider-references{width:calc(100vw - 16px)!important}.reference-row{grid-template-columns:80px 1fr}}</style>

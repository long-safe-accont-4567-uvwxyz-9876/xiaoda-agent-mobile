<script setup lang="ts">
defineProps<{ result?: any }>()
</script>
<template>
  <div v-if="result" class="provider-diagnostics" role="status">
    <div class="diagnostic-summary" :class="{ ok: result.ok }">{{ result.ok ? 'Connection verified' : 'Connection failed' }} ? {{ result.latency_ms || 0 }}ms</div>
    <div v-for="stage in result.stages || []" :key="stage.stage" class="diagnostic-stage">
      <strong>{{ stage.stage }}</strong><span>{{ stage.status }}</span><code v-if="stage.code">{{ stage.code }}</code><small>{{ stage.latency_ms || 0 }}ms</small>
    </div>
  </div>
</template>
<style scoped>
.provider-diagnostics{display:grid;gap:6px;padding:10px;border:1px solid var(--glass-border);border-radius:10px;background:rgba(3,10,7,.36)}
.diagnostic-summary{color:var(--alert)}.diagnostic-summary.ok{color:var(--dendro)}
.diagnostic-stage{display:grid;grid-template-columns:72px 60px 1fr auto;gap:8px;align-items:center;font-size:12px}.diagnostic-stage code{color:var(--wisdom)}
</style>

<script setup lang="ts">
// 桌面壳：左侧导航列。仅承载布局，不持有任何业务状态。
import SideBar from './SideBar.vue'

defineProps<{ expanded: boolean }>()
const emit = defineEmits<{ 'update:expanded': [value: boolean] }>()
</script>

<template>
  <SideBar :expanded="expanded" @update:expanded="emit('update:expanded', $event)" />
</template>
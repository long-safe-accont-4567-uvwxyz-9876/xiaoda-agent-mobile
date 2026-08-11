<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NRadio, NRadioGroup, NSwitch, useMessage } from 'naive-ui'
import { useProvidersStore } from '../../stores/providers'
import ProviderDiagnostics from './ProviderDiagnostics.vue'
import ProviderModelPicker from './ProviderModelPicker.vue'
const props = defineProps<{ show: boolean; provider?: any; create: boolean; discovered?: any }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const store = useProvidersStore()
const message = useMessage()
const draft = ref<any>({})
const diagnostics = ref<any>(null)
const testing = ref(false)
const saving = ref(false)
watch(() => [props.show, props.provider, props.create], () => {
  draft.value = props.create
    ? { id:'', label:'', format:'openai', base_url:'', default_model:'', api_key:'', enabled:true, manual_models:[] }
    : { ...props.provider, api_key:'', manual_models:[...(props.provider?.manual_models || [])] }
  diagnostics.value = null
}, { immediate: true, deep: true })
const normalizedUrl = computed(() => diagnostics.value?.normalized?.base_url || '')
async function testBeforeSave(){ testing.value=true; try{ const result=await store.diagnose(draft.value); diagnostics.value=result.diagnostics }catch(e:any){ diagnostics.value={ok:false,latency_ms:0,stages:[{stage:'validate',status:'error',code:e.message}]} }finally{testing.value=false} }
async function save(){ saving.value=true; try{ if(props.create) await store.create(draft.value); else await store.update(draft.value.id,draft.value); emit('saved') }catch(e:any){message.error(e.message)}finally{saving.value=false} }
</script>
<template>
  <n-modal :show="show" preset="card" class="provider-editor" :title="create ? 'New Provider' : `Edit - ${draft.id}`" @mask-click="emit('close')">
    <n-form label-placement="top">
      <n-form-item v-if="create" label="ID"><n-input v-model:value="draft.id" /></n-form-item>
      <n-form-item label="Name"><n-input v-model:value="draft.label" /></n-form-item>
      <n-form-item label="Format"><n-radio-group v-model:value="draft.format"><n-radio value="openai">OpenAI compatible</n-radio><n-radio value="anthropic">Anthropic compatible</n-radio></n-radio-group></n-form-item>
      <n-form-item label="Base URL"><n-input v-model:value="draft.base_url" placeholder="https://api.example.com/v1" /><small v-if="normalizedUrl">Normalized: {{ normalizedUrl }}</small></n-form-item>
      <n-form-item label="Default model"><n-input v-model:value="draft.default_model" /></n-form-item>
      <n-form-item label="API Key"><n-input v-model:value="draft.api_key" type="password" show-password-on="click" :placeholder="create ? 'Required for creation' : 'Leave blank to keep the existing key'" /></n-form-item>
      <n-form-item label="Enabled"><n-switch v-model:value="draft.enabled" /></n-form-item>
      <n-form-item><ProviderModelPicker v-model="draft.manual_models" :discovered="discovered" /></n-form-item>
    </n-form>
    <ProviderDiagnostics :result="diagnostics" />
    <template #footer><div class="editor-actions"><n-button @click="emit('close')">Cancel</n-button><n-button :loading="testing" @click="testBeforeSave">Test before save</n-button><n-button type="primary" :loading="saving" @click="save">Save</n-button></div></template>
  </n-modal>
</template>
<style>
.provider-editor{width:min(680px,96vw);max-height:92vh;overflow:auto}.editor-actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}
@media(max-width:767px){.provider-editor{width:100vw!important;max-width:none!important;height:100dvh;max-height:100dvh!important;margin:0!important;border-radius:0!important}.provider-editor .n-card__content{overflow:auto;padding-bottom:calc(92px + env(safe-area-inset-bottom))}.editor-actions{position:sticky;bottom:0;background:var(--forest-deep);padding-bottom:env(safe-area-inset-bottom)}.editor-actions>*{flex:1;min-height:48px}}
</style>

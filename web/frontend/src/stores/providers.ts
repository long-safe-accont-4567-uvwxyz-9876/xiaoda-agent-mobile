import { defineStore } from 'pinia'
import { ref } from 'vue'
import { del, get, post, put } from '../api'

export interface ProviderRecord {
  id: string
  label: string
  format: 'openai' | 'anthropic'
  base_url: string
  builtin?: boolean
  enabled: boolean
  default_model?: string
  manual_models?: Array<string | { id: string; category?: string }>
  key_masked?: string
  has_key?: boolean
  order?: number
}

export const useProvidersStore = defineStore('providers', () => {
  const providers = ref<ProviderRecord[]>([])
  const discovery = ref<any[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const [items, discovered] = await Promise.all([
        get<ProviderRecord[]>('/models/providers'),
        get<any[]>('/models/discover').catch(() => []),
      ])
      providers.value = items
      discovery.value = discovered
    } finally { loading.value = false }
  }

  const validate = (payload: any, providerId?: string) => providerId
    ? put<any>(`/models/providers/${providerId}`, { ...payload, validate_only: true })
    : post<any>('/models/providers', { ...payload, validate_only: true })
  const diagnose = (payload: any) => post<any>('/models/providers/diagnose', payload)
  const create = (payload: any) => post('/models/providers', payload)
  const update = (providerId: string, payload: any) => put(`/models/providers/${providerId}`, payload)
  const test = (providerId: string, payload: any = {}) => post<any>(`/models/providers/${providerId}/test`, payload)
  const discover = (providerId: string) => post<any>(`/models/providers/${providerId}/discover`)
  const references = (providerId: string) => get<any>(`/models/providers/${providerId}/references`)
  const remove = (providerId: string) => del(`/models/providers/${providerId}`, true)
  const reorder = (order: string[]) => post('/models/providers/reorder', { order })

  return { providers, discovery, loading, load, validate, diagnose, create, update, test, discover, references, remove, reorder }
})

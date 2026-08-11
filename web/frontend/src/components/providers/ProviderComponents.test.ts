import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(process.cwd(), 'src/components/providers')
const read = (name: string) => readFileSync(resolve(root, name), 'utf8')

describe('Provider mobile frontend contract', () => {
  it('splits list, editor, diagnostics, model picker, and references', () => {
    for (const name of ['ProviderList.vue','ProviderEditor.vue','ProviderDiagnostics.vue','ProviderModelPicker.vue','ProviderReferencesDialog.vue']) {
      expect(read(name).length).toBeGreaterThan(100)
    }
  })
  it('never backfills an existing API key and supports test-before-save', () => {
    const editor = read('ProviderEditor.vue')
    expect(editor).toContain("api_key:''")
    expect(editor).toContain('Leave blank to keep the existing key')
    expect(editor).toContain('Test before save')
    expect(editor).not.toContain('key_masked')
  })
  it('uses a full-height mobile editor and exposes manual models and references', () => {
    expect(read('ProviderEditor.vue')).toContain('height:100dvh')
    expect(read('ProviderModelPicker.vue')).toContain('Manual model IDs')
    expect(read('ProviderReferencesDialog.vue')).toContain('replacement_candidates')
  })
})

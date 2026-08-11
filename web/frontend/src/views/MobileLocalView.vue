<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { getLocalNativeBridge } from '../platform/localNativeBridge'

type Provider = {
  id: string
  label: string
  format: 'openai' | 'anthropic'
  baseUrl: string
  defaultModel: string
  hasApiKey: boolean
}

type Agent = {
  name: string
  providerId: string
  model: string
  systemPrompt: string
}

type SessionSummary = {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messageCount: number
}

type Attachment = {
  id: string
  name: string
  mimeType: string
  sizeBytes: number
}

type Message = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  attachments?: string[]
  streaming?: boolean
}

type Capability = { id: string; label: string; state: string }

const bridge = getLocalNativeBridge()
const loading = ref(true)
const error = ref('')
const providers = ref<Provider[]>([])
const agent = ref<Agent>({ name: 'Xiaoda', providerId: '', model: '', systemPrompt: 'You are Xiaoda, a reliable, clear, and privacy-conscious mobile AI assistant.' })
const sessions = ref<SessionSummary[]>([])
const messages = ref<Message[]>([])
const capabilities = ref<Capability[]>([])
const currentSessionId = ref('')
const prompt = ref('')
const attachments = ref<Attachment[]>([])
const processing = ref(false)
const activeRequestId = ref('')
const settingsOpen = ref(false)
const historyOpen = ref(false)
const showApiKey = ref(false)
const modelOptions = ref<string[]>([])
const modelLoading = ref(false)
const saving = ref(false)
const messageList = ref<HTMLElement | null>(null)

const providerForm = ref({
  id: 'openai',
  label: 'OpenAI',
  format: 'openai' as 'openai' | 'anthropic',
  baseUrl: 'https://api.openai.com/v1',
  defaultModel: 'gpt-4.1-mini',
  apiKey: '',
})

const configured = computed(() => providers.value.length > 0 && !!agent.value.providerId && !!agent.value.model)
const activeProvider = computed(() => providers.value.find(item => item.id === agent.value.providerId))
const canSend = computed(() => configured.value && prompt.value.trim().length > 0 && !processing.value)

const formatBytes = (bytes: number) => bytes < 1024 * 1024
  ? `${Math.max(1, Math.round(bytes / 1024))} KB`
  : `${(bytes / 1024 / 1024).toFixed(1)} MB`

const formatTime = (timestamp: number) => new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

function friendlyError(value: unknown) {
  const code = value instanceof Error ? value.message : String(value || '')
  const labels: Record<string, string> = {
    api_key_required: 'Enter an API key.',
    invalid_api_key: 'The API key format is invalid.',
    provider_authentication_failed: 'Authentication failed. Check the API key.',
    provider_endpoint_or_model_not_found: 'The endpoint or model was not found.',
    provider_rate_limited: 'The provider is rate limiting requests. Try again later.',
    insecure_base_url: 'Release builds require an HTTPS endpoint.',
    invalid_base_url: 'The endpoint URL is invalid.',
    provider_not_configured: 'Configure a provider and model first.',
    native_bridge_timeout: 'The local Android service timed out. Try again.',
    cancelled: 'Generation stopped.',
    attachment_not_supported_by_provider: 'This provider does not support that attachment type. Use an image or text file, or use Anthropic for PDF input.',
  }
  return labels[code] || 'Operation failed. Check the network and provider settings.'
}

async function scrollToBottom() {
  await nextTick()
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight, behavior: 'smooth' })
}

async function refreshBootstrap() {
  const data = await bridge.localBootstrap()
  providers.value = data.providers || []
  agent.value = data.agent || agent.value
  sessions.value = data.sessions || []
  capabilities.value = data.capabilities || []
  if (!providers.value.length) settingsOpen.value = true
}

async function ensureSession() {
  if (currentSessionId.value) return
  if (sessions.value.length) {
    await openSession(sessions.value[0].id)
    return
  }
  const session = await bridge.createLocalSession()
  currentSessionId.value = session.id
  sessions.value = [session]
}

async function openSession(sessionId: string) {
  const data = await bridge.getLocalMessages(sessionId)
  currentSessionId.value = sessionId
  messages.value = (data.messages || []).map((message: Message) => ({ ...message }))
  historyOpen.value = false
  await scrollToBottom()
}

async function newSession() {
  const session = await bridge.createLocalSession()
  currentSessionId.value = session.id
  sessions.value = [session, ...sessions.value]
  messages.value = []
  historyOpen.value = false
}

async function removeSession(sessionId: string) {
  await bridge.deleteLocalSession(sessionId)
  sessions.value = sessions.value.filter(item => item.id !== sessionId)
  if (currentSessionId.value === sessionId) {
    currentSessionId.value = ''
    messages.value = []
    await ensureSession()
  }
}

function applyProviderPreset(format: 'openai' | 'anthropic') {
  providerForm.value.format = format
  if (format === 'anthropic') {
    providerForm.value.id = 'anthropic'
    providerForm.value.label = 'Anthropic'
    providerForm.value.baseUrl = 'https://api.anthropic.com'
    providerForm.value.defaultModel = 'claude-sonnet-4-5'
  } else {
    providerForm.value.id = 'openai'
    providerForm.value.label = 'OpenAI'
    providerForm.value.baseUrl = 'https://api.openai.com/v1'
    providerForm.value.defaultModel = 'gpt-4.1-mini'
  }
  modelOptions.value = []
}

function editProvider(provider: Provider) {
  providerForm.value = {
    id: provider.id,
    label: provider.label,
    format: provider.format,
    baseUrl: provider.baseUrl,
    defaultModel: provider.defaultModel,
    apiKey: '',
  }
  modelOptions.value = []
}

async function saveProvider() {
  error.value = ''
  saving.value = true
  try {
    const saved = await bridge.saveLocalProvider(providerForm.value)
    const nextAgent = {
      ...agent.value,
      providerId: saved.id,
      model: providerForm.value.defaultModel,
    }
    await bridge.saveLocalAgent(nextAgent)
    providerForm.value.apiKey = ''
    await refreshBootstrap()
    settingsOpen.value = false
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    saving.value = false
  }
}

async function discoverModels() {
  error.value = ''
  modelLoading.value = true
  try {
    await bridge.saveLocalProvider(providerForm.value)
    const data = await bridge.listLocalModels(providerForm.value.id)
    modelOptions.value = data.models || []
    if (modelOptions.value.length && !modelOptions.value.includes(providerForm.value.defaultModel)) {
      providerForm.value.defaultModel = modelOptions.value[0]
    }
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    modelLoading.value = false
  }
}

async function saveAgent() {
  error.value = ''
  saving.value = true
  try {
    await bridge.saveLocalAgent(agent.value)
    await refreshBootstrap()
    settingsOpen.value = false
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    saving.value = false
  }
}

async function pickAttachment() {
  error.value = ''
  try {
    const attachment = await bridge.pickLocalAttachment('*/*', 10 * 1024 * 1024)
    if (attachment?.id) attachments.value.push(attachment)
  } catch (reason) {
    error.value = friendlyError(reason)
  }
}

function removeAttachment(id: string) {
  attachments.value = attachments.value.filter(item => item.id !== id)
}

async function sendMessage() {
  if (!canSend.value) return
  await ensureSession()
  const text = prompt.value.trim()
  const requestId = globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}`
  messages.value.push({ id: `user-${requestId}`, role: 'user', content: text, timestamp: Date.now(), attachments: attachments.value.map(item => item.id) })
  messages.value.push({ id: `assistant-${requestId}`, role: 'assistant', content: '', timestamp: Date.now(), streaming: true })
  prompt.value = ''
  const attachmentIds = attachments.value.map(item => item.id)
  attachments.value = []
  processing.value = true
  activeRequestId.value = requestId
  await scrollToBottom()
  try {
    await bridge.startLocalChat({ sessionId: currentSessionId.value, text, requestId, attachmentIds })
  } catch (reason) {
    const target = messages.value.find(item => item.id === `assistant-${requestId}`)
    if (target) {
      target.streaming = false
      target.content = friendlyError(reason)
    }
    processing.value = false
    activeRequestId.value = ''
  }
}

async function stopGeneration() {
  if (!activeRequestId.value) return
  await bridge.abortLocalChat(activeRequestId.value)
}

const unsubscribers = [
  bridge.on('local.chat.delta', async (data: any) => {
    if (data?.requestId !== activeRequestId.value) return
    const target = messages.value.find(item => item.id === `assistant-${data.requestId}`)
    if (target) target.content = data.accumulated || `${target.content}${data.delta || ''}`
    await scrollToBottom()
  }),
  bridge.on('local.chat.completed', async (data: any) => {
    if (data?.requestId !== activeRequestId.value) return
    const target = messages.value.find(item => item.id === `assistant-${data.requestId}`)
    if (target) {
      target.content = data.content || target.content
      target.streaming = false
    }
    processing.value = false
    activeRequestId.value = ''
    const response = await bridge.listLocalSessions()
    sessions.value = response.sessions || sessions.value
    await scrollToBottom()
  }),
  bridge.on('local.chat.failed', (data: any) => {
    if (data?.requestId !== activeRequestId.value) return
    const target = messages.value.find(item => item.id === `assistant-${data.requestId}`)
    if (target) {
      target.content = friendlyError(data.error)
      target.streaming = false
    }
    processing.value = false
    activeRequestId.value = ''
  }),
]

onMounted(async () => {
  try {
    await refreshBootstrap()
    await ensureSession()
  } catch (reason) {
    error.value = friendlyError(reason)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => unsubscribers.forEach(unsubscribe => unsubscribe()))
</script>

<template>
  <main class="local-app" aria-label="Xiaoda local mobile assistant">
    <header class="topbar">
      <button class="icon-button" type="button" aria-label="Open conversation history" @click="historyOpen = true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
      </button>
      <div class="brand-block">
        <span class="status-dot" :class="{ ready: configured }"></span>
        <div>
          <strong>{{ agent.name || 'Xiaoda' }}</strong>
          <span>{{ configured ? `${activeProvider?.label || ''} / ${agent.model}` : 'Model setup required' }}</span>
        </div>
      </div>
      <button class="icon-button" type="button" aria-label="Open local settings" @click="settingsOpen = true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21h-4v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6V3h4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>
      </button>
    </header>

    <section ref="messageList" class="messages" aria-live="polite">
      <div v-if="loading" class="center-state"><span class="loader"></span><p>Starting the local core...</p></div>
      <div v-else-if="messages.length === 0" class="welcome-card">
        <div class="logo-mark">XD</div>
        <h1>Xiaoda Local</h1>
        <p>Your API key is encrypted by the Android native layer and is never exposed to the WebView. Configure a model to begin.</p>
        <button v-if="!configured" class="primary-button" type="button" @click="settingsOpen = true">Configure provider</button>
        <div class="feature-grid">
          <span>Streaming chat</span><span>Local history</span><span>Images</span><span>PDF files</span>
        </div>
      </div>
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <div class="message-label">{{ message.role === 'user' ? 'You' : message.role === 'assistant' ? agent.name : 'System' }}</div>
        <div class="bubble">
          <p>{{ message.content }}<span v-if="message.streaming" class="stream-cursor" aria-label="Generating"></span></p>
          <time>{{ formatTime(message.timestamp) }}</time>
        </div>
      </article>
    </section>

    <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

    <footer class="composer">
      <div v-if="attachments.length" class="attachment-strip">
        <span v-for="attachment in attachments" :key="attachment.id" class="attachment-chip">
          <span><strong>{{ attachment.name }}</strong><small>{{ formatBytes(attachment.sizeBytes) }}</small></span>
          <button type="button" :aria-label="`Remove ${attachment.name}`" @click="removeAttachment(attachment.id)">&times;</button>
        </span>
      </div>
      <div class="composer-row">
        <button class="attach-button" type="button" aria-label="Add image or document" :disabled="processing" @click="pickAttachment">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m20.5 11.5-8.7 8.7a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7L9 17.4a2 2 0 1 1-2.8-2.8l8.5-8.5"/></svg>
        </button>
        <textarea v-model="prompt" rows="1" aria-label="Message" placeholder="Message Xiaoda..." :disabled="processing" @keydown.enter.exact.prevent="sendMessage"></textarea>
        <button v-if="processing" class="send-button stop" type="button" aria-label="Stop generation" @click="stopGeneration"><span></span></button>
        <button v-else class="send-button" type="button" aria-label="Send message" :disabled="!canSend" @click="sendMessage">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-8-4 16-3-6-7-2Z"/><path d="m12 14 7-10"/></svg>
        </button>
      </div>
      <small>AI responses may be inaccurate. Verify important information.</small>
    </footer>

    <div v-if="historyOpen" class="overlay" @click.self="historyOpen = false">
      <aside class="sheet history-sheet" aria-label="Conversation history">
        <div class="sheet-header"><div><span>On-device records</span><h2>Conversation history</h2></div><button class="text-button" type="button" @click="newSession">New</button></div>
        <div class="session-list">
          <div v-for="session in sessions" :key="session.id" class="session-row" :class="{ active: session.id === currentSessionId }">
            <button type="button" @click="openSession(session.id)"><strong>{{ session.title }}</strong><span>{{ session.messageCount }} messages / {{ new Date(session.updatedAt).toLocaleDateString() }}</span></button>
            <button class="delete-button" type="button" :aria-label="`Delete conversation ${session.title}`" @click="removeSession(session.id)">Delete</button>
          </div>
        </div>
      </aside>
    </div>

    <div v-if="settingsOpen" class="overlay" @click.self="settingsOpen = false">
      <aside class="sheet settings-sheet" aria-label="Local model settings">
        <div class="sheet-header"><div><span>On-device configuration</span><h2>Provider and agent</h2></div><button class="close-button" type="button" aria-label="Close settings" @click="settingsOpen = false">&times;</button></div>

        <section class="settings-section">
          <h3>Provider</h3>
          <div class="segmented" role="group" aria-label="Provider format">
            <button type="button" :class="{ active: providerForm.format === 'openai' }" @click="applyProviderPreset('openai')">OpenAI compatible</button>
            <button type="button" :class="{ active: providerForm.format === 'anthropic' }" @click="applyProviderPreset('anthropic')">Anthropic</button>
          </div>
          <label>Name<input v-model="providerForm.label" autocomplete="off" /></label>
          <label>Endpoint<input v-model="providerForm.baseUrl" type="url" inputmode="url" autocomplete="url" /></label>
          <label>API Key
            <span class="password-field"><input v-model="providerForm.apiKey" :type="showApiKey ? 'text' : 'password'" autocomplete="off" :placeholder="providers.some(item => item.id === providerForm.id) ? 'Leave blank to keep the saved key' : 'Required'" /><button type="button" @click="showApiKey = !showApiKey">{{ showApiKey ? 'Hide' : 'Show' }}</button></span>
          </label>
          <label>Model
            <input v-model="providerForm.defaultModel" list="local-model-options" autocomplete="off" />
            <datalist id="local-model-options"><option v-for="model in modelOptions" :key="model" :value="model" /></datalist>
          </label>
          <div class="inline-actions">
            <button class="secondary-button" type="button" :disabled="modelLoading" @click="discoverModels">{{ modelLoading ? 'Loading...' : 'Load model list' }}</button>
            <button class="primary-button" type="button" :disabled="saving" @click="saveProvider">{{ saving ? 'Saving...' : 'Save provider' }}</button>
          </div>
          <div v-if="providers.length" class="provider-list">
            <button v-for="provider in providers" :key="provider.id" type="button" @click="editProvider(provider)"><span>{{ provider.label }}</span><small>{{ provider.defaultModel }} / {{ provider.hasApiKey ? 'Key saved' : 'Key missing' }}</small></button>
          </div>
        </section>

        <section class="settings-section">
          <h3>Base agent</h3>
          <label>Agent name<input v-model="agent.name" maxlength="40" /></label>
          <label>Provider<select v-model="agent.providerId"><option value="" disabled>Select a provider</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.label }}</option></select></label>
          <label>Model<input v-model="agent.model" /></label>
          <label>System prompt<textarea v-model="agent.systemPrompt" rows="5"></textarea></label>
          <button class="primary-button full" type="button" :disabled="saving || !providers.length" @click="saveAgent">Save agent</button>
        </section>

        <section class="settings-section capability-section">
          <h3>Advanced capability migration</h3>
          <div v-for="capability in capabilities" :key="capability.id" class="capability-row"><span>{{ capability.label }}</span><small :class="capability.state">{{ capability.state === 'foundation' ? 'Foundation ready' : 'Planned' }}</small></div>
        </section>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.local-app {
  --bg: #07130f;
  --surface: rgba(17, 36, 29, 0.92);
  --surface-strong: #142b22;
  --line: rgba(143, 229, 96, 0.18);
  --primary: #8fe560;
  --primary-strong: #6bc840;
  --text: #f2f8ef;
  --muted: #9eb3a6;
  --danger: #ff8d82;
  position: fixed;
  inset: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: radial-gradient(circle at 50% -10%, rgba(91, 179, 92, 0.2), transparent 38%), var(--bg);
  color: var(--text);
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}
button, input, select, textarea { font: inherit; }
button { min-width: 44px; min-height: 44px; }
.topbar { display: grid; grid-template-columns: 48px 1fr 48px; align-items: center; gap: 10px; padding: calc(env(safe-area-inset-top) + 10px) 12px 10px; border-bottom: 1px solid var(--line); background: rgba(7, 19, 15, 0.88); backdrop-filter: blur(16px); z-index: 2; }
.icon-button, .attach-button, .send-button, .close-button { border: 0; border-radius: 14px; color: var(--text); background: rgba(255,255,255,.06); display: grid; place-items: center; }
.icon-button svg, .attach-button svg, .send-button svg { width: 23px; height: 23px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.brand-block { display: flex; align-items: center; gap: 10px; min-width: 0; }
.brand-block div { min-width: 0; display: grid; }
.brand-block strong { font-size: 16px; }
.brand-block span:not(.status-dot) { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; background: #718078; box-shadow: 0 0 0 5px rgba(113,128,120,.12); }
.status-dot.ready { background: var(--primary); box-shadow: 0 0 0 5px rgba(143,229,96,.12); }
.messages { overflow-y: auto; padding: 22px 16px 28px; scroll-behavior: smooth; }
.center-state, .welcome-card { min-height: 68vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 14px; }
.welcome-card { max-width: 520px; margin: auto; }
.logo-mark { width: 68px; height: 68px; display: grid; place-items: center; border-radius: 22px; color: #0b190f; background: linear-gradient(145deg, #b5f58c, #6bc840); font-weight: 900; letter-spacing: -2px; box-shadow: 0 18px 45px rgba(107,200,64,.22); }
.welcome-card h1 { font-size: 25px; }
.welcome-card p { color: var(--muted); line-height: 1.7; max-width: 360px; }
.feature-grid { display: grid; grid-template-columns: repeat(2, minmax(120px, 1fr)); gap: 8px; width: min(100%, 330px); }
.feature-grid span { padding: 10px; border: 1px solid var(--line); border-radius: 12px; color: #cfe1d3; font-size: 13px; }
.message { max-width: 760px; margin: 0 auto 18px; }
.message.user { display: grid; justify-items: end; }
.message-label { color: var(--muted); font-size: 12px; margin: 0 5px 6px; }
.bubble { max-width: 88%; padding: 13px 15px 8px; border: 1px solid var(--line); border-radius: 18px 18px 18px 5px; background: var(--surface); box-shadow: 0 8px 28px rgba(0,0,0,.12); }
.user .bubble { border-radius: 18px 18px 5px 18px; background: linear-gradient(145deg, rgba(97,169,75,.5), rgba(44,91,58,.78)); }
.bubble p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; font-size: 15px; }
.bubble time { display: block; margin-top: 5px; text-align: right; color: #83998a; font-size: 10px; }
.stream-cursor { display: inline-block; width: 7px; height: 16px; margin-left: 3px; border-radius: 2px; background: var(--primary); vertical-align: -2px; animation: pulse 1s ease-in-out infinite; }
.composer { padding: 8px 12px calc(env(safe-area-inset-bottom) + 8px); border-top: 1px solid var(--line); background: rgba(7,19,15,.92); backdrop-filter: blur(16px); }
.composer-row { display: grid; grid-template-columns: 44px 1fr 46px; gap: 8px; align-items: end; max-width: 760px; margin: auto; }
.composer textarea { min-height: 46px; max-height: 132px; resize: none; padding: 12px 14px; color: var(--text); background: rgba(255,255,255,.06); border: 1px solid var(--line); border-radius: 16px; outline: none; }
.composer textarea:focus { border-color: rgba(143,229,96,.65); box-shadow: 0 0 0 3px rgba(143,229,96,.1); }
.send-button { color: #0b190f; background: var(--primary); }
.send-button:disabled { opacity: .38; }
.send-button.stop { background: var(--danger); }
.send-button.stop span { width: 14px; height: 14px; border-radius: 3px; background: #32110e; }
.composer > small { display: block; text-align: center; margin-top: 6px; color: #718477; font-size: 10px; }
.attachment-strip { display: flex; gap: 8px; overflow-x: auto; max-width: 760px; margin: 0 auto 8px; }
.attachment-chip { display: flex; align-items: center; flex: 0 0 auto; gap: 8px; padding: 7px 8px 7px 11px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.attachment-chip span { display: grid; max-width: 170px; }
.attachment-chip strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.attachment-chip small { color: var(--muted); font-size: 10px; }
.attachment-chip button { min-width: 32px; min-height: 32px; border: 0; border-radius: 9px; color: var(--muted); background: rgba(255,255,255,.06); }
.error-banner { position: fixed; left: 14px; right: 14px; bottom: 90px; z-index: 4; padding: 11px 14px; border: 1px solid rgba(255,141,130,.4); border-radius: 12px; color: #ffd4cf; background: rgba(91,24,20,.94); font-size: 13px; }
.overlay { position: fixed; inset: 0; z-index: 10; display: flex; align-items: flex-end; background: rgba(0,0,0,.58); }
.sheet { width: 100%; max-height: 91vh; overflow-y: auto; padding: 18px 16px calc(env(safe-area-inset-bottom) + 24px); border: 1px solid var(--line); border-bottom: 0; border-radius: 26px 26px 0 0; background: #0e2119; box-shadow: 0 -24px 80px rgba(0,0,0,.45); animation: sheet-in .22s ease-out; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 18px; }
.sheet-header span { color: var(--primary); font-size: 11px; text-transform: uppercase; letter-spacing: 1.6px; }
.sheet-header h2 { font-size: 22px; }
.close-button { font-size: 26px; }
.text-button, .primary-button, .secondary-button { padding: 0 16px; border-radius: 13px; font-weight: 700; }
.text-button { border: 1px solid var(--line); color: var(--text); background: transparent; }
.primary-button { border: 0; color: #0b190f; background: var(--primary); }
.secondary-button { border: 1px solid var(--line); color: var(--text); background: rgba(255,255,255,.05); }
.primary-button.full { width: 100%; }
.settings-section { margin-top: 16px; padding: 16px; border: 1px solid var(--line); border-radius: 18px; background: rgba(255,255,255,.025); }
.settings-section h3 { margin-bottom: 14px; font-size: 16px; }
.settings-section label { display: grid; gap: 7px; margin-bottom: 13px; color: #c9d8cd; font-size: 13px; }
.settings-section input, .settings-section select, .settings-section textarea { width: 100%; min-height: 46px; padding: 11px 12px; border: 1px solid var(--line); border-radius: 12px; outline: none; color: var(--text); background: #0a1913; }
.settings-section textarea { resize: vertical; line-height: 1.6; }
.settings-section input:focus, .settings-section select:focus, .settings-section textarea:focus { border-color: var(--primary); }
.password-field { display: grid; grid-template-columns: 1fr 58px; }
.password-field input { border-radius: 12px 0 0 12px; }
.password-field button { min-width: 58px; border: 1px solid var(--line); border-left: 0; border-radius: 0 12px 12px 0; color: var(--primary); background: #12271e; }
.segmented { display: grid; grid-template-columns: 1fr 1fr; padding: 4px; margin-bottom: 14px; border-radius: 13px; background: #091711; }
.segmented button { border: 0; border-radius: 10px; color: var(--muted); background: transparent; }
.segmented button.active { color: var(--text); background: #1b382b; box-shadow: inset 0 0 0 1px var(--line); }
.inline-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.provider-list { display: grid; gap: 8px; margin-top: 14px; }
.provider-list button { display: grid; justify-items: start; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; color: var(--text); background: rgba(255,255,255,.025); text-align: left; }
.provider-list small { color: var(--muted); }
.session-list { display: grid; gap: 9px; }
.session-row { display: grid; grid-template-columns: 1fr auto; align-items: center; border: 1px solid var(--line); border-radius: 14px; background: rgba(255,255,255,.025); }
.session-row.active { border-color: rgba(143,229,96,.55); background: rgba(143,229,96,.07); }
.session-row > button:first-child { display: grid; justify-items: start; padding: 12px; border: 0; color: var(--text); background: transparent; text-align: left; }
.session-row span { color: var(--muted); font-size: 11px; }
.delete-button { min-width: 58px; border: 0; color: var(--danger); background: transparent; }
.capability-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,.05); }
.capability-row:last-child { border-bottom: 0; }
.capability-row small { color: var(--muted); }
.capability-row small.foundation { color: var(--primary); }
.form-error { margin-top: 14px; color: #ffd0cb; }
.loader { width: 28px; height: 28px; border: 3px solid rgba(143,229,96,.18); border-top-color: var(--primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 50% { opacity: .28; } }
@keyframes sheet-in { from { transform: translateY(22px); opacity: .4; } }
@media (min-width: 720px) { .sheet { max-width: 620px; margin: 0 auto; border-radius: 26px 26px 0 0; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; } }
</style>

package com.xiaoda.agent.local

import okhttp3.Call
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class LocalAiController(
    private val store: LocalStateStore,
    private val providerClient: ProviderClient = ProviderClient(),
    private val validator: ProviderConfigValidator,
    private val capabilities: LocalCapabilityRegistry = LocalCapabilityRegistry(),
    private val executor: ExecutorService = Executors.newCachedThreadPool(),
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val activeCalls = ConcurrentHashMap<String, Call>()

    fun bootstrap(): JSONObject = JSONObject()
        .put("providers", JSONArray(store.providers().map { it.toJson(store.apiKey(it.id) != null) }))
        .put("agent", store.agent().toJson())
        .put("sessions", JSONArray(store.sessions().map(LocalSession::summaryJson)))
        .put("capabilities", capabilities.descriptors())

    fun saveProvider(args: JSONObject): JSONObject {
        val provider = LocalProvider(
            id = args.optString("id").trim().lowercase(),
            label = args.optString("label").trim(),
            format = args.optString("format", "openai").trim().lowercase(),
            baseUrl = args.optString("baseUrl").trim().trimEnd('/'),
            defaultModel = args.optString("defaultModel").trim(),
        )
        validator.validate(provider)?.let { return JSONObject().put("error", it) }
        val apiKey = args.optString("apiKey").trim()
        if (apiKey.any(Char::isISOControl) || apiKey.length > MAX_API_KEY_LENGTH) return JSONObject().put("error", "invalid_api_key")
        if (apiKey.isEmpty() && store.apiKey(provider.id) == null) return JSONObject().put("error", "api_key_required")
        store.saveProvider(provider, apiKey.takeIf(String::isNotEmpty))
        val currentAgent = store.agent()
        if (currentAgent.providerId.isEmpty()) store.saveAgent(currentAgent.copy(providerId = provider.id, model = provider.defaultModel))
        return provider.toJson(true)
    }

    fun deleteProvider(args: JSONObject): JSONObject {
        val providerId = args.optString("providerId")
        if (!providerId.matches(PROVIDER_ID)) return JSONObject().put("error", "invalid_provider_id")
        store.deleteProvider(providerId)
        return JSONObject().put("deleted", true)
    }

    fun saveAgent(args: JSONObject): JSONObject {
        val providerId = args.optString("providerId")
        val provider = store.providers().firstOrNull { it.id == providerId } ?: return JSONObject().put("error", "provider_not_found")
        val model = args.optString("model", provider.defaultModel).trim()
        val systemPrompt = args.optString("systemPrompt", DEFAULT_SYSTEM_PROMPT).trim()
        val name = args.optString("name", "Xiaoda").trim()
        if (model.isEmpty() || model.length > 160) return JSONObject().put("error", "invalid_model")
        if (systemPrompt.isEmpty() || systemPrompt.length > 20_000) return JSONObject().put("error", "invalid_system_prompt")
        if (name.isEmpty() || name.length > 40) return JSONObject().put("error", "invalid_agent_name")
        return LocalAgentConfig(name, providerId, model, systemPrompt).also(store::saveAgent).toJson()
    }

    fun createSession(): JSONObject = store.createSession().summaryJson()

    fun sessions(): JSONObject = JSONObject().put("sessions", JSONArray(store.sessions().map(LocalSession::summaryJson)))

    fun messages(args: JSONObject): JSONObject {
        val session = store.session(args.optString("sessionId")) ?: return JSONObject().put("error", "session_not_found")
        return JSONObject().put("session", session.summaryJson()).put("messages", JSONArray(session.messages.map(LocalMessage::toJson)))
    }

    fun deleteSession(args: JSONObject): JSONObject = JSONObject().put("deleted", store.deleteSession(args.optString("sessionId")))

    fun listModels(args: JSONObject, reply: (JSONObject) -> Unit) {
        val provider = store.providers().firstOrNull { it.id == args.optString("providerId") }
        if (provider == null) {
            reply(JSONObject().put("error", "provider_not_found"))
            return
        }
        val apiKey = store.apiKey(provider.id)
        if (apiKey == null) {
            reply(JSONObject().put("error", "api_key_required"))
            return
        }
        executor.execute {
            val result = runCatching { JSONObject().put("models", JSONArray(providerClient.listModels(provider, apiKey))) }
                .getOrElse { JSONObject().put("error", safeError(it)) }
            reply(result)
        }
    }

    fun storeAttachment(name: String, mimeType: String, bytes: ByteArray): JSONObject =
        store.storeAttachment(name, mimeType, bytes).publicJson()

    fun startChat(args: JSONObject, event: (JSONObject) -> Unit): JSONObject {
        val sessionId = args.optString("sessionId")
        val text = args.optString("text").trim()
        if (text.isEmpty() || text.length > 100_000) return JSONObject().put("error", "invalid_message")
        if (store.session(sessionId) == null) return JSONObject().put("error", "session_not_found")
        val agent = store.agent()
        val provider = store.providers().firstOrNull { it.id == agent.providerId } ?: return JSONObject().put("error", "provider_not_configured")
        val apiKey = store.apiKey(provider.id) ?: return JSONObject().put("error", "api_key_required")
        val model = agent.model.ifBlank { provider.defaultModel }
        val requestId = args.optString("requestId").takeIf { it.matches(REQUEST_ID) } ?: UUID.randomUUID().toString()
        val attachmentIds = args.optJSONArray("attachmentIds")?.let { array ->
            (0 until array.length()).map { array.optString(it) }.filter { it.matches(UUID_PATTERN) }
        }.orEmpty()
        val attachments = attachmentIds.mapNotNull { id ->
            val item = store.attachment(id) ?: return@mapNotNull null
            val bytes = store.attachmentBytes(id) ?: return@mapNotNull null
            LocalAttachmentPayload(item.name, item.mimeType, bytes)
        }
        val unsupportedAttachment = attachments.firstOrNull { attachment ->
            when (provider.format) {
                "anthropic" -> attachment.mimeType != "text/plain" && attachment.mimeType != "application/pdf" && !attachment.mimeType.startsWith("image/")
                else -> attachment.mimeType != "text/plain" && !attachment.mimeType.startsWith("image/")
            }
        }
        if (unsupportedAttachment != null) return JSONObject().put("error", "attachment_not_supported_by_provider")
        val userMessage = LocalMessage(UUID.randomUUID().toString(), "user", text, clock(), attachmentIds)
        val session = store.appendMessage(sessionId, userMessage)
        executor.execute {
            try {
                var accumulated = ""
                val answer = providerClient.streamChat(
                    provider = provider,
                    apiKey = apiKey,
                    model = model,
                    systemPrompt = agent.systemPrompt,
                    messages = session.messages.filter { it.role == "user" || it.role == "assistant" }.takeLast(MAX_CONTEXT_MESSAGES),
                    attachments = attachments,
                    onCall = { call -> activeCalls[requestId] = call },
                    onDelta = { delta ->
                        accumulated += delta
                        event(JSONObject().put("event", "local.chat.delta").put("data", JSONObject().put("requestId", requestId).put("delta", delta).put("accumulated", accumulated)))
                    },
                )
                val finalAnswer = answer.ifBlank { accumulated }
                if (finalAnswer.isBlank()) throw IllegalStateException("empty_provider_response")
                store.appendMessage(sessionId, LocalMessage(UUID.randomUUID().toString(), "assistant", finalAnswer, clock()))
                event(JSONObject().put("event", "local.chat.completed").put("data", JSONObject().put("requestId", requestId).put("content", finalAnswer)))
            } catch (error: Throwable) {
                val code = if (activeCalls[requestId]?.isCanceled() == true) "cancelled" else safeError(error)
                event(JSONObject().put("event", "local.chat.failed").put("data", JSONObject().put("requestId", requestId).put("error", code)))
            } finally {
                activeCalls.remove(requestId)
            }
        }
        return JSONObject().put("started", true).put("requestId", requestId)
    }

    fun abort(args: JSONObject): JSONObject {
        val requestId = args.optString("requestId")
        val call = activeCalls.remove(requestId)
        call?.cancel()
        return JSONObject().put("cancelled", call != null)
    }

    fun close() {
        activeCalls.values.forEach(Call::cancel)
        activeCalls.clear()
        executor.shutdownNow()
    }

    private fun safeError(error: Throwable): String = when (error) {
        is ProviderException -> when (error.statusCode) {
            401, 403 -> "provider_authentication_failed"
            404 -> "provider_endpoint_or_model_not_found"
            429 -> "provider_rate_limited"
            else -> error.message.takeIf { it.matches(SAFE_ERROR) } ?: "provider_request_failed"
        }
        else -> error.message?.takeIf { it.matches(SAFE_ERROR) } ?: "provider_request_failed"
    }

    private companion object {
        const val MAX_API_KEY_LENGTH = 16_384
        const val MAX_CONTEXT_MESSAGES = 100
        val PROVIDER_ID = Regex("[a-z0-9][a-z0-9._-]{0,63}")
        val UUID_PATTERN = Regex("[a-f0-9-]{36}")
        val REQUEST_ID = Regex("[A-Za-z0-9._:-]{1,100}")
        val SAFE_ERROR = Regex("[a-z0-9_]{1,80}")
    }
}

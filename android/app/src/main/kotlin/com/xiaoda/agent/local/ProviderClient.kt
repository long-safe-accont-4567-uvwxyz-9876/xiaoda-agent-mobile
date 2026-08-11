package com.xiaoda.agent.local

import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Base64
import java.util.concurrent.TimeUnit

class ProviderClient(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build(),
) {
    fun listModels(provider: LocalProvider, apiKey: String): List<String> {
        val request = Request.Builder()
            .url(endpoint(provider.baseUrl, "models"))
            .apply { authorization(provider, apiKey) }
            .get()
            .build()
        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw ProviderException(response.code, providerError(body))
            val data = JSONObject(body).optJSONArray("data") ?: JSONArray()
            return (0 until data.length()).mapNotNull { index ->
                data.optJSONObject(index)?.optString("id")?.takeIf(String::isNotBlank)
            }.distinct().sorted()
        }
    }

    fun streamChat(
        provider: LocalProvider,
        apiKey: String,
        model: String,
        systemPrompt: String,
        messages: List<LocalMessage>,
        attachments: List<LocalAttachmentPayload>,
        onCall: (Call) -> Unit,
        onDelta: (String) -> Unit,
    ): String {
        val payload = when (provider.format) {
            "anthropic" -> anthropicPayload(model, systemPrompt, messages, attachments)
            else -> openAiPayload(model, systemPrompt, messages, attachments)
        }
        val request = Request.Builder()
            .url(endpoint(provider.baseUrl, if (provider.format == "anthropic") "messages" else "chat/completions"))
            .apply { authorization(provider, apiKey) }
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        val call = client.newCall(request)
        onCall(call)
        call.execute().use { response ->
            if (!response.isSuccessful) {
                val body = response.body?.string().orEmpty()
                throw ProviderException(response.code, providerError(body))
            }
            val source = response.body?.source() ?: throw ProviderException(response.code, "empty_provider_response")
            val result = StringBuilder()
            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break
                if (!line.startsWith("data:")) continue
                val data = line.removePrefix("data:").trim()
                if (data.isEmpty() || data == "[DONE]") continue
                val delta = runCatching {
                    val event = JSONObject(data)
                    if (provider.format == "anthropic") {
                        if (event.optString("type") == "content_block_delta") event.optJSONObject("delta")?.optString("text").orEmpty() else ""
                    } else {
                        event.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("delta")?.optString("content").orEmpty()
                    }
                }.getOrDefault("")
                if (delta.isNotEmpty()) {
                    result.append(delta)
                    onDelta(delta)
                }
            }
            return result.toString()
        }
    }

    private fun openAiPayload(
        model: String,
        systemPrompt: String,
        messages: List<LocalMessage>,
        attachments: List<LocalAttachmentPayload>,
    ): JSONObject {
        val output = JSONArray().put(JSONObject().put("role", "system").put("content", systemPrompt))
        messages.forEachIndexed { index, message ->
            val isLastUser = index == messages.lastIndex && message.role == "user"
            if (!isLastUser || attachments.isEmpty()) {
                output.put(JSONObject().put("role", message.role).put("content", message.content))
            } else {
                val content = JSONArray().put(JSONObject().put("type", "text").put("text", message.content))
                attachments.filter { it.mimeType.startsWith("image/") }.forEach { attachment ->
                    val encoded = Base64.getEncoder().encodeToString(attachment.bytes)
                    content.put(JSONObject().put("type", "image_url").put("image_url", JSONObject().put("url", "data:${attachment.mimeType};base64,$encoded")))
                }
                attachments.filter { it.mimeType == "text/plain" }.forEach { attachment ->
                    content.put(JSONObject().put("type", "text").put("text", "Attachment ${attachment.name}:\n${String(attachment.bytes, Charsets.UTF_8)}"))
                }
                output.put(JSONObject().put("role", message.role).put("content", content))
            }
        }
        return JSONObject().put("model", model).put("stream", true).put("messages", output)
    }

    private fun anthropicPayload(
        model: String,
        systemPrompt: String,
        messages: List<LocalMessage>,
        attachments: List<LocalAttachmentPayload>,
    ): JSONObject {
        val output = JSONArray()
        messages.filter { it.role != "system" }.forEachIndexed { index, message ->
            val isLastUser = index == messages.filter { it.role != "system" }.lastIndex && message.role == "user"
            if (!isLastUser || attachments.isEmpty()) {
                output.put(JSONObject().put("role", message.role).put("content", message.content))
            } else {
                val content = JSONArray()
                attachments.filter { it.mimeType.startsWith("image/") }.forEach { attachment ->
                    content.put(JSONObject().put("type", "image").put("source", base64Source(attachment)))
                }
                attachments.filter { it.mimeType == "application/pdf" }.forEach { attachment ->
                    content.put(JSONObject().put("type", "document").put("source", base64Source(attachment)))
                }
                attachments.filter { it.mimeType == "text/plain" }.forEach { attachment ->
                    content.put(JSONObject().put("type", "text").put("text", "Attachment ${attachment.name}:\n${String(attachment.bytes, Charsets.UTF_8)}"))
                }
                content.put(JSONObject().put("type", "text").put("text", message.content))
                output.put(JSONObject().put("role", "user").put("content", content))
            }
        }
        return JSONObject()
            .put("model", model)
            .put("system", systemPrompt)
            .put("max_tokens", 4096)
            .put("stream", true)
            .put("messages", output)
    }

    private fun base64Source(attachment: LocalAttachmentPayload): JSONObject = JSONObject()
        .put("type", "base64")
        .put("media_type", attachment.mimeType)
        .put("data", Base64.getEncoder().encodeToString(attachment.bytes))

    private fun Request.Builder.authorization(provider: LocalProvider, apiKey: String): Request.Builder = apply {
        if (provider.format == "anthropic") {
            header("x-api-key", apiKey)
            header("anthropic-version", "2023-06-01")
        } else {
            header("Authorization", "Bearer $apiKey")
        }
        header("Content-Type", "application/json")
    }

    private fun endpoint(baseUrl: String, path: String): String {
        val base = baseUrl.trimEnd('/')
        return if (base.endsWith("/v1")) "$base/$path" else "$base/v1/$path"
    }

    private fun providerError(body: String): String = runCatching {
        val root = JSONObject(body)
        root.optJSONObject("error")?.optString("message")?.takeIf(String::isNotBlank)
            ?: root.optString("error").takeIf(String::isNotBlank)
            ?: "provider_request_failed"
    }.getOrDefault("provider_request_failed")

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}

data class LocalAttachmentPayload(val name: String, val mimeType: String, val bytes: ByteArray)

class ProviderException(val statusCode: Int, override val message: String) : RuntimeException(message)

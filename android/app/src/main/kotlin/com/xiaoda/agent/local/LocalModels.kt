package com.xiaoda.agent.local

import org.json.JSONArray
import org.json.JSONObject

const val DEFAULT_SYSTEM_PROMPT = "You are Xiaoda, a reliable, clear, and privacy-conscious mobile AI assistant."

data class LocalProvider(
    val id: String,
    val label: String,
    val format: String,
    val baseUrl: String,
    val defaultModel: String,
) {
    fun toJson(hasApiKey: Boolean = false): JSONObject = JSONObject()
        .put("id", id)
        .put("label", label)
        .put("format", format)
        .put("baseUrl", baseUrl)
        .put("defaultModel", defaultModel)
        .put("hasApiKey", hasApiKey)

    companion object {
        fun fromJson(value: JSONObject): LocalProvider = LocalProvider(
            id = value.getString("id"),
            label = value.getString("label"),
            format = value.getString("format"),
            baseUrl = value.getString("baseUrl"),
            defaultModel = value.optString("defaultModel"),
        )
    }
}

data class LocalAgentConfig(
    val name: String = "Xiaoda",
    val providerId: String = "",
    val model: String = "",
    val systemPrompt: String = DEFAULT_SYSTEM_PROMPT,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("name", name)
        .put("providerId", providerId)
        .put("model", model)
        .put("systemPrompt", systemPrompt)

    companion object {
        fun fromJson(value: JSONObject): LocalAgentConfig = LocalAgentConfig(
            name = value.optString("name", "Xiaoda"),
            providerId = value.optString("providerId"),
            model = value.optString("model"),
            systemPrompt = value.optString("systemPrompt", DEFAULT_SYSTEM_PROMPT),
        )
    }
}

data class LocalAttachment(
    val id: String,
    val name: String,
    val mimeType: String,
    val sizeBytes: Long,
    val path: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("name", name)
        .put("mimeType", mimeType)
        .put("sizeBytes", sizeBytes)
        .put("path", path)

    fun publicJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("name", name)
        .put("mimeType", mimeType)
        .put("sizeBytes", sizeBytes)

    companion object {
        fun fromJson(value: JSONObject): LocalAttachment = LocalAttachment(
            id = value.getString("id"),
            name = value.getString("name"),
            mimeType = value.getString("mimeType"),
            sizeBytes = value.getLong("sizeBytes"),
            path = value.getString("path"),
        )
    }
}

data class LocalMessage(
    val id: String,
    val role: String,
    val content: String,
    val timestamp: Long,
    val attachments: List<String> = emptyList(),
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("role", role)
        .put("content", content)
        .put("timestamp", timestamp)
        .put("attachments", JSONArray(attachments))

    companion object {
        fun fromJson(value: JSONObject): LocalMessage = LocalMessage(
            id = value.getString("id"),
            role = value.getString("role"),
            content = value.getString("content"),
            timestamp = value.getLong("timestamp"),
            attachments = value.optJSONArray("attachments")?.let { array ->
                (0 until array.length()).map { array.getString(it) }
            }.orEmpty(),
        )
    }
}

data class LocalSession(
    val id: String,
    val title: String,
    val createdAt: Long,
    val updatedAt: Long,
    val messages: List<LocalMessage>,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("title", title)
        .put("createdAt", createdAt)
        .put("updatedAt", updatedAt)
        .put("messages", JSONArray(messages.map(LocalMessage::toJson)))

    fun summaryJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("title", title)
        .put("createdAt", createdAt)
        .put("updatedAt", updatedAt)
        .put("messageCount", messages.size)

    companion object {
        fun fromJson(value: JSONObject): LocalSession {
            val messages = value.optJSONArray("messages") ?: JSONArray()
            return LocalSession(
                id = value.getString("id"),
                title = value.optString("title", "New chat"),
                createdAt = value.getLong("createdAt"),
                updatedAt = value.getLong("updatedAt"),
                messages = (0 until messages.length()).map { LocalMessage.fromJson(messages.getJSONObject(it)) },
            )
        }
    }
}

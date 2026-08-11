package com.xiaoda.agent.local

import android.content.Context
import com.xiaoda.agent.security.SecureSecretStore
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

class LocalStateStore(
    context: Context,
    private val secrets: SecureSecretStore,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val preferences = context.getSharedPreferences("xiaoda_local_state", Context.MODE_PRIVATE)
    private val root = File(context.filesDir, "local-ai").apply { mkdirs() }
    private val sessionsDir = File(root, "sessions").apply { mkdirs() }
    private val attachmentsDir = File(root, "attachments").apply { mkdirs() }

    @Synchronized
    fun providers(): List<LocalProvider> = runCatching {
        val array = JSONArray(preferences.getString(PROVIDERS, "[]"))
        (0 until array.length()).map { LocalProvider.fromJson(array.getJSONObject(it)) }
    }.getOrDefault(emptyList())

    @Synchronized
    fun saveProvider(provider: LocalProvider, apiKey: String?) {
        val updated = providers().filterNot { it.id == provider.id } + provider
        preferences.edit().putString(PROVIDERS, JSONArray(updated.map(LocalProvider::toJson)).toString()).apply()
        if (!apiKey.isNullOrBlank()) secrets.put(secretName(provider.id), apiKey.trim())
    }

    @Synchronized
    fun deleteProvider(providerId: String) {
        val updated = providers().filterNot { it.id == providerId }
        preferences.edit().putString(PROVIDERS, JSONArray(updated.map(LocalProvider::toJson)).toString()).apply()
        secrets.remove(secretName(providerId))
        val agent = agent()
        if (agent.providerId == providerId) saveAgent(agent.copy(providerId = "", model = ""))
    }

    fun apiKey(providerId: String): String? = secrets.get(secretName(providerId))

    @Synchronized
    fun agent(): LocalAgentConfig = preferences.getString(AGENT, null)?.let {
        runCatching { LocalAgentConfig.fromJson(JSONObject(it)) }.getOrNull()
    } ?: LocalAgentConfig()

    @Synchronized
    fun saveAgent(agent: LocalAgentConfig) {
        preferences.edit().putString(AGENT, agent.toJson().toString()).apply()
    }

    @Synchronized
    fun createSession(): LocalSession {
        val now = clock()
        return LocalSession(UUID.randomUUID().toString(), "New chat", now, now, emptyList()).also(::writeSession)
    }

    @Synchronized
    fun sessions(): List<LocalSession> = sessionsDir.listFiles { file -> file.extension == "json" }.orEmpty()
        .mapNotNull { runCatching { LocalSession.fromJson(JSONObject(it.readText())) }.getOrNull() }
        .sortedByDescending(LocalSession::updatedAt)

    @Synchronized
    fun session(sessionId: String): LocalSession? = safeId(sessionId)?.let { id ->
        val file = File(sessionsDir, "$id.json")
        if (!file.isFile) null else runCatching { LocalSession.fromJson(JSONObject(file.readText())) }.getOrNull()
    }

    @Synchronized
    fun appendMessage(sessionId: String, message: LocalMessage): LocalSession {
        val current = session(sessionId) ?: throw IllegalArgumentException("session_not_found")
        val messages = current.messages + message
        val firstUser = messages.firstOrNull { it.role == "user" }?.content.orEmpty().trim()
        val title = if (current.title == "New chat" && firstUser.isNotEmpty()) firstUser.take(32) else current.title
        return current.copy(title = title, updatedAt = clock(), messages = messages).also(::writeSession)
    }

    @Synchronized
    fun deleteSession(sessionId: String): Boolean = safeId(sessionId)?.let { File(sessionsDir, "$it.json").delete() } ?: false

    @Synchronized
    fun storeAttachment(name: String, mimeType: String, bytes: ByteArray): LocalAttachment {
        val id = UUID.randomUUID().toString()
        val safeName = name.replace(Regex("[^A-Za-z0-9._\u4e00-\u9fff-]"), "_").take(120).ifBlank { "attachment" }
        val file = File(attachmentsDir, "$id-$safeName")
        atomicWrite(file, bytes)
        val attachment = LocalAttachment(id, safeName, mimeType, bytes.size.toLong(), file.absolutePath)
        preferences.edit().putString("attachment.$id", attachment.toJson().toString()).apply()
        return attachment
    }

    fun attachment(id: String): LocalAttachment? = safeId(id)?.let {
        preferences.getString("attachment.$it", null)?.let { raw ->
            runCatching { LocalAttachment.fromJson(JSONObject(raw)) }.getOrNull()?.takeIf { item -> File(item.path).isFile }
        }
    }

    fun attachmentBytes(id: String): ByteArray? = attachment(id)?.let { runCatching { File(it.path).readBytes() }.getOrNull() }

    private fun writeSession(session: LocalSession) {
        val id = safeId(session.id) ?: throw IllegalArgumentException("invalid_session_id")
        atomicWrite(File(sessionsDir, "$id.json"), session.toJson().toString().toByteArray(Charsets.UTF_8))
    }

    private fun atomicWrite(target: File, bytes: ByteArray) {
        val temporary = File(target.parentFile, ".${target.name}.${UUID.randomUUID()}.tmp")
        temporary.writeBytes(bytes)
        runCatching {
            Files.move(
                temporary.toPath(),
                target.toPath(),
                StandardCopyOption.ATOMIC_MOVE,
                StandardCopyOption.REPLACE_EXISTING,
            )
        }.recoverCatching {
            Files.move(temporary.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }.getOrElse {
            temporary.delete()
            throw IllegalStateException("local_storage_write_failed")
        }
    }

    private fun safeId(id: String): String? = id.takeIf { it.matches(Regex("[a-f0-9-]{36}")) }
    private fun secretName(providerId: String): String = "provider.$providerId.apiKey"

    private companion object {
        const val PROVIDERS = "providers"
        const val AGENT = "agent"
    }
}

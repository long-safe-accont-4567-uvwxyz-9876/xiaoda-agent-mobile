package com.xiaoda.agent

import android.content.Context
import android.net.Uri

/**
 * Persists the remote Xiaoda Agent server endpoint the Web UI connects to.
 * The endpoint is stored in private shared preferences; credentials are never
 * written here (they stay in the Keystore-backed token store).
 */
class ConnectionSettings(context: Context) {
    private val preferences = context.getSharedPreferences("connection", Context.MODE_PRIVATE)

    var serverUrl: String?
        get() = preferences.getString(KEY_SERVER_URL, null)
        set(value) = preferences.edit().putString(KEY_SERVER_URL, value).apply()

    fun clear() {
        preferences.edit().remove(KEY_SERVER_URL).apply()
    }

    companion object {
        private const val KEY_SERVER_URL = "server_url"

        /**
         * Normalizes and validates a user-supplied server URL.
         * Returns null when the value is not a usable https/http origin.
         */
        fun normalize(raw: String?): String? {
            if (raw.isNullOrBlank()) return null
            val uri = runCatching { Uri.parse(raw.trim()) }.getOrNull() ?: return null
            val scheme = uri.scheme?.lowercase() ?: return null
            if (scheme !in setOf("https", "http")) return null
            val host = uri.host ?: return null
            if (host.isBlank() || uri.userInfo != null) return null
            val port = uri.port
            if (port !in -1..65535) return null
            val path = uri.path?.trimEnd('/')?.takeIf { it.isNotEmpty() } ?: ""
            return Uri.Builder()
                .scheme(scheme)
                .authority(if (port != -1) "$host:$port" else host)
                .path(path)
                .build()
                .toString()
        }
    }
}
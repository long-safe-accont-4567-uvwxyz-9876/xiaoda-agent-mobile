package com.xiaoda.agent.webcontainer

import org.json.JSONObject

class AssetManifestVerifier {
    fun isValid(manifest: String, appVersion: String, actualFiles: Map<String, String>): Boolean {
        val root = runCatching { JSONObject(manifest) }.getOrNull() ?: return false
        if (root.optString("appVersion") != appVersion) return false
        val files = root.optJSONObject("files") ?: return false
        val expectedFiles = files.keys().asSequence().associateWith { files.optString(it) }
        if (expectedFiles.any { (path, digest) -> path.startsWith("/") || path.split('/').contains("..") || '\\' in path || !digest.matches(Regex("[a-f0-9]{64}")) }) return false
        return expectedFiles.isNotEmpty() && expectedFiles == actualFiles
    }
}

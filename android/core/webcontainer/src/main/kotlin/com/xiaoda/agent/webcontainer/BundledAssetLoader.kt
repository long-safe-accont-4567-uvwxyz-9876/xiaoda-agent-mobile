package com.xiaoda.agent.webcontainer

import android.content.Context
import android.content.res.AssetManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import androidx.webkit.WebViewAssetLoader
import java.security.MessageDigest
import org.json.JSONObject

class BundledAssetLoader(private val context: Context) {
    private val loader = WebViewAssetLoader.Builder()
        .addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()

    fun intercept(request: WebResourceRequest): WebResourceResponse? = loader.shouldInterceptRequest(request.url)

    fun isTrusted(appVersion: String): Boolean {
        val manifest = runCatching {
            context.assets.open("asset-manifest.json").bufferedReader().use { it.readText() }
        }.getOrNull() ?: return false
        val root = runCatching { JSONObject(manifest) }.getOrNull() ?: return false
        if (root.optString("appVersion") != appVersion) return false
        val files = root.optJSONObject("files") ?: return false
        val expectedPaths = files.keys().asSequence().toList()
        if (expectedPaths.isEmpty()) return false

        val actualFiles = mutableMapOf<String, String>()
        for (path in expectedPaths) {
            val expectedDigest = files.optString(path)
            if (
                path.startsWith("/") ||
                path.split('/').contains("..") ||
                '\\' in path ||
                !expectedDigest.matches(Regex("[a-f0-9]{64}"))
            ) return false
            val digest = runCatching {
                context.assets.open(path, AssetManager.ACCESS_STREAMING).use { input ->
                    MessageDigest.getInstance("SHA-256").digest(input.readBytes())
                }
            }.getOrNull() ?: return false
            actualFiles[path] = digest.joinToString("") { "%02x".format(it) }
        }
        return AssetManifestVerifier().isValid(manifest, appVersion, actualFiles)
    }

    companion object {
        const val ORIGIN = "https://appassets.androidplatform.net"
        const val START_URL = "$ORIGIN/index.html"
    }
}

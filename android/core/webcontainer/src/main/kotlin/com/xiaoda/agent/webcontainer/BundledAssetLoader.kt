package com.xiaoda.agent.webcontainer

import android.content.Context
import android.content.res.AssetManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import androidx.webkit.WebViewAssetLoader
import java.security.MessageDigest

class BundledAssetLoader(private val context: Context) {
    private val loader = WebViewAssetLoader.Builder()
        .addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(context))
        .build()

    fun intercept(request: WebResourceRequest): WebResourceResponse? = loader.shouldInterceptRequest(request.url)

    fun isTrusted(appVersion: String): Boolean {
        val manifest = runCatching { context.assets.open("asset-manifest.json").bufferedReader().use { it.readText() } }.getOrNull() ?: return false
        val actualFiles = mutableMapOf<String, String>()
        fun collect(path: String) {
            val children = context.assets.list(path).orEmpty()
            if (children.isNotEmpty()) {
                children.forEach { child -> collect(if (path.isEmpty()) child else "$path/$child") }
                return
            }
            if (path == "asset-manifest.json") return
            val digest = runCatching {
                context.assets.open(path, AssetManager.ACCESS_STREAMING).use { input -> MessageDigest.getInstance("SHA-256").digest(input.readBytes()) }
            }.getOrNull() ?: return
            actualFiles[path] = digest.joinToString("") { "%02x".format(it) }
        }
        return runCatching { collect(""); AssetManifestVerifier().isValid(manifest, appVersion, actualFiles) }.getOrDefault(false)
    }

    companion object {
        const val ORIGIN = "https://appassets.androidplatform.net"
        const val START_URL = "$ORIGIN/index.html"
    }
}

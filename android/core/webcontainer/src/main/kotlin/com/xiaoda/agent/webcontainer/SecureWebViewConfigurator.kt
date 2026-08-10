package com.xiaoda.agent.webcontainer

import android.webkit.WebSettings
import android.webkit.WebView

object SecureWebViewConfigurator {
    fun configure(webView: WebView, debuggingEnabled: Boolean) {
        WebView.setWebContentsDebuggingEnabled(debuggingEnabled)
        webView.settings.apply {
            javaScriptEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            domStorageEnabled = false
            databaseEnabled = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
        }
        webView.clearCache(true)
    }
}

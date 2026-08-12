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
            // The original Vue UI persists language and display preferences here.
            // Authentication tokens still stay in Android Keystore via the native bridge.
            domStorageEnabled = true
            databaseEnabled = false
            // The trusted HTTPS appassets origin talks only to the fixed loopback
            // backend. Network Security Config rejects cleartext for every other host.
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
        }
        webView.clearCache(true)
    }
}

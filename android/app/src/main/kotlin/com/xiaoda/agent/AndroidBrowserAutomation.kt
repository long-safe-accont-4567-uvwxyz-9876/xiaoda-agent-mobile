package com.xiaoda.agent

import android.graphics.Bitmap
import android.graphics.Canvas
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.io.File
import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.net.URI
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Process-local browser automation backed by a dedicated Android WebView.
 *
 * The automation WebView is separate from Xiaoda's UI WebView, so navigation and
 * page scripts never replace the app interface. Python calls this object through
 * Chaquopy; every WebView operation is marshalled onto Android's main thread.
 */
object AndroidBrowserAutomation {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val webViewRef = AtomicReference<WebView?>()
    private val filesDirRef = AtomicReference<File?>()
    private val pageLatchRef = AtomicReference<CountDownLatch?>()
    private val pageErrorRef = AtomicReference<String?>(null)

    @JvmStatic
    fun initialize(webView: WebView, filesDir: File) {
        webViewRef.set(webView)
        filesDirRef.set(filesDir)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = false
            allowFileAccess = false
            allowContentAccess = false
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
            userAgentString = "$userAgentString XiaodaAndroidLocalBrowser/${BuildConfig.VERSION_NAME}"
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url.toString()
                if (!isAllowedUrl(target)) {
                    pageErrorRef.set("Blocked navigation target: $target")
                    pageLatchRef.getAndSet(null)?.countDown()
                    return true
                }
                return false
            }

            override fun onPageFinished(view: WebView, url: String) {
                pageLatchRef.getAndSet(null)?.countDown()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: android.webkit.WebResourceError) {
                if (request.isForMainFrame) {
                    pageErrorRef.set(error.description?.toString() ?: "WebView navigation failed")
                    pageLatchRef.getAndSet(null)?.countDown()
                }
            }
        }
    }

    @JvmStatic
    fun shutdown() {
        val view = webViewRef.getAndSet(null) ?: return
        pageLatchRef.getAndSet(null)?.countDown()
        mainHandler.post {
            view.stopLoading()
            view.loadUrl("about:blank")
            view.clearHistory()
            view.webViewClient = WebViewClient()
        }
    }

    @JvmStatic
    fun execute(requestJson: String): String {
        val request = runCatching { JSONObject(requestJson) }.getOrElse {
            return failure("Invalid browser automation request: ${it.message}")
        }
        val action = request.optString("action").lowercase()
        val timeoutMs = request.optLong("timeout_ms", 30_000L).coerceIn(1_000L, 120_000L)
        return try {
            when (action) {
                "open" -> open(request.optString("url"), timeoutMs)
                "read" -> read(request.optString("selector"), request.optInt("max_chars", 20_000), timeoutMs)
                "click" -> javascriptAction(clickScript(request.optString("selector")), timeoutMs)
                "type" -> javascriptAction(typeScript(request.optString("selector"), request.optString("value")), timeoutMs)
                "evaluate" -> javascriptAction(evaluateScript(request.optString("script")), timeoutMs)
                "scroll" -> javascriptAction("window.scrollBy(0, ${request.optInt("delta_y", 600)}); ({x:window.scrollX,y:window.scrollY});", timeoutMs)
                "back" -> navigationAction(timeoutMs) { if (it.canGoBack()) it.goBack() else it.loadUrl("about:blank") }
                "reload" -> navigationAction(timeoutMs) { it.reload() }
                "screenshot" -> screenshot(request.optString("name"), timeoutMs)
                "state" -> state(timeoutMs)
                "close" -> close(timeoutMs)
                else -> failure("Unsupported browser action: $action")
            }
        } catch (error: Throwable) {
            failure("${error::class.java.simpleName}: ${error.message}")
        }
    }

    private fun open(url: String, timeoutMs: Long): String {
        if (!isAllowedUrl(url)) return failure("Only public http/https URLs are allowed")
        val latch = CountDownLatch(1)
        pageErrorRef.set(null)
        pageLatchRef.set(latch)
        val view = requireView()
        mainHandler.post { view.loadUrl(url) }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
            pageLatchRef.compareAndSet(latch, null)
            return failure("Browser navigation timed out")
        }
        pageErrorRef.getAndSet(null)?.let { return failure(it) }
        return state(timeoutMs)
    }

    private fun navigationAction(timeoutMs: Long, action: (WebView) -> Unit): String {
        val latch = CountDownLatch(1)
        pageErrorRef.set(null)
        pageLatchRef.set(latch)
        val view = requireView()
        mainHandler.post { action(view) }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) {
            pageLatchRef.compareAndSet(latch, null)
            return failure("Browser navigation timed out")
        }
        pageErrorRef.getAndSet(null)?.let { return failure(it) }
        return state(timeoutMs)
    }

    private fun read(selector: String, maxChars: Int, timeoutMs: Long): String {
        val safeLimit = maxChars.coerceIn(1, 200_000)
        val selectorJson = JSONObject.quote(selector)
        val script = """
            (() => {
              const selector = $selectorJson;
              const node = selector ? document.querySelector(selector) : document.body;
              if (!node) return {found:false,url:location.href,title:document.title,text:""};
              const text = (node.innerText || node.textContent || "").slice(0, $safeLimit);
              return {found:true,url:location.href,title:document.title,text};
            })();
        """.trimIndent()
        return javascriptAction(script, timeoutMs)
    }

    private fun state(timeoutMs: Long): String = javascriptAction(
        "({url:location.href,title:document.title,readyState:document.readyState,canGoBack:history.length>1});",
        timeoutMs,
    )

    private fun close(timeoutMs: Long): String {
        val result = javascriptAction("document.documentElement.innerHTML=''; true;", timeoutMs)
        mainHandler.post {
            webViewRef.get()?.apply {
                stopLoading()
                loadUrl("about:blank")
                clearHistory()
            }
        }
        return result
    }

    private fun javascriptAction(script: String, timeoutMs: Long): String {
        if (script.isBlank()) return failure("JavaScript is empty")
        val latch = CountDownLatch(1)
        val result = AtomicReference<String?>(null)
        mainHandler.post {
            val view = webViewRef.get()
            if (view == null) {
                result.set(null)
                latch.countDown()
                return@post
            }
            view.evaluateJavascript(script) { value ->
                result.set(value)
                latch.countDown()
            }
        }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) return failure("Browser JavaScript timed out")
        val raw = result.get() ?: return failure("Browser WebView is not initialized")
        val parsed = parseJavascriptResult(raw)
        return success(JSONObject().put("value", parsed))
    }

    private fun screenshot(name: String, timeoutMs: Long): String {
        val latch = CountDownLatch(1)
        val result = AtomicReference<String?>(null)
        val error = AtomicReference<String?>(null)
        mainHandler.post {
            try {
                val view = requireView()
                val width = view.width.coerceAtLeast(1)
                val height = view.height.coerceAtLeast(1)
                val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
                view.draw(Canvas(bitmap))
                val base = filesDirRef.get() ?: error("Files directory unavailable")
                val outputDir = base.resolve("xiaoda/.ai-agent/data/media/browser")
                outputDir.mkdirs()
                val safeName = name.ifBlank { "browser-${System.currentTimeMillis()}" }
                    .replace(Regex("[^A-Za-z0-9._-]"), "_")
                    .take(80)
                val output = outputDir.resolve(if (safeName.endsWith(".png")) safeName else "$safeName.png")
                output.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                bitmap.recycle()
                result.set(output.absolutePath)
            } catch (throwable: Throwable) {
                error.set(throwable.message ?: throwable::class.java.simpleName)
            } finally {
                latch.countDown()
            }
        }
        if (!latch.await(timeoutMs, TimeUnit.MILLISECONDS)) return failure("Browser screenshot timed out")
        error.get()?.let { return failure(it) }
        return success(JSONObject().put("path", result.get()).put("mime_type", "image/png"))
    }

    private fun clickScript(selector: String): String {
        if (selector.isBlank()) return "({ok:false,error:'selector is required'});"
        val quoted = JSONObject.quote(selector)
        return """
            (() => {
              const node = document.querySelector($quoted);
              if (!node) return {ok:false,error:'element not found'};
              node.scrollIntoView({block:'center',inline:'center'});
              node.click();
              return {ok:true,tag:node.tagName,text:(node.innerText||node.value||'').slice(0,500)};
            })();
        """.trimIndent()
    }

    private fun typeScript(selector: String, value: String): String {
        if (selector.isBlank()) return "({ok:false,error:'selector is required'});"
        val quotedSelector = JSONObject.quote(selector)
        val quotedValue = JSONObject.quote(value)
        return """
            (() => {
              const node = document.querySelector($quotedSelector);
              if (!node) return {ok:false,error:'element not found'};
              node.focus();
              node.value = $quotedValue;
              node.dispatchEvent(new Event('input',{bubbles:true}));
              node.dispatchEvent(new Event('change',{bubbles:true}));
              return {ok:true,value:node.value};
            })();
        """.trimIndent()
    }

    private fun evaluateScript(script: String): String =
        "(() => { const value = (() => { $script })(); return value === undefined ? null : value; })();"

    private fun requireView(): WebView = webViewRef.get() ?: error("Browser WebView is not initialized")

    private fun isAllowedUrl(value: String): Boolean {
        val uri = runCatching { URI(value) }.getOrNull() ?: return false
        if (uri.scheme !in setOf("http", "https") || uri.userInfo != null || uri.host.isNullOrBlank()) return false
        val addresses = runCatching { InetAddress.getAllByName(uri.host) }.getOrNull() ?: return false
        return addresses.all { address ->
            val privateAddress = address.isAnyLocalAddress || address.isLoopbackAddress || address.isLinkLocalAddress ||
                address.isSiteLocalAddress || isCarrierGradeNat(address) || isUniqueLocalIpv6(address)
            !privateAddress || BuildConfig.DEBUG && address.isLoopbackAddress
        }
    }

    private fun isCarrierGradeNat(address: InetAddress): Boolean {
        if (address !is Inet4Address) return false
        val bytes = address.address
        val first = bytes[0].toInt() and 0xff
        val second = bytes[1].toInt() and 0xff
        return first == 100 && second in 64..127
    }

    private fun isUniqueLocalIpv6(address: InetAddress): Boolean {
        if (address !is Inet6Address) return false
        return (address.address[0].toInt() and 0xfe) == 0xfc
    }

    private fun parseJavascriptResult(raw: String): Any {
        if (raw == "null" || raw == "undefined") return JSONObject.NULL
        return runCatching { JSONObject("{\"value\":$raw}").get("value") }
            .getOrElse { raw.removeSurrounding("\"") }
    }

    private fun success(data: JSONObject): String = JSONObject().put("ok", true).put("data", data).toString()
    private fun failure(message: String): String = JSONObject().put("ok", false).put("error", message).toString()
}

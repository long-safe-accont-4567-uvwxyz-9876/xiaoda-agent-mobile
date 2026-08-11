package com.xiaoda.agent

import android.Manifest
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Base64
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.xiaoda.agent.bridge.BridgeContract
import com.xiaoda.agent.bridge.BridgeRequestValidator
import com.xiaoda.agent.bridge.SelectedFileInspection
import com.xiaoda.agent.bridge.SelectedFileReader
import com.xiaoda.agent.local.LocalAiController
import com.xiaoda.agent.local.LocalStateStore
import com.xiaoda.agent.local.ProviderConfigValidator
import com.xiaoda.agent.security.KeystoreSecretStore
import com.xiaoda.agent.webcontainer.BundledAssetLoader
import com.xiaoda.agent.webcontainer.SecureWebViewConfigurator
import com.xiaoda.agent.webcontainer.TrustedNavigationPolicy
import org.json.JSONObject
import java.util.UUID

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var connectivityManager: ConnectivityManager
    private lateinit var lifecyclePolicy: ConnectionLifecyclePolicy
    private lateinit var localAi: LocalAiController
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var networkCallbackGeneration: Long? = null
    private val networkCallbackGenerations = NetworkCallbackGeneration()
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingFileRequest: PendingFileRequest? = null
    private val filePicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val request = pendingFileRequest
        val inspection = uri?.let { selectedUri -> request?.let { selectedFileInspection(selectedUri, it) } }
        val acceptedUri = uri?.takeIf { inspection != null }
        request?.fileCallback?.onReceiveValue(acceptedUri?.let { arrayOf(it) })
        fileCallback = null
        val reply = when {
            request == null -> null
            inspection == null -> bridgeError(request.id, "invalid_selected_file")
            request.localAttachment -> bridgeReply(
                request.id,
                localAi.storeAttachment(uri?.let(::selectedFileName) ?: "attachment", inspection.mimeType, inspection.bytes),
            )
            else -> bridgeReply(request.id, fileResultObject(inspection))
        }
        request?.replyProxy?.postMessage(reply?.toString().orEmpty())
        pendingFileRequest = null
    }
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.web_view)
        SecureWebViewConfigurator.configure(webView, BuildConfig.WEBVIEW_DEBUGGING)
        lifecyclePolicy = ConnectionLifecyclePolicy(ConnectionLifecycleState(false, false))
        localAi = LocalAiController(
            LocalStateStore(applicationContext, KeystoreSecretStore(applicationContext)),
            validator = ProviderConfigValidator(BuildConfig.DEBUG),
        )
        configureWebContainer()
        configureBridge()
        configureBackNavigation()
        connectivityManager = getSystemService(ConnectivityManager::class.java)
        refreshNetworkState()
        val restored = savedInstanceState != null && webView.restoreState(savedInstanceState) != null
        val deepLinkHandled = handleDeepLink(intent)
        requestNotificationPermission()
        if (!restored && !deepLinkHandled) {
            if (BundledAssetLoader(this).isTrusted(BuildConfig.WEB_ASSET_VERSION)) webView.loadUrl(BundledAssetLoader.START_URL) else showDiagnosticError()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleDeepLink(intent)
    }

    override fun onStart() {
        super.onStart()
        registerNetworkCallback()
        lifecyclePolicy.onForegroundChanged(true)?.let(::notifyConnectionPolicy)
    }

    override fun onStop() {
        lifecyclePolicy.onForegroundChanged(false)?.let(::notifyConnectionPolicy)
        unregisterNetworkCallback()
        super.onStop()
    }

    override fun onDestroy() {
        unregisterNetworkCallback()
        fileCallback?.onReceiveValue(null)
        fileCallback = null
        pendingFileRequest?.let { it.replyProxy?.postMessage(bridgeError(it.id, "activity_destroyed").toString()) }
        pendingFileRequest = null
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) WebViewCompat.removeWebMessageListener(webView, "XiaodaNative")
        webView.stopLoading()
        webView.webChromeClient = null
        webView.webViewClient = WebViewClient()
        webView.removeAllViews()
        webView.destroy()
        if (::localAi.isInitialized) localAi.close()
        super.onDestroy()
    }

    private fun configureWebContainer() {
        val loader = BundledAssetLoader(this)
        val navigation = TrustedNavigationPolicy(BundledAssetLoader.ORIGIN)
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? = loader.intercept(request)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (navigation.isBundledResource(url)) return false
                if (navigation.isExternalLink(url)) startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: android.webkit.WebResourceError) {
                if (request.isForMainFrame) showDiagnosticError()
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (navigation.isBundledResource(url)) notifyConnectionPolicy(lifecyclePolicy.shouldConnect)
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                val accept = params.acceptTypes.firstOrNull { it.isNotBlank() } ?: "application/pdf"
                pendingFileRequest = PendingFileRequest("", accept, BuildConfig.UPLOAD_MAX_BYTES, null, callback)
                filePicker.launch(arrayOf(accept))
                return true
            }
        }
    }

    private fun configureBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when (BackNavigationPolicy.decide(webView.canGoBack())) {
                    BackAction.GO_BACK -> webView.goBack()
                    BackAction.FINISH -> finish()
                }
            }
        })
    }

    private fun configureBridge() {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) return
        val validator = BridgeRequestValidator(BundledAssetLoader.ORIGIN, BuildConfig.UPLOAD_MAX_BYTES)
        WebViewCompat.addWebMessageListener(webView, "XiaodaNative", setOf(BundledAssetLoader.ORIGIN), object : WebViewCompat.WebMessageListener {
            override fun onPostMessage(view: WebView, message: WebMessageCompat, sourceOrigin: Uri, isMainFrame: Boolean, replyProxy: JavaScriptReplyProxy) {
                val request = runCatching { JSONObject(message.data ?: return) }.getOrNull() ?: return
                val method = request.optString("method")
                if (!isMainFrame || !validator.isMethodAllowed(sourceOrigin.toString(), method)) return
                val args = request.optJSONObject("args") ?: JSONObject()
                val result = when (method) {
                    "getInsets" -> JSONObject().put("top", 0).put("right", 0).put("bottom", 0).put("left", 0)
                    "getNetworkStatus" -> JSONObject().put("connected", lifecyclePolicy.shouldConnect)
                    "shareText" -> shareText(args.optString("text"), validator)
                    "pickFile" -> pickFile(request.optString("id"), args.optString("accept"), args.optLong("maxBytes"), validator, replyProxy)
                    "local.bootstrap" -> localAi.bootstrap()
                    "local.saveProvider" -> localAi.saveProvider(args)
                    "local.deleteProvider" -> localAi.deleteProvider(args)
                    "local.saveAgent" -> localAi.saveAgent(args)
                    "local.listSessions" -> localAi.sessions()
                    "local.createSession" -> localAi.createSession()
                    "local.getMessages" -> localAi.messages(args)
                    "local.deleteSession" -> localAi.deleteSession(args)
                    "local.abort" -> localAi.abort(args)
                    "local.pickAttachment" -> pickAttachment(request.optString("id"), args.optString("accept", "*/*"), args.optLong("maxBytes"), validator, replyProxy)
                    "local.listModels" -> {
                        val id = request.optString("id")
                        localAi.listModels(args) { asyncResult -> postBridgeResult(id, asyncResult, replyProxy) }
                        null
                    }
                    "local.chat" -> localAi.startChat(args) { event -> webView.post { replyProxy.postMessage(event.toString()) } }
                    else -> JSONObject().put("error", "unsupported_method")
                }
                if (result != null) {
                    val id = request.optString("id")
                    val error = result.optString("error")
                    replyProxy.postMessage((if (error.isNotEmpty()) bridgeError(id, error) else bridgeReply(id, result)).toString())
                }
            }
        })
    }


    private fun bridgeReply(id: String, result: Any): JSONObject = JSONObject().put("id", id).put("result", result)

    private fun bridgeError(id: String, error: String): JSONObject = JSONObject().put("id", id).put("error", error)

    private fun postBridgeResult(id: String, result: JSONObject, replyProxy: JavaScriptReplyProxy) {
        webView.post {
            val error = result.optString("error")
            replyProxy.postMessage((if (error.isNotEmpty()) bridgeError(id, error) else bridgeReply(id, result)).toString())
        }
    }

    private fun shareText(text: String, validator: BridgeRequestValidator): JSONObject {
        if (!validator.isShareTextValid(text)) return JSONObject().put("error", "invalid_share_text")
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }, null))
        return JSONObject().put("accepted", true)
    }

    private fun pickFile(id: String, accept: String, maxBytes: Long, validator: BridgeRequestValidator, replyProxy: JavaScriptReplyProxy): JSONObject? {
        if (!validator.isFileRequestValid(accept, maxBytes)) return JSONObject().put("error", "invalid_file_request")
        if (pendingFileRequest != null) return JSONObject().put("error", "file_request_in_progress")
        pendingFileRequest = PendingFileRequest(id, accept, maxBytes, replyProxy, null)
        filePicker.launch(arrayOf(accept))
        return null
    }

    private fun pickAttachment(id: String, accept: String, maxBytes: Long, validator: BridgeRequestValidator, replyProxy: JavaScriptReplyProxy): JSONObject? {
        if (!validator.isFileRequestValid(accept, maxBytes)) return JSONObject().put("error", "invalid_file_request")
        if (pendingFileRequest != null) return JSONObject().put("error", "file_request_in_progress")
        pendingFileRequest = PendingFileRequest(id, accept, maxBytes, replyProxy, null, localAttachment = true)
        filePicker.launch(arrayOf(accept))
        return null
    }

    private fun selectedFileInspection(uri: Uri, request: PendingFileRequest): SelectedFileInspection? {
        val reportedSize = runCatching {
            contentResolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getLong(0) else null
            }
        }.getOrNull()
        val input = runCatching { contentResolver.openInputStream(uri) }.getOrNull() ?: return null
        return SelectedFileReader(BridgeRequestValidator(BundledAssetLoader.ORIGIN, BuildConfig.UPLOAD_MAX_BYTES)).read(
            uri.scheme,
            contentResolver.getType(uri),
            input,
            request.accept,
            request.maxBytes,
            reportedSize,
        )
    }

    private fun selectedFileName(uri: Uri): String = runCatching {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst() && !cursor.isNull(0)) cursor.getString(0) else null
        }
    }.getOrNull()?.takeIf(String::isNotBlank) ?: "attachment"

    private fun fileResultObject(file: SelectedFileInspection): JSONObject = JSONObject()
        .put("dataBase64", Base64.encodeToString(file.bytes, Base64.NO_WRAP))
        .put("mimeType", file.mimeType)
        .put("sizeBytes", file.sizeBytes)
        .put("name", "upload")

    private fun refreshNetworkState() {
        val activeNetwork = connectivityManager.activeNetwork
        val capabilities = connectivityManager.getNetworkCapabilities(activeNetwork)
        lifecyclePolicy.onNetworkChanged(capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true)?.let(::notifyConnectionPolicy)
    }

    private fun registerNetworkCallback() {
        if (networkCallback != null) return
        refreshNetworkState()
        val generation = networkCallbackGenerations.register()
        networkCallbackGeneration = generation
        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { if (networkCallbackGenerations.isCurrent(generation)) refreshNetworkState() }
            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) { if (networkCallbackGenerations.isCurrent(generation)) refreshNetworkState() }
            override fun onLost(network: Network) { if (networkCallbackGenerations.isCurrent(generation)) refreshNetworkState() }
        }.also(connectivityManager::registerDefaultNetworkCallback)
    }

    private fun unregisterNetworkCallback() {
        networkCallbackGeneration?.let(networkCallbackGenerations::unregister)
        networkCallbackGeneration = null
        networkCallback?.let { runCatching { connectivityManager.unregisterNetworkCallback(it) } }
        networkCallback = null
    }

    private fun notifyConnectionPolicy(shouldConnect: Boolean) {
        if (::webView.isInitialized) webView.post {
            webView.evaluateJavascript("window.dispatchEvent(new CustomEvent('xiaoda:connection-policy',{detail:{connect:$shouldConnect}}))", null)
        }
    }

    private fun handleDeepLink(intent: Intent): Boolean {
        val route = NotificationNavigationPolicy.route(
            intent.action,
            intent.getStringExtra(NotificationNavigationPolicy.EXTRA_ROUTE),
        ) ?: intent.dataString?.let(DeepLinkPolicy::route) ?: return false
        if (!::webView.isInitialized) return false
        webView.loadUrl("${BundledAssetLoader.ORIGIN}/index.html#${Uri.encode(route, "/")}")
        return true
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun showDiagnosticError() {
        val diagnosticId = UUID.randomUUID().toString()
        val message = getString(R.string.web_error, BuildConfig.VERSION_NAME, diagnosticId)
        webView.loadDataWithBaseURL(BundledAssetLoader.ORIGIN, message, "text/plain", "UTF-8", null)
    }

    private data class PendingFileRequest(
        val id: String,
        val accept: String,
        val maxBytes: Long,
        val replyProxy: JavaScriptReplyProxy?,
        val fileCallback: ValueCallback<Array<Uri>>?,
        val localAttachment: Boolean = false,
    )

}

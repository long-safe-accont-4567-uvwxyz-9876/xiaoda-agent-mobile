package com.xiaoda.agent

import android.content.Context
import android.content.Intent
import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.chaquo.python.Python
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class MainActivityLocalBackendTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun activityAlwaysUsesTheEmbeddedLoopbackBackend() {
        val intent = Intent(context, MainActivity::class.java)

        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            scenario.onActivity { activity ->
                val method = MainActivity::class.java.getDeclaredMethod("localEndpoint").apply { isAccessible = true }
                assertEquals("http://127.0.0.1:8765", method.invoke(activity))
            }
        }
    }

    @Test
    fun embeddedPythonStartsTheOriginalFastApiRouteSet() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)

        val ping = requestJson("GET", "${LocalBackendRuntime.endpoint}/api/v1/ping")
        assertTrue(ping.getBoolean("ok"))

        val paths = requestJson("GET", "${LocalBackendRuntime.endpoint}/openapi.json").getJSONObject("paths")
        listOf(
            "/api/v1/auth/login",
            "/api/v1/sessions",
            "/api/v1/agents",
            "/api/v1/models/providers",
            "/api/v1/tools",
            "/api/v1/schedule/config",
            "/api/v1/plugins",
            "/api/v1/workflows",
            "/api/v1/workspace",
        ).forEach { path -> assertTrue("Missing original route: $path", paths.has(path)) }

        val privateRoot = context.filesDir.resolve("xiaoda/.ai-agent")
        listOf(
            "config/agent.json5",
            "config/security_patterns.yaml",
            "config/provider_metadata.json",
            "config/agents/xiaoda.json",
            "config/agents/xiaoda_personality.md",
            "config/workspace/SOUL.md",
            "config/workspace/TOOLS.md",
        ).forEach { relative ->
            assertTrue("Missing seeded mobile resource: $relative", privateRoot.resolve(relative).isFile)
        }

        val login = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/auth/login",
            JSONObject().put("password", ""),
        )
        assertTrue(login.getBoolean("ok"))
        val token = login.getJSONObject("data").getString("token")
        assertTrue(token.isNotBlank())

        val providerId = "android_local_${System.currentTimeMillis()}"
        val apiKey = "sk-android-local-secret-123456"
        val modelId = "xiaoda-mobile-model"
        val create = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
            JSONObject()
                .put("id", providerId)
                .put("label", "Android 鏈湴娴嬭瘯")
                .put("format", "openai")
                .put("base_url", "https://api.example.com/v1")
                .put("api_key", apiKey)
                .put("default_model", modelId)
                .put("manual_models", org.json.JSONArray().put(modelId))
                .put("enabled", true),
            token,
        )
        assertTrue(create.getBoolean("ok"))
        assertEquals(providerId, create.getJSONObject("data").getString("id"))

        val credentialFile = privateRoot.resolve("credentials/provider_${providerId}.key")
        assertTrue("Provider credential was not persisted locally", credentialFile.isFile)
        val encryptedCredential = credentialFile.readText()
        assertTrue("Provider credential must use the encrypted vault format", encryptedCredential.startsWith("enc:v1:"))
        assertFalse("Provider credential leaked as plaintext", encryptedCredential.contains(apiKey))

        val providers = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
            token = token,
        ).getJSONArray("data")
        val persistedProvider = (0 until providers.length())
            .map { providers.getJSONObject(it) }
            .firstOrNull { it.getString("id") == providerId }
            ?: throw AssertionError("Created provider is missing from the local provider registry")
        assertTrue(persistedProvider.getBoolean("has_key"))
        assertEquals(modelId, persistedProvider.getString("default_model"))

        val routeUpdate = requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/models/routes/chat",
            JSONObject().put("provider", providerId).put("model", modelId),
            token,
        )
        assertTrue(routeUpdate.getBoolean("ok"))

        val chatModel = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/models/chat-model",
            token = token,
        ).getJSONObject("data")
        assertEquals(providerId, chatModel.getString("provider"))
        assertEquals(modelId, chatModel.getString("model_id"))
        assertTrue(
            "Provider and route settings were not persisted in app-private storage",
            privateRoot.resolve("config/webui_overrides.json").isFile,
        )
    }


    @Test
    fun sessionsAndUploadsRemainInAppPrivateStorage() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        val createdSession = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/sessions",
            JSONObject(),
            token,
        ).getJSONObject("data").getString("session_id")
        assertTrue(createdSession.startsWith("web_"))
        val emptyMessages = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/sessions/$createdSession/messages",
            token = token,
        ).getJSONArray("data")
        assertEquals(0, emptyMessages.length())
        val deletedSession = requestJson(
            "DELETE",
            "${LocalBackendRuntime.endpoint}/api/v1/sessions/$createdSession",
            token = token,
        ).getJSONObject("data").getString("deleted")
        assertEquals(createdSession, deletedSession)

        val documentBytes = "# 鎵嬫満鏈湴鏂囨。\n杩欎唤鍐呭蹇呴』淇濆瓨鍦ㄥ簲鐢ㄧ鏈夌洰褰曘€俓n".toByteArray(Charsets.UTF_8)
        val uploadedDocument = requestMultipart(
            "${LocalBackendRuntime.endpoint}/api/v1/chat/upload-doc",
            "mobile-local.md",
            "text/markdown",
            documentBytes,
            token,
        ).getJSONObject("data")
        assertEquals(".md", uploadedDocument.getString("ext"))
        val documentFile = java.io.File(uploadedDocument.getString("path"))
        assertTrue("Uploaded document is missing", documentFile.isFile)
        assertTrue(
            "Uploaded document escaped app-private storage: ${documentFile.absolutePath}",
            documentFile.canonicalPath.startsWith(context.filesDir.canonicalPath + java.io.File.separator),
        )
        assertTrue(documentBytes.contentEquals(documentFile.readBytes()))

        val pngBytes = android.util.Base64.decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            android.util.Base64.DEFAULT,
        )
        val uploadedImage = requestMultipart(
            "${LocalBackendRuntime.endpoint}/api/v1/chat/upload-image",
            "mobile-local.png",
            "image/png",
            pngBytes,
            token,
        ).getJSONObject("data")
        val imageUrl = uploadedImage.getString("url")
        assertTrue(imageUrl.startsWith("/media/upload/"))
        val imageFile = context.filesDir.resolve("xiaoda/.ai-agent/data/media/upload/${java.io.File(imageUrl).name}")
        assertTrue("Uploaded image is missing from app-private media storage", imageFile.isFile)
        assertTrue(pngBytes.contentEquals(imageFile.readBytes()))
    }


    @Test
    fun localProviderChatPersistsSessionHistory() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        FakeOpenAiServer().use { provider ->
            setPythonEnvironment("PROVIDER_ALLOW_HOSTS", "127.0.0.1")
            setPythonEnvironment("PROVIDER_ALLOWED_HTTP_PORTS", provider.port.toString())

            val providerId = "android_chat_${System.currentTimeMillis()}"
            val modelId = "xiaoda-android-e2e"
            requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
                JSONObject()
                    .put("id", providerId)
                    .put("label", "Android 本地对话测试")
                    .put("format", "openai")
                    .put("base_url", "http://127.0.0.1:${provider.port}/v1")
                    .put("api_key", "local-test-key")
                    .put("default_model", modelId)
                    .put("manual_models", org.json.JSONArray().put(modelId))
                    .put("enabled", true),
                token,
            )
            requestJson(
                "PUT",
                "${LocalBackendRuntime.endpoint}/api/v1/models/routes/chat",
                JSONObject().put("provider", providerId).put("model", modelId),
                token,
            )

            val sessionId = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/sessions",
                JSONObject(),
                token,
            ).getJSONObject("data").getString("session_id")
            val userText = "请验证手机本地 Agent、模型路由和会话落库链路"
            val chatData = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/chat",
                JSONObject()
                    .put("session_id", sessionId)
                    .put("agent", "xiaoda")
                    .put("text", userText),
                token,
            ).getJSONObject("data")
            val reply = chatData.optString("reply", chatData.optString("text"))
            assertTrue("The local OpenAI-compatible provider was never called", provider.requestCount.get() > 0)
            assertTrue("Unexpected local Agent reply after ${provider.requestCount.get()} provider calls: $reply", reply.contains(FakeOpenAiServer.REPLY_MARKER))

            var messages = org.json.JSONArray()
            for (attempt in 0 until 40) {
                messages = requestJson(
                    "GET",
                    "${LocalBackendRuntime.endpoint}/api/v1/sessions/$sessionId/messages",
                    token = token,
                ).getJSONArray("data")
                if (messages.length() >= 2) break
                Thread.sleep(250)
            }
            assertTrue("Conversation was not persisted to the local database", messages.length() >= 2)
            assertEquals("user", messages.getJSONObject(0).getString("role"))
            assertEquals(userText, messages.getJSONObject(0).getString("content"))
            assertEquals("assistant", messages.getJSONObject(1).getString("role"))
            assertTrue(messages.getJSONObject(1).getString("content").contains(FakeOpenAiServer.REPLY_MARKER))

            val sessions = requestJson(
                "GET",
                "${LocalBackendRuntime.endpoint}/api/v1/sessions",
                token = token,
            ).getJSONArray("data")
            assertTrue(
                "Persisted conversation is missing from session history",
                (0 until sessions.length()).any { sessions.getJSONObject(it).getString("session_id") == sessionId },
            )
            assertTrue(
                "The Android database is not in the durable app-private data root",
                context.filesDir.resolve("xiaoda/.ai-agent/data/db/agent.db").isFile,
            )
        }
    }



    @Test
    fun websocketChatRunsThroughTheEmbeddedAgent() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        FakeOpenAiServer().use { provider ->
            setPythonEnvironment("PROVIDER_ALLOW_HOSTS", "127.0.0.1")
            setPythonEnvironment("PROVIDER_ALLOWED_HTTP_PORTS", provider.port.toString())
            val providerId = "android_ws_${System.currentTimeMillis()}"
            val modelId = "xiaoda-android-ws"
            requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
                JSONObject()
                    .put("id", providerId)
                    .put("label", "Android WebSocket ??")
                    .put("format", "openai")
                    .put("base_url", "http://127.0.0.1:${provider.port}/v1")
                    .put("api_key", "local-ws-key")
                    .put("default_model", modelId)
                    .put("manual_models", org.json.JSONArray().put(modelId))
                    .put("enabled", true),
                token,
            )
            requestJson(
                "PUT",
                "${LocalBackendRuntime.endpoint}/api/v1/models/routes/chat",
                JSONObject().put("provider", providerId).put("model", modelId),
                token,
            )
            val sessionId = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/sessions",
                JSONObject(),
                token,
            ).getJSONObject("data").getString("session_id")

            ActivityScenario.launch<MainActivity>(Intent(context, MainActivity::class.java)).use { scenario ->
                var webView: WebView? = null
                scenario.onActivity { activity -> webView = activity.findViewById(R.id.web_view) }
                val view = webView ?: throw AssertionError("Main WebView was not created")
                waitForJavaScript(view, "document.readyState === 'complete'", 60_000)

                val script = """
                    (() => {
                      window.__xiaodaAndroidWsEvents = [];
                      const ws = new WebSocket('ws://127.0.0.1:8765/ws?token=$token');
                      window.__xiaodaAndroidWs = ws;
                      ws.onmessage = (event) => {
                        const message = JSON.parse(event.data);
                        window.__xiaodaAndroidWsEvents.push(message);
                        if (message.type === 'connected') {
                          ws.send(JSON.stringify({
                            type: 'chat',
                            msg_id: 'android-ws-e2e',
                            session_id: '$sessionId',
                            agent: 'xiaoda',
                            text: '请通过手机本地 WebSocket Agent 链路回复'
                          }));
                        }
                      };
                      ws.onerror = () => window.__xiaodaAndroidWsEvents.push({type: 'client_error'});
                      return true;
                    })();
                """.trimIndent()
                evaluateJavaScript(view, script)

                var events = org.json.JSONArray()
                val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(180)
                while (System.nanoTime() < deadline) {
                    val encoded = evaluateJavaScript(
                        view,
                        "JSON.stringify(window.__xiaodaAndroidWsEvents || [])",
                    )
                    val decoded = org.json.JSONTokener(encoded).nextValue() as? String ?: "[]"
                    events = org.json.JSONArray(decoded)
                    if ((0 until events.length()).any {
                            events.getJSONObject(it).optString("type") in setOf("final", "error", "client_error")
                        }
                    ) break
                    Thread.sleep(250)
                }

                val eventTypes = (0 until events.length()).map { events.getJSONObject(it).optString("type") }
                assertTrue("WebSocket never connected: $events", "connected" in eventTypes)
                assertFalse("WebSocket client failed: $events", "client_error" in eventTypes)
                assertTrue("WebSocket chat did not push streamed text: $events", "stream_text" in eventTypes)
                val finalEvent = (0 until events.length())
                    .map { events.getJSONObject(it) }
                    .firstOrNull { it.optString("type") == "final" }
                    ?: throw AssertionError("WebSocket chat produced no final event: $events")
                val reply = finalEvent.optString("reply", finalEvent.optString("text"))
                assertTrue("Unexpected WebSocket Agent reply: $reply", reply.contains(FakeOpenAiServer.REPLY_MARKER))
                assertTrue("WebSocket chat never reached the configured provider", provider.requestCount.get() > 0)
                assertTrue("Streamed tool calls were not reconstructed and executed", provider.toolRequestCount.get() > 0)
            }
        }
    }



    @Test
    fun customAgentUsesTheEncryptedLocalProviderAndPersists() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        FakeOpenAiServer().use { provider ->
            setPythonEnvironment("PROVIDER_ALLOW_HOSTS", "127.0.0.1")
            setPythonEnvironment("PROVIDER_ALLOWED_HTTP_PORTS", provider.port.toString())
            val providerId = "android_agent_${System.currentTimeMillis()}"
            val modelId = "xiaoda-agent-local"
            requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
                JSONObject()
                    .put("id", providerId)
                    .put("label", "Android Agent Provider")
                    .put("format", "openai")
                    .put("base_url", "http://127.0.0.1:${provider.port}/v1")
                    .put("api_key", "local-agent-key")
                    .put("default_model", modelId)
                    .put("manual_models", org.json.JSONArray().put(modelId))
                    .put("enabled", true),
                token,
            )

            val agentName = "mobile_helper_${System.currentTimeMillis()}"
            val personality = "你是完全运行在手机本地的测试 Agent，请用中文回答。"
            val created = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/agents",
                JSONObject()
                    .put("name", agentName)
                    .put("display_name", "本地助手")
                    .put("provider", providerId)
                    .put("model", modelId)
                    .put("route_description", "Android 手机本地测试 Agent")
                    .put("capabilities", org.json.JSONArray().put("local-agent-e2e"))
                    .put("max_turns", 4)
                    .put("effort", "medium")
                    .put("permission_mode", "default")
                    .put("memory_scope", "isolated")
                    .put("personality_text", personality),
                token,
            ).getJSONObject("data")
            assertEquals(providerId, created.getString("provider"))
            assertEquals(modelId, created.getString("model"))
            assertEquals("http://127.0.0.1:${provider.port}/v1", created.getString("base_url"))
            assertTrue(created.getString("api_key_env").startsWith("PROVIDER_"))
            assertFalse(created.getBoolean("degraded"))

            val agentFile = context.filesDir.resolve("xiaoda/.ai-agent/config/agents/$agentName.json")
            assertTrue("Custom Agent config was not persisted", agentFile.isFile)
            val agentConfigText = agentFile.readText()
            assertTrue(agentConfigText.contains(providerId))
            assertFalse("Agent config leaked the provider key", agentConfigText.contains("local-agent-key"))
            val personalityFile = context.filesDir.resolve("xiaoda/.ai-agent/config/agents/${agentName}_personality.md")
            assertTrue("Custom Agent personality was not persisted", personalityFile.isFile)
            assertTrue(personalityFile.readText().contains("手机本地"))

            val beforeCalls = provider.requestCount.get()
            val tested = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/agents/$agentName/test",
                JSONObject(),
                token,
            ).getJSONObject("data")
            assertTrue("Custom Agent test failed: $tested", tested.getBoolean("ok"))
            assertTrue(tested.getString("reply").contains(FakeOpenAiServer.REPLY_MARKER))
            assertTrue("Custom Agent never reached its selected local provider", provider.requestCount.get() > beforeCalls)

            val fetched = requestJson(
                "GET",
                "${LocalBackendRuntime.endpoint}/api/v1/agents/$agentName",
                token = token,
            ).getJSONObject("data")
            assertEquals(providerId, fetched.getString("provider"))
            assertFalse(fetched.getBoolean("degraded"))
        }
    }

    @Test
    fun workflowDagExecutesAndPersistsEntirelyOnDevice() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()
        val workflowId = "android_workflow_${System.currentTimeMillis()}"
        val nodes = org.json.JSONArray()
            .put(
                JSONObject()
                    .put("id", "first")
                    .put("type", "tool")
                    .put("label", "First local calculation")
                    .put("ref", "calculator")
                    .put("params", JSONObject().put("expression", "2+3")),
            )
            .put(
                JSONObject()
                    .put("id", "second")
                    .put("type", "tool")
                    .put("label", "Second local calculation")
                    .put("ref", "calculator")
                    .put("params", JSONObject().put("expression", "5+4")),
            )
        requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/workflows",
            JSONObject()
                .put("id", workflowId)
                .put("name", "Android local workflow")
                .put("description", "Runs through the embedded DAG engine")
                .put("version", "1.0.0")
                .put("enabled", true)
                .put("nodes", nodes)
                .put("edges", org.json.JSONArray().put(org.json.JSONArray().put("first").put("second")))
                .put("trigger", "manual"),
            token,
        )

        val run = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/workflows/$workflowId/run",
            JSONObject().put("input", "phone-local").put("variables", JSONObject()).put("wait", true),
            token,
        ).getJSONObject("data")
        assertEquals("success", run.getString("status"))
        assertEquals(2, run.getJSONArray("nodes").length())
        assertEquals("success", run.getJSONArray("nodes").getJSONObject(0).getString("status"))
        assertEquals("success", run.getJSONArray("nodes").getJSONObject(1).getString("status"))
        assertTrue(run.getJSONObject("outputs").has("first"))
        assertTrue(run.getJSONObject("outputs").has("second"))

        val runId = run.getString("id")
        val runFile = context.filesDir.resolve("xiaoda/.ai-agent/config/workspace/workflow_runs/$runId.json")
        assertTrue("Workflow run record was not persisted in app-private storage", runFile.isFile)
        assertFalse("Workflow run escaped app-private storage", runFile.canonicalPath.contains("chaquopy", ignoreCase = true))
        val restored = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/workflow-runs/$runId",
            token = token,
        ).getJSONObject("data")
        assertEquals("success", restored.getString("status"))
        assertEquals(workflowId, restored.getString("workflow_id"))
    }

    @Test
    fun privatePluginIsDiscoveredLoadedEnabledAndInvokedLocally() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()
        val pluginId = "android-local-plugin"
        val toolName = "${pluginId}__echo"
        val pluginDir = context.filesDir.resolve("xiaoda/.ai-agent/plugin_packages/$pluginId")
        pluginDir.mkdirs()
        pluginDir.resolve("plugin.yaml").writeText(
            """
            id: $pluginId
            name: Android Local Plugin
            version: 1.0.0
            entrypoint: android_local_plugin:AndroidLocalPlugin
            description: Android app-private plugin test
            capabilities:
              tools:
                - name: echo
                  description: Local echo
            """.trimIndent(),
        )
        pluginDir.resolve("android_local_plugin.py").writeText(
            """
            from plugins.sdk import Plugin, register_tool

            class AndroidLocalPlugin(Plugin):
                @register_tool("echo", description="Android local echo")
                async def echo(self, text=""):
                    return "ANDROID_PLUGIN:" + text
            """.trimIndent(),
        )

        val discovered = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/plugins/discover",
            JSONObject(),
            token,
        ).getJSONObject("data").getJSONArray("discovered")
        assertTrue((0 until discovered.length()).any { discovered.getString(it) == pluginId })
        assertEquals(
            "ok",
            requestJson("POST", "${LocalBackendRuntime.endpoint}/api/v1/plugins/$pluginId/load", JSONObject(), token)
                .getJSONObject("data").getString("status"),
        )
        assertEquals(
            "ok",
            requestJson("POST", "${LocalBackendRuntime.endpoint}/api/v1/plugins/$pluginId/enable", JSONObject(), token)
                .getJSONObject("data").getString("status"),
        )
        requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/plugins/$pluginId/config",
            JSONObject().put("config", JSONObject().put("language", "zh-CN")),
            token,
        )
        val invoked = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/$toolName/invoke",
            JSONObject().put("args", JSONObject().put("text", "phone")),
            token,
        ).getJSONObject("data")
        assertTrue("Private plugin tool failed: $invoked", invoked.getBoolean("success"))
        assertTrue(invoked.getString("data").contains("ANDROID_PLUGIN:phone"))

        val trustStore = context.filesDir.resolve("xiaoda/.ai-agent/plugins/trust_store.json")
        val pluginConfig = context.filesDir.resolve("xiaoda/.ai-agent/plugins/$pluginId/config.json")
        assertTrue("Plugin trust store was not persisted privately", trustStore.isFile)
        assertTrue("Plugin config was not persisted privately", pluginConfig.isFile)
        assertTrue(pluginConfig.readText().contains("zh-CN"))
        assertFalse(pluginDir.canonicalPath.contains("chaquopy", ignoreCase = true))
    }

    @Test
    fun memoryAndSchedulesPersistLocallyWithoutProvider() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        val marker = "android-memory-${System.currentTimeMillis()}"
        val memoryId = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories",
            JSONObject()
                .put("summary", "$marker 手机本地长期记忆")
                .put("importance", 0.91)
                .put("emotion_label", "curious"),
            token,
        ).getJSONObject("data").getInt("id")
        val found = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories?q=$marker&limit=20",
            token = token,
        ).getJSONArray("data")
        assertTrue(
            "Created local memory was not searchable",
            (0 until found.length()).any { found.getJSONObject(it).optInt("id") == memoryId },
        )
        requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories/$memoryId",
            JSONObject().put("summary", "$marker 已更新").put("importance", 0.95),
            token,
        )
        val updated = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories?q=${marker}%20%E5%B7%B2%E6%9B%B4%E6%96%B0&limit=20",
            token = token,
        ).getJSONArray("data")
        assertTrue((0 until updated.length()).any { updated.getJSONObject(it).optInt("id") == memoryId })

        requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/config",
            JSONObject().put("enabled", true).put("greeting_max_per_day", 5),
            token,
        )
        requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/dnd",
            JSONObject().put("periods", org.json.JSONArray().put(JSONObject().put("start", "23:00").put("end", "07:00"))),
            token,
        )
        val schedule = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/greetings",
            JSONObject()
                .put("type", "fixed")
                .put("time", "08:30")
                .put("days", org.json.JSONArray().put(1).put(2).put(3).put(4).put(5))
                .put("prompt_hint", "手机本地晨间问候")
                .put("channels", org.json.JSONArray().put("web"))
                .put("enabled", true),
            token,
        ).getJSONObject("data")
        val scheduleId = schedule.getInt("id")
        assertTrue("Greeting scheduler was not started in local-only mode", scheduleId > 0)
        val schedules = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/greetings",
            token = token,
        ).getJSONArray("data")
        assertTrue((0 until schedules.length()).any { schedules.getJSONObject(it).getInt("id") == scheduleId })
        val disabled = requestJson(
            "PUT",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/greetings/$scheduleId",
            JSONObject().put("enabled", false),
            token,
        ).getJSONObject("data")
        assertEquals(0, disabled.getInt("enabled"))

        val privateRoot = context.filesDir.resolve("xiaoda/.ai-agent")
        assertTrue("Local Agent database directory is missing", privateRoot.resolve("data").exists())
        assertTrue("Schedule configuration was not persisted privately", privateRoot.resolve("config/webui_overrides.json").isFile)

        requestJson(
            "DELETE",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories/$memoryId",
            token = token,
            confirm = true,
        )
        requestJson(
            "DELETE",
            "${LocalBackendRuntime.endpoint}/api/v1/schedule/greetings/$scheduleId",
            token = token,
        )
        val afterDelete = requestJson(
            "GET",
            "${LocalBackendRuntime.endpoint}/api/v1/insight/memories?q=$marker&limit=20",
            token = token,
        ).getJSONArray("data")
        assertFalse((0 until afterDelete.length()).any { afterDelete.getJSONObject(it).optInt("id") == memoryId })
    }

    @Test
    fun twoCustomAgentsRunInParallelInsideTheLocalDag() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        FakeOpenAiServer().use { provider ->
            setPythonEnvironment("PROVIDER_ALLOW_HOSTS", "127.0.0.1")
            setPythonEnvironment("PROVIDER_ALLOWED_HTTP_PORTS", provider.port.toString())
            val providerId = "android_multi_${System.currentTimeMillis()}"
            val modelId = "xiaoda-multi-local"
            requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/models/providers",
                JSONObject()
                    .put("id", providerId)
                    .put("label", "Android Multi Agent Provider")
                    .put("format", "openai")
                    .put("base_url", "http://127.0.0.1:${provider.port}/v1")
                    .put("api_key", "local-multi-key")
                    .put("default_model", modelId)
                    .put("manual_models", org.json.JSONArray().put(modelId))
                    .put("enabled", true),
                token,
            )
            val agentA = "mobile_research_${System.currentTimeMillis()}"
            val agentB = "mobile_writer_${System.currentTimeMillis()}"
            for ((name, display) in listOf(agentA to "Local Researcher", agentB to "Local Writer")) {
                requestJson(
                    "POST",
                    "${LocalBackendRuntime.endpoint}/api/v1/agents",
                    JSONObject()
                        .put("name", name)
                        .put("display_name", display)
                        .put("provider", providerId)
                        .put("model", modelId)
                        .put("route_description", "Android local parallel Agent")
                        .put("capabilities", org.json.JSONArray().put("parallel-e2e"))
                        .put("personality_text", "You are a fully local Android sub-Agent."),
                    token,
                )
            }

            val workflowId = "multi_agent_${System.currentTimeMillis()}"
            requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/workflows",
                JSONObject()
                    .put("id", workflowId)
                    .put("name", "Android Multi Agent DAG")
                    .put("description", "Two local Agents execute as independent DAG roots")
                    .put("version", "1.0.0")
                    .put("enabled", true)
                    .put(
                        "nodes",
                        org.json.JSONArray()
                            .put(JSONObject().put("id", "research").put("type", "agent").put("label", "Research").put("ref", agentA).put("params", JSONObject().put("task", "Research on-device Agents")))
                            .put(JSONObject().put("id", "write").put("type", "agent").put("label", "Write").put("ref", agentB).put("params", JSONObject().put("task", "Write an on-device summary")))
                            .put(JSONObject().put("id", "finish").put("type", "tool").put("label", "Finish").put("ref", "calculator").put("params", JSONObject().put("expression", "6*7"))),
                    )
                    .put(
                        "edges",
                        org.json.JSONArray()
                            .put(org.json.JSONArray().put("research").put("finish"))
                            .put(org.json.JSONArray().put("write").put("finish")),
                    )
                    .put("trigger", "manual"),
                token,
            )
            val run = requestJson(
                "POST",
                "${LocalBackendRuntime.endpoint}/api/v1/workflows/$workflowId/run",
                JSONObject().put("input", "Run both Agents locally").put("wait", true),
                token,
            ).getJSONObject("data")
            assertEquals("success", run.getString("status"))
            val nodes = run.getJSONArray("nodes")
            assertEquals("success", nodes.getJSONObject(0).getString("status"))
            assertEquals("success", nodes.getJSONObject(1).getString("status"))
            assertTrue(run.getJSONObject("outputs").getString("research").contains(FakeOpenAiServer.REPLY_MARKER))
            assertTrue(run.getJSONObject("outputs").getString("write").contains(FakeOpenAiServer.REPLY_MARKER))
            assertTrue("The two local Agents were not dispatched concurrently", provider.maxConcurrentRequests.get() >= 2)
        }
    }

    @Test
    fun embeddedPythonExecutorRunsWithoutDesktopSubprocess() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        val executed = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/python_executor/invoke",
            JSONObject().put(
                "args",
                JSONObject().put(
                    "code",
                    "import json\nvalues=[n*n for n in range(6)]\nprint(json.dumps(values))\n_result=sum(values)",
                ),
            ),
            token,
        ).getJSONObject("data")
        assertTrue("Embedded Python execution failed: $executed", executed.getBoolean("success"))
        assertTrue(executed.getString("data").contains("[0, 1, 4, 9, 16, 25]"))
        assertTrue(executed.getString("data").contains("result: 55"))

        val blocked = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/python_executor/invoke",
            JSONObject().put("args", JSONObject().put("code", "import os\n_result=os.listdir('/')")),
            token,
        ).getJSONObject("data")
        assertFalse("Dangerous module import escaped the mobile Python sandbox", blocked.getBoolean("success"))
        assertTrue(blocked.getString("error").contains("os"))
    }

    @Test
    fun androidWebViewBrowserAutomationOperatesLocally() {
        val state = awaitBackend()
        if (state is LocalBackendRuntime.State.Failed) fail(state.detail)
        assertTrue(state is LocalBackendRuntime.State.Ready)
        val token = loginToken()

        val opened = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/browser_automation/invoke",
            JSONObject().put("args", JSONObject().put("action", "open").put("url", "https://example.com").put("timeout_ms", 60_000)),
            token,
        ).getJSONObject("data")
        assertTrue("Android WebView failed to open a public page: $opened", opened.getBoolean("success"))

        val read = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/browser_automation/invoke",
            JSONObject().put("args", JSONObject().put("action", "read").put("selector", "h1").put("max_chars", 2_000)),
            token,
        ).getJSONObject("data")
        assertTrue("Android WebView failed to read the page: $read", read.getBoolean("success"))
        assertTrue(read.getString("data").contains("Example Domain"))

        val evaluated = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/browser_automation/invoke",
            JSONObject().put("args", JSONObject().put("action", "evaluate").put("script", "return document.querySelector('h1').textContent + ':native';")),
            token,
        ).getJSONObject("data")
        assertTrue("Android WebView JavaScript failed: $evaluated", evaluated.getBoolean("success"))
        assertTrue(evaluated.getString("data").contains("Example Domain:native"))

        val screenshot = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/browser_automation/invoke",
            JSONObject().put("args", JSONObject().put("action", "screenshot").put("name", "android-browser-e2e")),
            token,
        ).getJSONObject("data")
        assertTrue("Android WebView screenshot failed: $screenshot", screenshot.getBoolean("success"))
        val screenshotText = screenshot.getString("data")
        assertTrue(screenshotText.contains("android-browser-e2e.png"))
        assertTrue(
            "Browser screenshot was not persisted in app-private storage",
            context.filesDir.resolve("xiaoda/.ai-agent/data/media/browser/android-browser-e2e.png").isFile,
        )

        val blocked = requestJson(
            "POST",
            "${LocalBackendRuntime.endpoint}/api/v1/tools/browser_automation/invoke",
            JSONObject().put("args", JSONObject().put("action", "open").put("url", "http://169.254.169.254/latest/meta-data")),
            token,
        ).getJSONObject("data")
        assertFalse("Browser automation allowed a metadata/SSRF target", blocked.getBoolean("success"))
    }

    private fun awaitBackend(): LocalBackendRuntime.State {
        val latch = CountDownLatch(1)
        val result = AtomicReference<LocalBackendRuntime.State>(LocalBackendRuntime.State.Starting)
        LocalBackendRuntime.start(context) { next ->
            result.set(next)
            if (next !is LocalBackendRuntime.State.Starting) latch.countDown()
        }
        assertTrue("Embedded backend did not finish startup", latch.await(180, TimeUnit.SECONDS))
        return result.get()
    }






    private fun evaluateJavaScript(webView: WebView, script: String): String {
        val latch = CountDownLatch(1)
        val result = AtomicReference("null")
        webView.post {
            webView.evaluateJavascript(script) { value ->
                result.set(value ?: "null")
                latch.countDown()
            }
        }
        assertTrue("JavaScript evaluation timed out", latch.await(15, TimeUnit.SECONDS))
        return result.get()
    }

    private fun waitForJavaScript(webView: WebView, expression: String, timeoutMs: Long) {
        val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMs)
        while (System.nanoTime() < deadline) {
            if (evaluateJavaScript(webView, "Boolean($expression)") == "true") return
            Thread.sleep(200)
        }
        fail("JavaScript condition did not become true: $expression")
    }

    private fun setPythonEnvironment(name: String, value: String) {
        val environment = Python.getInstance().getModule("os").get("environ")!!
        environment.callAttr("__setitem__", name, value)
    }

    private fun loginToken(): String = requestJson(
        "POST",
        "${LocalBackendRuntime.endpoint}/api/v1/auth/login",
        JSONObject().put("password", ""),
    ).getJSONObject("data").getString("token")

    private fun requestMultipart(
        url: String,
        filename: String,
        contentType: String,
        bytes: ByteArray,
        token: String,
    ): JSONObject {
        val boundary = "----XiaodaAndroid${System.nanoTime()}"
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 5_000
            connection.readTimeout = 180_000
            connection.doOutput = true
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            connection.outputStream.use { output ->
                output.write("--$boundary\r\n".toByteArray())
                output.write("Content-Disposition: form-data; name=\"file\"; filename=\"$filename\"\r\n".toByteArray())
                output.write("Content-Type: $contentType\r\n\r\n".toByteArray())
                output.write(bytes)
                output.write("\r\n--$boundary--\r\n".toByteArray())
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val payload = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) fail("POST $url failed with HTTP $status: $payload")
            JSONObject(payload)
        } finally {
            connection.disconnect()
        }
    }
    private fun requestJson(
        method: String,
        url: String,
        body: JSONObject? = null,
        token: String? = null,
        confirm: Boolean = false,
    ): JSONObject {
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = method
            connection.connectTimeout = 5_000
            connection.readTimeout = 180_000
            connection.setRequestProperty("Accept", "application/json")
            if (!token.isNullOrBlank()) connection.setRequestProperty("Authorization", "Bearer $token")
            if (confirm) connection.setRequestProperty("X-Confirm", "yes")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val payload = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) fail("$method $url failed with HTTP $status: $payload")
            JSONObject(payload)
        } finally {
            connection.disconnect()
        }
    }

    private class FakeOpenAiServer : AutoCloseable {
        companion object {
            const val REPLY_MARKER = "LOCAL_ANDROID_REPLY"
        }

        private val closed = AtomicBoolean(false)
        private val server = ServerSocket(0, 16, InetAddress.getByName("127.0.0.1"))
        val port: Int = server.localPort
        val requestCount = AtomicInteger(0)
        val toolRequestCount = AtomicInteger(0)
        private val activeRequests = AtomicInteger(0)
        val maxConcurrentRequests = AtomicInteger(0)
        private val worker = Thread({ serve() }, "xiaoda-fake-openai").apply {
            isDaemon = true
            start()
        }

        private fun serve() {
            while (!closed.get()) {
                val socket = try {
                    server.accept()
                } catch (_: Exception) {
                    break
                }
                Thread({
                    runCatching { handle(socket) }
                    runCatching { socket.close() }
                }, "xiaoda-fake-openai-request").apply { isDaemon = true; start() }
            }
        }

        private fun handle(socket: Socket) {
            val active = activeRequests.incrementAndGet()
            maxConcurrentRequests.updateAndGet { current -> maxOf(current, active) }
            try {
            socket.soTimeout = 10_000
            val input = socket.getInputStream()
            val headerBytes = java.io.ByteArrayOutputStream()
            var matched = 0
            val delimiter = byteArrayOf(13, 10, 13, 10)
            while (headerBytes.size() < 64 * 1024) {
                val next = input.read()
                if (next < 0) break
                headerBytes.write(next)
                matched = if (next.toByte() == delimiter[matched]) {
                    matched + 1
                } else if (next.toByte() == delimiter[0]) {
                    1
                } else {
                    0
                }
                if (matched == delimiter.size) break
            }
            val headers = headerBytes.toString(Charsets.ISO_8859_1.name())
            val contentLength = headers.lineSequence()
                .firstOrNull { it.startsWith("Content-Length:", ignoreCase = true) }
                ?.substringAfter(':')?.trim()?.toIntOrNull() ?: 0
            val bodyBytes = ByteArray(contentLength)
            var offset = 0
            while (offset < bodyBytes.size) {
                val read = input.read(bodyBytes, offset, bodyBytes.size - offset)
                if (read < 0) break
                offset += read
            }
            val body = bodyBytes.copyOf(offset).toString(Charsets.UTF_8)
            val request = runCatching { JSONObject(body) }.getOrElse { JSONObject() }
            val stream = request.optBoolean("stream")
            val messages = request.optJSONArray("messages")
            val hasToolResult = messages != null && (0 until messages.length()).any {
                messages.optJSONObject(it)?.optString("role") == "tool"
            }
            val shouldCallTool = stream && request.optJSONArray("tools") != null && !hasToolResult
            requestCount.incrementAndGet()
            if (!stream) Thread.sleep(150)
            if (shouldCallTool) toolRequestCount.incrementAndGet()

            val payload = when {
                shouldCallTool -> streamingToolCallResponse()
                stream -> streamingResponse()
                else -> regularResponse()
            }
            val contentType = if (stream) "text/event-stream" else "application/json"
            val payloadBytes = payload.toByteArray(Charsets.UTF_8)
            val responseHeaders = buildString {
                append("HTTP/1.1 200 OK\r\n")
                append("Content-Type: $contentType; charset=utf-8\r\n")
                append("Content-Length: ${payloadBytes.size}\r\n")
                append("Connection: close\r\n\r\n")
            }.toByteArray(Charsets.ISO_8859_1)
            socket.getOutputStream().use { output ->
                output.write(responseHeaders)
                output.write(payloadBytes)
                output.flush()
            }
            } finally {
                activeRequests.decrementAndGet()
            }
        }

        private fun regularResponse(): String = JSONObject()
            .put("id", "chatcmpl-android-local")
            .put("object", "chat.completion")
            .put("created", System.currentTimeMillis() / 1000)
            .put("model", "xiaoda-android-e2e")
            .put(
                "choices",
                org.json.JSONArray().put(
                    JSONObject()
                        .put("index", 0)
                        .put("message", JSONObject().put("role", "assistant").put("content", "$REPLY_MARKER 手机本地完整回复"))
                        .put("finish_reason", "stop"),
                ),
            )
            .put("usage", JSONObject().put("prompt_tokens", 8).put("completion_tokens", 6).put("total_tokens", 14))
            .toString()

        private fun streamingToolCallResponse(): String {
            fun chunk(toolCall: JSONObject?, finishReason: String?): String = JSONObject()
                .put("id", "chatcmpl-android-tool")
                .put("object", "chat.completion.chunk")
                .put("created", System.currentTimeMillis() / 1000)
                .put("model", "xiaoda-android-e2e")
                .put(
                    "choices",
                    org.json.JSONArray().put(
                        JSONObject()
                            .put("index", 0)
                            .put(
                                "delta",
                                JSONObject().apply {
                                    if (toolCall != null) put("tool_calls", org.json.JSONArray().put(toolCall))
                                },
                            )
                            .put("finish_reason", finishReason ?: JSONObject.NULL),
                    ),
                )
                .toString()
            val first = JSONObject()
                .put("index", 0)
                .put("id", "call_android_calculator")
                .put("type", "function")
                .put("function", JSONObject().put("name", "calculator").put("arguments", "{\"expression\":"))
            val second = JSONObject()
                .put("index", 0)
                .put("function", JSONObject().put("arguments", "\"1+1\"}"))
            return buildString {
                append("data: ${chunk(first, null)}\n\n")
                append("data: ${chunk(second, null)}\n\n")
                append("data: ${chunk(null, "tool_calls")}\n\n")
                append("data: [DONE]\n\n")
            }
        }

        private fun streamingResponse(): String {
            fun chunk(content: String?, finishReason: String?): String = JSONObject()
                .put("id", "chatcmpl-android-local")
                .put("object", "chat.completion.chunk")
                .put("created", System.currentTimeMillis() / 1000)
                .put("model", "xiaoda-android-e2e")
                .put(
                    "choices",
                    org.json.JSONArray().put(
                        JSONObject()
                            .put("index", 0)
                            .put("delta", JSONObject().apply { if (content != null) put("content", content) })
                            .put("finish_reason", finishReason ?: JSONObject.NULL),
                    ),
                )
                .toString()
            return buildString {
                append("data: ${chunk(REPLY_MARKER, null)}\n\n")
                append("data: ${chunk(" 手机本地流式回复", null)}\n\n")
                append("data: ${chunk(null, "stop")}\n\n")
                append("data: [DONE]\n\n")
            }
        }

        override fun close() {
            closed.set(true)
            runCatching { server.close() }
            worker.join(2_000)
        }
    }

}




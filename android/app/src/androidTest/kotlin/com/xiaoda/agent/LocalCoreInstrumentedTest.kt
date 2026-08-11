package com.xiaoda.agent

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.xiaoda.agent.local.LocalAiController
import com.xiaoda.agent.local.LocalStateStore
import com.xiaoda.agent.local.ProviderConfigValidator
import com.xiaoda.agent.security.KeystoreSecretStore
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class LocalCoreInstrumentedTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun encryptedProviderConfigurationStreamsACompleteLocalConversation() {
        MockWebServer().use { server ->
            server.enqueue(
                MockResponse()
                    .setHeader("Content-Type", "text/event-stream")
                    .setBody(
                        "data: {\"choices\":[{\"delta\":{\"content\":\"Local \"}}]}\n\n" +
                            "data: {\"choices\":[{\"delta\":{\"content\":\"works\"}}]}\n\n" +
                            "data: [DONE]\n\n",
                    ),
            )
            server.start()
            val providerId = "instrumented-${System.currentTimeMillis()}"
            val controller = LocalAiController(
                LocalStateStore(context, KeystoreSecretStore(context)),
                validator = ProviderConfigValidator(allowDevelopmentEndpoints = true),
            )
            try {
                val saved = controller.saveProvider(
                    JSONObject()
                        .put("id", providerId)
                        .put("label", "Instrumented")
                        .put("format", "openai")
                        .put("baseUrl", server.url("/v1").toString().trimEnd('/'))
                        .put("defaultModel", "test-model")
                        .put("apiKey", "instrumented-secret"),
                )
                assertTrue(saved.optBoolean("hasApiKey"))
                assertFalse(saved.toString().contains("instrumented-secret"))
                assertFalse(controller.bootstrap().toString().contains("instrumented-secret"))

                controller.saveAgent(
                    JSONObject()
                        .put("name", "Xiaoda")
                        .put("providerId", providerId)
                        .put("model", "test-model")
                        .put("systemPrompt", "Be concise"),
                )
                val sessionId = controller.createSession().getString("id")
                val completed = CountDownLatch(1)
                var answer = ""
                var failure = ""

                val started = controller.startChat(
                    JSONObject()
                        .put("sessionId", sessionId)
                        .put("requestId", "instrumented-request")
                        .put("text", "test"),
                ) { event ->
                    when (event.optString("event")) {
                        "local.chat.completed" -> {
                            answer = event.getJSONObject("data").getString("content")
                            completed.countDown()
                        }
                        "local.chat.failed" -> {
                            failure = event.getJSONObject("data").getString("error")
                            completed.countDown()
                        }
                    }
                }

                assertTrue(started.optBoolean("started"))
                assertTrue("local chat timed out", completed.await(15, TimeUnit.SECONDS))
                assertEquals("", failure)
                assertEquals("Local works", answer)
                val messages = controller.messages(JSONObject().put("sessionId", sessionId)).getJSONArray("messages")
                assertEquals(2, messages.length())
                assertEquals("Local works", messages.getJSONObject(1).getString("content"))
                val request = server.takeRequest(5, TimeUnit.SECONDS)
                assertEquals("/v1/chat/completions", request?.path)
                assertEquals("Bearer instrumented-secret", request?.getHeader("Authorization"))
            } finally {
                controller.close()
            }
        }
    }
}

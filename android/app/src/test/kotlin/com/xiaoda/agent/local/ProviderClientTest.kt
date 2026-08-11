package com.xiaoda.agent.local

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProviderClientTest {
    @Test
    fun listsOpenAiCompatibleModelsWithoutExposingTheKeyInTheUrl() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setHeader("Content-Type", "application/json").setBody("""{"data":[{"id":"model-b"},{"id":"model-a"}]}"""))
            server.start()
            val provider = LocalProvider("test", "Test", "openai", server.url("/v1").toString().trimEnd('/'), "model-a")

            val models = ProviderClient().listModels(provider, "secret-key")

            assertEquals(listOf("model-a", "model-b"), models)
            val request = server.takeRequest()
            assertEquals("/v1/models", request.path)
            assertEquals("Bearer secret-key", request.getHeader("Authorization"))
            assertTrue(request.requestUrl.toString().contains("secret-key").not())
        }
    }

    @Test
    fun streamsOpenAiCompatibleTextDeltas() {
        MockWebServer().use { server ->
            server.enqueue(
                MockResponse()
                    .setHeader("Content-Type", "text/event-stream")
                    .setBody("data: {\"choices\":[{\"delta\":{\"content\":\"?\"}}]}\n\ndata: {\"choices\":[{\"delta\":{\"content\":\"?\"}}]}\n\ndata: [DONE]\n\n"),
            )
            server.start()
            val provider = LocalProvider("test", "Test", "openai", server.url("/v1").toString().trimEnd('/'), "model-a")
            val deltas = mutableListOf<String>()

            val result = ProviderClient().streamChat(
                provider,
                "secret-key",
                "model-a",
                "system",
                listOf(LocalMessage("1", "user", "hello", 1L)),
                emptyList(),
                onCall = {},
                onDelta = deltas::add,
            )

            assertEquals("??", result)
            assertEquals(listOf("?", "?"), deltas)
            val request = server.takeRequest()
            assertEquals("/v1/chat/completions", request.path)
            assertTrue(request.body.readUtf8().contains("\"stream\":true"))
        }
    }
}

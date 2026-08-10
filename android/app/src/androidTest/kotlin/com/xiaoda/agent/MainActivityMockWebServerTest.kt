package com.xiaoda.agent

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.MockResponse
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class MainActivityMockWebServerTest {
    @Test
    fun notificationIntentNavigatesTheRealWebViewToItsRoute() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val intent = Intent(context, MainActivity::class.java)
            .setAction(NotificationNavigationPolicy.ACTION_OPEN_ROUTE)
            .putExtra(NotificationNavigationPolicy.EXTRA_ROUTE, "/settings/system")

        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            scenario.onActivity { activity ->
                val field = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
                val webView = field.get(activity) as android.webkit.WebView
                assertTrue(webView.url.orEmpty().contains("#/settings/system"))
            }
        }
    }

    @Test
    fun debugActivityAcceptsOnlyTheExplicitTestEndpointOverride() {
        MockWebServer().use { server ->
            server.start()
            val endpoint = server.url("/").toString().trimEnd('/')
            val context = ApplicationProvider.getApplicationContext<android.content.Context>()
            val intent = Intent(context, MainActivity::class.java)
                .putExtra("xiaoda.remoteEndpointOverride", endpoint)

            ActivityScenario.launch<MainActivity>(intent).use { scenario ->
                scenario.onActivity { activity ->
                    val method = MainActivity::class.java.getDeclaredMethod("remoteEndpoint").apply { isAccessible = true }
                    assertEquals(endpoint, method.invoke(activity))
                }
            }
        }
    }

    @Test
    fun endpointOverrideCannotChangeAfterActivityStartup() {
        MockWebServer().use { first ->
            MockWebServer().use { second ->
                first.start()
                second.start()
                val firstEndpoint = first.url("/").toString().trimEnd('/')
                val secondEndpoint = second.url("/").toString().trimEnd('/')
                val context = ApplicationProvider.getApplicationContext<android.content.Context>()
                val intent = Intent(context, MainActivity::class.java)
                    .putExtra("xiaoda.remoteEndpointOverride", firstEndpoint)

                ActivityScenario.launch<MainActivity>(intent).use { scenario ->
                    scenario.onActivity { activity ->
                        val method = MainActivity::class.java.getDeclaredMethod("remoteEndpoint").apply { isAccessible = true }
                        assertEquals(firstEndpoint, method.invoke(activity))
                        val onNewIntent = MainActivity::class.java.getDeclaredMethod("onNewIntent", Intent::class.java).apply { isAccessible = true }
                        onNewIntent.invoke(activity, Intent(activity, MainActivity::class.java).putExtra("xiaoda.remoteEndpointOverride", secondEndpoint))
                        assertEquals(firstEndpoint, method.invoke(activity))
                    }
                }
            }
        }
    }

    @Test
    fun realActivityPostsAuthenticationToMockWebServer() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"ok":true,"data":{"token":"bearer-token","expires_at":9999999999}}""").setHeader("Content-Type", "application/json"))
            val endpoint = server.url("/").toString().trimEnd('/')
            val context = ApplicationProvider.getApplicationContext<android.content.Context>()
            val intent = Intent(context, MainActivity::class.java).putExtra("xiaoda.remoteEndpointOverride", endpoint)

            ActivityScenario.launch<MainActivity>(intent).use { scenario ->
                lateinit var activity: MainActivity
                scenario.onActivity { activity = it }
                val method = MainActivity::class.java.getDeclaredMethod("postJson", String::class.java, JSONObject::class.java, String::class.java).apply { isAccessible = true }
                val executor = Executors.newSingleThreadExecutor()
                try {
                    val result = executor.submit<JSONObject> {
                        method.invoke(activity, "/api/v1/auth/login", JSONObject().put("password", "password"), null) as JSONObject
                    }.get(5, TimeUnit.SECONDS)
                    assertEquals("bearer-token", result.getJSONObject("data").getString("token"))
                } finally {
                    executor.shutdownNow()
                }
            }

            val request = server.takeRequest(5, TimeUnit.SECONDS)
            assertEquals("/api/v1/auth/login", requireNotNull(request).path)
            assertTrue(request.body.readUtf8().contains("password"))
        }
    }
}

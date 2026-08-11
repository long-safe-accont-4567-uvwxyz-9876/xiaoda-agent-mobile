package com.xiaoda.agent

import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.xiaoda.agent.local.LocalAiController
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

@RunWith(AndroidJUnit4::class)
class MainActivityLocalIntegrationTest {
    @Test
    fun coldStartLoadsTheBundledApplicationWithoutARemoteEndpoint() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            Thread.sleep(1_500)
            scenario.onActivity { activity ->
                val field = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
                val webView = field.get(activity) as android.webkit.WebView
                assertTrue(webView.url.orEmpty().startsWith("https://appassets.androidplatform.net"))
            }
            val rendered = AtomicBoolean(false)
            for (attempt in 0 until 20) {
                val evaluated = CountDownLatch(1)
                scenario.onActivity { activity ->
                    val field = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
                    val webView = field.get(activity) as android.webkit.WebView
                    webView.evaluateJavascript("document.querySelector('.local-app') !== null") { result ->
                        rendered.set(result == "true")
                        evaluated.countDown()
                    }
                }
                assertTrue("WebView JavaScript evaluation timed out", evaluated.await(2, TimeUnit.SECONDS))
                if (rendered.get()) break
                Thread.sleep(500)
            }
            assertTrue("Mobile local UI did not render", rendered.get())
        }
    }

    @Test
    fun localControllerIsInitializedOnColdStart() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val field = MainActivity::class.java.getDeclaredField("localAi").apply { isAccessible = true }
                val controller = field.get(activity) as LocalAiController
                val bootstrap = controller.bootstrap()
                assertNotNull(bootstrap.optJSONArray("providers"))
                assertNotNull(bootstrap.optJSONArray("sessions"))
                assertNotNull(bootstrap.optJSONArray("capabilities"))
            }
        }
    }

    @Test
    fun notificationIntentNavigatesTheBundledWebViewRoute() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val intent = Intent(context, MainActivity::class.java)
            .setAction(NotificationNavigationPolicy.ACTION_OPEN_ROUTE)
            .putExtra(NotificationNavigationPolicy.EXTRA_ROUTE, "/mobile-local")

        ActivityScenario.launch<MainActivity>(intent).use { scenario ->
            scenario.onActivity { activity ->
                val field = MainActivity::class.java.getDeclaredField("webView").apply { isAccessible = true }
                val webView = field.get(activity) as android.webkit.WebView
                assertTrue(webView.url.orEmpty().contains("#/mobile-local"))
            }
        }
    }
}
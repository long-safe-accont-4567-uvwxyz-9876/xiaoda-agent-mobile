package com.xiaoda.agent.webcontainer

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WebContainerPolicyTest {
    @Test
    fun `trusted navigation accepts only bundled origin and approved external links`() {
        val policy = TrustedNavigationPolicy("https://appassets.androidplatform.net")

        assertTrue(policy.isBundledResource("https://appassets.androidplatform.net/assets/index.js"))
        assertTrue(policy.isExternalLink("https://example.com/help"))
        assertFalse(policy.isBundledResource("https://example.com/index.html"))
        assertFalse(policy.isExternalLink("intent://settings"))
        assertFalse(policy.isExternalLink("javascript:alert(1)"))
    }

    @Test
    fun `resource manifest requires matching version and hashes`() {
        val verifier = AssetManifestVerifier()
        val firstHash = "a".repeat(64)
        val secondHash = "b".repeat(64)
        val manifest = """{"appVersion":"0.5.70","files":{"index.html":"$firstHash","assets/app.js":"$secondHash"}}"""

        assertTrue(verifier.isValid(manifest, "0.5.70", mapOf("index.html" to firstHash, "assets/app.js" to secondHash)))
        assertFalse(verifier.isValid(manifest, "0.5.71", mapOf("index.html" to firstHash, "assets/app.js" to secondHash)))
        assertFalse(verifier.isValid(manifest, "0.5.70", mapOf("index.html" to "c".repeat(64), "assets/app.js" to secondHash)))
        assertFalse(verifier.isValid("""{"appVersion":"0.5.70","files":{"index.html":"abc"}}""", "0.5.70", mapOf("index.html" to "abc")))
        assertFalse(verifier.isValid("""{"appVersion":"0.5.70","files":{"../index.html":"${"a".repeat(64)}"}}""", "0.5.70", mapOf("../index.html" to "${"a".repeat(64)}")))
    }
}

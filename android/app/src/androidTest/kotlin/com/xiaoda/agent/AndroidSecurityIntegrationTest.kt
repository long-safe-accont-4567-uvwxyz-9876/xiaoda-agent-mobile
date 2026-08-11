package com.xiaoda.agent

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.xiaoda.agent.bridge.BridgeContract
import com.xiaoda.agent.webcontainer.BundledAssetLoader
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AndroidSecurityIntegrationTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test
    fun packagedWebAssetsMatchTheRuntimeManifest() {
        assertTrue(BundledAssetLoader(context).isTrusted(BuildConfig.WEB_ASSET_VERSION))
    }

    @Test
    fun packagedBridgeCannotReceiveRawTokensOrGenericCapabilities() {
        assertTrue("local.bootstrap" in BridgeContract.allowedMethods)
        assertTrue("local.chat" in BridgeContract.allowedMethods)
        assertFalse("authenticate" in BridgeContract.allowedMethods)
        assertFalse("restoreSession" in BridgeContract.allowedMethods)
        assertFalse("clearSession" in BridgeContract.allowedMethods)
        assertFalse("setSecureToken" in BridgeContract.allowedMethods)
        assertFalse("runCommand" in BridgeContract.allowedMethods)
        assertFalse("readFile" in BridgeContract.allowedMethods)
        assertFalse("openIntent" in BridgeContract.allowedMethods)
    }
}

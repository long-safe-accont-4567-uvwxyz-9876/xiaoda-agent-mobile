import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AndroidBuildContractTest(unittest.TestCase):
    def test_web_build_tracks_all_reproducibility_inputs(self):
        build_script = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")

        self.assertIn('webBuildInputs.from(webFrontendDir.resolve("src"))', build_script)
        self.assertIn('webBuildInputs.from(webFrontendDir.resolve("public"))', build_script)
        for filename in ("package.json", "package-lock.json", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "index.html"):
            self.assertIn(f'webFrontendDir.resolve("{filename}")', build_script)
        self.assertIn("inputs.files(webBuildInputs)", build_script)
        self.assertIn('inputs.property("webAssetVersion", webAssetVersion)', build_script)
        self.assertIn("verifyGeneratedWebAssets", build_script)
        self.assertIn("dependsOn(verifyGeneratedWebAssets)", build_script)

    def test_android_web_build_does_not_consume_mutable_server_dist(self):
        build_script = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")

        self.assertNotIn('resolve("web/dist")', build_script)
        self.assertNotIn('"run", "build"', build_script)
        self.assertIn('"exec", "vite", "--", "build"', build_script)

    def test_asset_version_uses_project_version_source_of_truth(self):
        build_script = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertNotIn('val webAssetVersion = "', build_script)
        self.assertIn('pyproject.toml', build_script)
        self.assertIn('buildConfigField("String", "WEB_ASSET_VERSION"', build_script)
        self.assertIn('appVersion\\\":\\\"$webAssetVersion', build_script)
        self.assertIn(".isTrusted(BuildConfig.WEB_ASSET_VERSION)", activity)

    def test_network_callback_is_scoped_to_started_lifecycle(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        on_start = activity[activity.index("override fun onStart()") : activity.index("override fun onStop()")]
        on_stop = activity[activity.index("override fun onStop()") : activity.index("override fun onDestroy()")]
        self.assertIn("registerNetworkCallback()", on_start)
        self.assertIn("unregisterNetworkCallback()", on_stop)

    def test_webview_is_torn_down_with_activity(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")
        on_destroy = activity[activity.index("override fun onDestroy()") : activity.index("private fun configureWebContainer")]

        self.assertIn('removeWebMessageListener(webView, "XiaodaNative")', on_destroy)
        self.assertIn("webView.destroy()", on_destroy)

    def test_real_android_tests_are_a_blocking_ci_gate(self):
        app_script = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")
        workflow = (ROOT.parent / ".github" / "workflows" / "android-apk.yml").read_text(encoding="utf-8")
        instrumentation_test = ROOT / "app" / "src" / "androidTest" / "kotlin" / "com" / "xiaoda" / "agent" / "AndroidSecurityIntegrationTest.kt"

        self.assertIn('testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"', app_script)
        self.assertIn("connectedCheck", workflow)
        self.assertIn("android-emulator-runner", workflow)
        self.assertTrue(instrumentation_test.is_file())
        self.assertIn("BundledAssetLoader(context).isTrusted", instrumentation_test.read_text(encoding="utf-8"))

    def test_native_authentication_exposes_only_opaque_handles(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")
        contract = (ROOT / "core" / "bridge-api" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "bridge" / "BridgeContract.kt").read_text(encoding="utf-8")

        self.assertNotIn("setSecureToken", contract)
        self.assertIn('"authenticate"', contract)
        self.assertIn('"restoreSession"', contract)
        self.assertIn("KeystoreTokenStore", activity)
        self.assertIn("SessionHandleManager", activity)
        self.assertNotIn('put("token"', activity)

    def test_webview_state_is_restored_before_loading_fresh_ui(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertIn("webView.saveState(outState)", activity)
        self.assertIn("webView.restoreState(savedInstanceState)", activity)

    def test_ci_reads_web_asset_version_instead_of_hardcoding_it(self):
        workflow = (ROOT.parent / ".github" / "workflows" / "android-apk.yml").read_text(encoding="utf-8")

        self.assertNotIn("verify_web_assets.py app/build/generated/webAssets 0.5.70", workflow)
        self.assertIn("scripts/project_version.py", workflow)

    def test_file_bridge_uses_resolver_mime_and_openable_size(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertIn("contentResolver.getType(uri)", activity)
        self.assertIn("OpenableColumns.SIZE", activity)
        self.assertIn("SelectedFileReader", activity)

    def test_network_callbacks_are_generation_guarded(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertIn("NetworkCallbackGeneration", activity)
        self.assertIn("isCurrent(generation)", activity)
        self.assertNotIn("NETWORK_AVAILABLE", activity)

    def test_bridge_file_result_returns_verified_content_not_content_uri(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertIn('put("dataBase64"', activity)
        self.assertIn('put("sizeBytes"', activity)
        self.assertNotIn('put("uri", uri.toString())', activity)

    def test_runtime_manifest_is_verified_before_main_ui_loads(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")

        self.assertIn(".isTrusted(BuildConfig.WEB_ASSET_VERSION)", activity)
        self.assertLess(activity.index(".isTrusted(BuildConfig.WEB_ASSET_VERSION)"), activity.index("webView.loadUrl(BundledAssetLoader.START_URL)"))

    def test_termux_component_is_opt_in_research_only(self):
        settings = (ROOT / "settings.gradle.kts").read_text(encoding="utf-8")
        app_build = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")
        contract = (ROOT / "core" / "bridge-api" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "bridge" / "BridgeContract.kt").read_text(encoding="utf-8")
        workflow = (ROOT.parent / ".github" / "workflows" / "android-apk.yml").read_text(encoding="utf-8")
        self.assertIn('include(":feature:terminal-runtime")', settings)
        self.assertIn("terminalRuntimeResearchEnabled", app_build)
        self.assertIn('add("debugRuntimeOnly", project(":feature:terminal-runtime"))', app_build)
        self.assertTrue((ROOT / "feature" / "terminal-runtime").is_dir())
        for name in ("openTerminal", "getRuntimeStatus", "stopRuntime"):
            self.assertNotIn(f'"{name}"', contract)
        for marker in ("ndk;22.1.7171670", "terminalRuntimeResearchEnabled=true", "verify_termux_component.py"):
            self.assertIn(marker, workflow)

    def test_remote_runtime_config_is_injected_before_frontend_modules(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")
        api = (ROOT.parent / "web" / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
        websocket = (ROOT.parent / "web" / "frontend" / "src" / "api" / "ws.ts").read_text(encoding="utf-8")

        self.assertIn("addDocumentStartJavaScript", activity)
        self.assertIn("__XIAODA_RUNTIME_CONFIG__", activity)
        self.assertIn("runtimeApiBase", api)
        self.assertIn("credentials: 'include'", api)
        self.assertIn("runtimeWebSocketUrl", websocket)
        self.assertIn("['xiaoda-session', token]", websocket)
        self.assertIn("isAndroidWebView() && token", websocket)

    def test_upload_limit_is_shared_by_runtime_and_bridge(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")
        gradle = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")
        prompt = (ROOT.parent / "web" / "frontend" / "src" / "components" / "chat" / "PromptInput.vue").read_text(encoding="utf-8")

        self.assertIn('config/mobile_contract.json', gradle)
        self.assertIn('put("maxUploadBytes", BuildConfig.UPLOAD_MAX_BYTES)', activity)
        self.assertIn("runtimeMaxUploadBytes()", prompt)
        self.assertNotIn("MAX_FILE_BYTES", activity)

    def test_activity_handles_notification_routes_without_terminal_sheet_bridge(self):
        activity = (ROOT / "app" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivity.kt").read_text(encoding="utf-8")
        contract = (ROOT / "core" / "bridge-api" / "src" / "main" / "kotlin" / "com" / "xiaoda" / "agent" / "bridge" / "BridgeContract.kt").read_text(encoding="utf-8")
        chat_view = (ROOT.parent / "web" / "frontend" / "src" / "views" / "ChatView.vue").read_text(encoding="utf-8")

        self.assertNotIn('"setSheetOpen"', contract)
        self.assertNotIn("sheetOpen", activity)
        self.assertNotIn("xiaoda:close-top-sheet", activity)
        self.assertIn("BackNavigationPolicy.decide(webView.canGoBack())", activity)
        self.assertIn("NotificationNavigationPolicy.route", activity)
        self.assertIn("setIntent(intent)", activity)
        self.assertIn('ChatTerminal v-if="terminalAvailable"', chat_view)
        self.assertIn("!isMobile.value && !isAndroidWebView()", chat_view)

    def test_mock_webserver_activity_integration_is_present(self):
        catalog = (ROOT / "gradle" / "libs.versions.toml").read_text(encoding="utf-8")
        app_script = (ROOT / "app" / "build.gradle.kts").read_text(encoding="utf-8")
        test_file = ROOT / "app" / "src" / "androidTest" / "kotlin" / "com" / "xiaoda" / "agent" / "MainActivityMockWebServerTest.kt"

        self.assertIn("mockwebserver", catalog.lower())
        self.assertIn("androidTestImplementation(libs.okhttp.mockwebserver)", app_script)
        self.assertTrue(test_file.is_file())
        source = test_file.read_text(encoding="utf-8")
        self.assertIn("ActivityScenario", source)
        self.assertIn("MockWebServer", source)


if __name__ == "__main__":
    unittest.main()

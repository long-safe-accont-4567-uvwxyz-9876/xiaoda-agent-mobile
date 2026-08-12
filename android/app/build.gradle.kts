plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.chaquopy)
}

import java.security.MessageDigest

val repositoryRoot = rootProject.projectDir.parentFile
val webFrontendDir = repositoryRoot.resolve("web/frontend")
val projectMetadataFile = repositoryRoot.resolve("pyproject.toml")
val mobileContractFile = repositoryRoot.resolve("config/mobile_contract.json")
val mobileContract = groovy.json.JsonSlurper().parse(mobileContractFile) as Map<*, *>
val uploadMaxBytes = (mobileContract["upload_max_bytes"] as Number).toLong()
val sessionCookie = mobileContract["webview_session_cookie"] as Map<*, *>
val sessionCookieName = sessionCookie["name"].toString()
val sessionCookieMaxAgeSeconds = (sessionCookie["max_age_seconds"] as Number).toInt()
val sessionCookieSameSite = sessionCookie["same_site"].toString().replaceFirstChar { it.uppercase() }
val webDistDir = layout.buildDirectory.dir("intermediates/webDist")
val generatedWebAssets = layout.buildDirectory.dir("generated/webAssets")
val webAssetVersion = Regex("""(?m)^version\s*=\s*"([^"]+)"\s*$""")
    .find(projectMetadataFile.readText())
    ?.groupValues
    ?.get(1)
    ?: error("Unable to read project version from ${projectMetadataFile.absolutePath}")
val webBuildInputs = objects.fileCollection()
webBuildInputs.from(webFrontendDir.resolve("src"))
webBuildInputs.from(webFrontendDir.resolve("public"))
webBuildInputs.from(webFrontendDir.resolve("package.json"))
webBuildInputs.from(webFrontendDir.resolve("package-lock.json"))
webBuildInputs.from(webFrontendDir.resolve("vite.config.ts"))
webBuildInputs.from(webFrontendDir.resolve("tsconfig.json"))
webBuildInputs.from(webFrontendDir.resolve("tsconfig.app.json"))
webBuildInputs.from(webFrontendDir.resolve("index.html"))
webBuildInputs.from(projectMetadataFile)
webBuildInputs.from(mobileContractFile)

val buildWebUi by tasks.registering(Exec::class) {
    workingDir(webFrontendDir)
    val output = webDistDir.get().asFile
    environment("VITE_XIAODA_MOBILE_BUILD", "1")
    commandLine(if (System.getProperty("os.name").startsWith("Windows")) "npm.cmd" else "npm", "exec", "vite", "--", "build", "--outDir", output.absolutePath, "--emptyOutDir")
    inputs.files(webBuildInputs)
    inputs.property("mobileWebBuild", true)
    outputs.dir(output)
}

val prepareWebAssets by tasks.registering {
    dependsOn(buildWebUi)
    inputs.dir(webDistDir)
    inputs.property("webAssetVersion", webAssetVersion)
    outputs.dir(generatedWebAssets)
    doLast {
        val output = generatedWebAssets.get().asFile
        output.deleteRecursively()
        webDistDir.get().asFile.copyRecursively(output, overwrite = true)
        val files = output.walkTopDown().filter { it.isFile && it.name != "asset-manifest.json" }.sortedBy { it.relativeTo(output).invariantSeparatorsPath }
        val entries = files.map { file ->
            val digest = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }
            "\"${file.relativeTo(output).invariantSeparatorsPath}\":\"$digest\""
        }
        output.resolve("asset-manifest.json").writeText("{\"appVersion\":\"$webAssetVersion\",\"files\":{${entries.joinToString(",")}}}")
    }
}

val verifyGeneratedWebAssets by tasks.registering {
    dependsOn(prepareWebAssets)
    inputs.dir(generatedWebAssets)
    inputs.property("webAssetVersion", webAssetVersion)
    doLast {
        val output = generatedWebAssets.get().asFile
        val manifest = groovy.json.JsonSlurper().parse(output.resolve("asset-manifest.json")) as Map<*, *>
        require(manifest["appVersion"] == webAssetVersion)
        val expected = manifest["files"] as Map<*, *>
        val actual = output.walkTopDown().filter { it.isFile && it.name != "asset-manifest.json" }.associate { file ->
            val path = file.relativeTo(output).invariantSeparatorsPath
            val digest = MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }
            path to digest
        }
        require(expected == actual)
    }
}

// The embedded backend (web.server) imports the whole repository's runtime packages
// (tools, db, core, config, web, utils, security, tool_engine, ...). Chaquopy only
// packages the Python source dirs it is told about, so we stage a copy of the
// repository root into the build dir, excluding non-runtime content, and point
// Chaquopy at that staged directory.
val pythonRuntimeDir = layout.buildDirectory.dir("intermediates/pythonRuntime")
val stagePythonRuntime by tasks.registering(Sync::class) {
    from(repositoryRoot)
    into(pythonRuntimeDir)
    exclude(
        "web/frontend/**",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.git/**",
        "tests/**",
        "scripts/**",
        "docs/**",
        "audit/**",
        "deploy/**",
        "output/**",
        "specs/**",
        "codeact/**",
        "assets/**",
        "android/**",
        "evaluation/**",
        "chaos/**",
        ".venv/**",
        ".pytest_cache/**",
        ".ruff_cache/**",
        ".scan_reports/**",
        ".learnings/**",
        ".playwright-cli/**",
        ".superpowers/**",
        ".superpowers-skills",
        ".dbg/**",
        ".auto_update",
        ".brooks-lint-history.json",
        "tmp/**",
        "nohup.out",
        "*.log",
    )
}
// Ensure the staged Python tree is ready before any Chaquopy/Android packaging step.
tasks.configureEach {
    if (name != "stagePythonRuntime" && (name.contains("Python", ignoreCase = true) || name == "preBuild")) {
        dependsOn(stagePythonRuntime)
    }
}

val keystoreFile = rootProject.file("keystore/xiaoda-release.jks")
val keystorePassword = System.getenv("XIAODA_KEYSTORE_PASSWORD")
val hasReleaseKey = keystoreFile.exists() && !keystorePassword.isNullOrEmpty()

android {
    namespace = "com.xiaoda.agent"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.xiaoda.agent"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = 1
        versionName = webAssetVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "WEB_ASSET_VERSION", "\"$webAssetVersion\"")
        buildConfigField("long", "UPLOAD_MAX_BYTES", "${uploadMaxBytes}L")
        buildConfigField("String", "SESSION_COOKIE_NAME", "\"$sessionCookieName\"")
        buildConfigField("int", "SESSION_COOKIE_MAX_AGE_SECONDS", sessionCookieMaxAgeSeconds.toString())
        buildConfigField("String", "SESSION_COOKIE_SAME_SITE", "\"$sessionCookieSameSite\"")
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    signingConfigs {
        if (hasReleaseKey) {
            create("release") {
                storeFile = keystoreFile
                storePassword = keystorePassword
                keyAlias = System.getenv("XIAODA_KEY_ALIAS") ?: "xiaoda"
                keyPassword = keystorePassword
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "true")
        }
        create("staging") {
            initWith(getByName("release"))
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            signingConfig = if (hasReleaseKey) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "false")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = if (hasReleaseKey) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "false")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    sourceSets.getByName("main").assets.srcDir(generatedWebAssets)

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        // Cross-platform: prefer an explicit env override (CI sets XIAODA_BUILD_PYTHON),
        // otherwise fall back to the Windows developer path used on this machine.
        buildPython = listOf(System.getenv("XIAODA_BUILD_PYTHON") ?: "C:/Users/lenovo/AppData/Local/Programs/Python/Python311/python.exe")
        pip {
            install("fastapi==0.115.12")
            install("uvicorn==0.34.0")
            install("websockets==14.2")
            install("httpx==0.28.1")
            // pydantic 2.x：plugins/manifest.py 等使用 field_validator（pydantic 2 API），
            // openai 2.x 亦要求 pydantic 2；与 requirements.txt 的 pydantic>=2.13.4 对齐。
            install("pydantic>=2.13.4,<3")
            // 运行时顶层导入的第三方依赖（缺失会导致 ModuleNotFoundError）：
            install("loguru>=0.7.3")
            install("python-dotenv>=1.2.1")
            install("pyyaml>=6.0")
            install("openai>=2.41.0")
            install("certifi>=2024.7.0")
            // 注意：jieba 在 PyPI 只有 sdist（无 wheel），Chaquopy 要求 wheel，无法安装。
            // 运行时已全部改为 lazy import + 降级（见 core/jieba_prewarm.py、memory/key_extractor.py）。
            install("cryptography>=43.0.0")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(pythonRuntimeDir)
        }
    }
}

tasks.named("preBuild").configure { dependsOn(verifyGeneratedWebAssets) }

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":core:webcontainer"))
    implementation(project(":core:security"))
    implementation(project(":core:bridge-api"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.webkit)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.okhttp.mockwebserver)
}

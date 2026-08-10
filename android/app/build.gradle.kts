plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

import java.security.MessageDigest

val repositoryRoot = rootProject.projectDir.parentFile
val webFrontendDir = repositoryRoot.resolve("web/frontend")
val projectMetadataFile = repositoryRoot.resolve("pyproject.toml")
val webDistDir = layout.buildDirectory.dir("intermediates/webDist")
val generatedWebAssets = layout.buildDirectory.dir("generated/webAssets")
val webAssetVersion = Regex("""(?m)^version\s*=\s*"([^"]+)"\s*$""")
    .find(projectMetadataFile.readText())
    ?.groupValues
    ?.get(1)
    ?: error("Unable to read project version from ${projectMetadataFile.absolutePath}")
val terminalRuntimeResearchEnabled = providers.gradleProperty("terminalRuntimeResearchEnabled")
    .map(String::toBoolean)
    .orElse(false)
    .get()

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

val buildWebUi by tasks.registering(Exec::class) {
    workingDir(webFrontendDir)
    val output = webDistDir.get().asFile
    commandLine(if (System.getProperty("os.name").startsWith("Windows")) "npm.cmd" else "npm", "exec", "vite", "--", "build", "--outDir", output.absolutePath, "--emptyOutDir")
    inputs.files(webBuildInputs)
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
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "true")
            buildConfigField("boolean", "TERMINAL_RUNTIME_ENABLED", terminalRuntimeResearchEnabled.toString())
        }
        create("staging") {
            initWith(getByName("release"))
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "false")
            buildConfigField("boolean", "TERMINAL_RUNTIME_ENABLED", "false")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
            buildConfigField("boolean", "WEBVIEW_DEBUGGING", "false")
            buildConfigField("boolean", "TERMINAL_RUNTIME_ENABLED", "false")
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

tasks.named("preBuild").configure { dependsOn(verifyGeneratedWebAssets) }

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(project(":core:webcontainer"))
    implementation(project(":core:security"))
    implementation(project(":core:bridge-api"))
    if (terminalRuntimeResearchEnabled) {
        add("debugRuntimeOnly", project(":feature:terminal-runtime"))
    }
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.webkit)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.core)
}

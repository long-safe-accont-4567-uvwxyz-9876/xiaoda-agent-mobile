# Android G5-01 工程初始化设计

## 目标

在 `android/` 下建立可复现构建的 Kotlin DSL Android 工程，使 debug、staging、release 三个变体均能生成 APK，并在提交后由独立 GitHub Actions 工作流执行 lint、JVM test、assemble 和制品上传。

## 范围

本阶段创建五个 Gradle 模块：

- `:app`：单 Activity、启动路由和依赖装配。
- `:core:webcontainer`：WebView 安全默认值、远端地址策略和导航边界。
- `:core:security`：安全存储契约和敏感值脱敏基础能力。
- `:core:bridge-api`：最小 Bridge 契约和危险能力防复活门禁。
- `:feature:terminal-runtime`：仅提供禁用状态契约，不包含 Termux、PTY、本地 AgentCore 或本地服务端。

本阶段不实现 G5-02 的内置 Vue 资源复制与 `WebViewAssetLoader`，不实现 G5-03 的真实 Keystore Token 流程，不实现 G5-05 的终端运行时。

## 构建结构

```text
android/
├─ app/
├─ core/webcontainer/
├─ core/security/
├─ core/bridge-api/
├─ feature/terminal-runtime/
├─ build-logic/
├─ gradle/libs.versions.toml
├─ gradle/wrapper/
├─ build.gradle.kts
├─ settings.gradle.kts
├─ gradle.properties
├─ gradlew
└─ gradlew.bat
```

所有插件和依赖版本由版本目录统一管理。Gradle Wrapper、AGP、Kotlin、JDK 和 compile SDK 必须形成官方兼容组合，CI 与本地使用同一 JDK 主版本。

## 变体策略

- `debug`：允许开发地址，启用 WebView 调试，application id 带 `.debug` 后缀。
- `staging`：面向测试远端服务，仅允许 HTTPS/WSS，application id 带 `.staging` 后缀。
- `release`：仅允许 HTTPS/WSS，关闭 WebView 调试和明文流量。
- 远端入口通过 `BuildConfig` 和资源注入，不把 Provider Key、Embedding Key 或用户 Token 写入 APK。
- CI 的 release APK 使用非生产签名，仅用于构建验收；正式发布签名属于 G6-04。

## 安全边界

- Android 端不包含 Python、Ollama、本地模型、ONNX Runtime 或 AgentCore。
- WebView 默认禁止文件访问、内容访问、混合内容和任意窗口打开。
- staging/release 拒绝 `http://` 和 `ws://`。
- Bridge 白名单仅允许架构规格中的窄接口，不允许 `runCommand`、`readFile`、`openIntent`。
- terminal runtime 默认返回 disabled，不启动进程，不下载二进制。

## CI

新增 `.github/workflows/android-apk.yml`：

- 对目标分支 push、pull request 和手动触发运行。
- 使用固定 JDK 和 Gradle 缓存。
- 执行 `lint test assembleDebug assembleStaging assembleRelease`。
- 校验三个 APK 均存在。
- 扫描 APK/工程，阻断本地 AI、Ollama、Python runtime 和 Provider Key 残留。
- 分别上传 debug、staging、release APK artifact。

## 验收

1. 五个模块均参与 Gradle 构建。
2. debug、staging、release 三个 APK 均可生成。
3. JVM 测试覆盖地址策略、Bridge 白名单、脱敏和 terminal disabled 状态。
4. Android lint 与单元测试通过。
5. APK 防复活扫描通过。
6. 提交后独立 Android workflow 明确上传 APK，不依赖桌面 PyInstaller job。

## 决策

- 采用五模块架构，修正文档中“四个模块”的数量歧义。
- 采用独立 Android workflow，不把 APK 构建耦合进桌面发布矩阵。
- G5-01 只建立安全骨架；未通过 G5-05 法务和运行时门禁前，release 不包含终端 runtime 实现。

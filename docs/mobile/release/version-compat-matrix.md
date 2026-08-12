# 移动端版本兼容矩阵

版本基线：`0.5.70`（来自 `pyproject.toml` / `web/frontend/package.json` 同步，经 `scripts/check_version_sync.py --ci` 校验）。

## 1. Android OS 支持范围

| 维度 | 声明 | 依据 |
|---|---|---|
| minSdk | 26（Android 8.0 Oreo） | `android/gradle/libs.versions.toml` → `minSdk = "26"` |
| targetSdk | 35（Android 15） | 同上 → `targetSdk = "35"` |
| compileSdk | 35 | 同上 → `compileSdk = "35"` |
| 架构 | arm64-v8a（内嵌 Python 后端） | 本地 Python 后端按 AArch64 交叉编译 |
| JVM | Java 17 / Kotlin jvmTarget 17 | 各模块 `build.gradle.kts` |

例外：`targetSdk < 26` 的旧设备不在支持范围；高版本 OS 以 Google 兼容性矩阵为准，文档不硬编码未来会失效的版本号。

## 2. 前端 Web 资源版本绑定

| 维度 | 值 |
|---|---|
| web asset 版本 | `0.5.70`（`WEB_ASSET_VERSION` buildConfig） |
| 哈希清单 | `assets/asset-manifest.json`（SHA-256 逐文件） |
| 校验 | `verify_web_assets.py` + `verifyGeneratedWebAssets`，构建期强制 |

Web 资源与 APK 版本强绑定：`asset-manifest.json` 的 `appVersion` 必须等于 `pyproject.toml` version，否则 `preBuild` 失败。

## 3. 服务端协议兼容

| 通道 | 协议 | 版本策略 |
|---|---|---|
| WebSocket | 自定义 subprotocol 头认证 | 服务端不匹配时 WebView 明确阻断（REL-006） |
| REST | `/api/...` 短会话（5 分钟 handle） | 与 `config/mobile_contract.json` 绑定 |
| 会话 | Android Keystore 存 token，5 分钟 WebView session handle | 不把 bearer token 暴露给 JS |

兼容策略：客户端遇到不兼容协议版本，明确阻断并提示，不做静默降级。

## 4. 数据层迁移

| 迁移 | 兼容范围 | 回滚 |
|---|---|---|
| 向量维度 512↔1024 | 备份 → 全量重编码 → 原子替换 | 保留备份可回滚 |
| 配置迁移 | 向后兼容旧配置 | 备份 + 回滚测试通过 |

见 `docs/mobile/architecture-v2.md` 迁移表与 `docs/mobile/release/rollback.md`。

## 5. Provider 协议版本

| 项 | 版本策略 |
|---|---|
| Provider 协议 | 稳定 `PROVIDER_OPERATION_FAILED` / `persist` 错误协议 |
| 出站 | HTTP/HTTPS 端口策略、SSRF 防护按 `PROVIDER_ALLOW_HOSTS` |
| 诊断 | DNS/TLS/认证/发现/聊天分阶段超时 |

## 6. 已发布基线记录

| 发布 | 版本 | Android OS | 说明 |
|---|---|---|---|
| 当前工作树 | 0.5.70 | 8.0 (minSdk 26) – 15 (targetSdk 35) | 发布候选验收中 |

> 本矩阵为声明式文档；实际安装校验与真机行为证据见 `test-evidence.md`（G6-02/G6-03 需设备门禁）。
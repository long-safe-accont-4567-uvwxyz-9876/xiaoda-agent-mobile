# 移动端重构测试证据

## G2-04 Provider 应用服务

任务编号：G2-04

状态：PASS

实现边界：

- `ProviderRepository` 独占 `models.providers.<id>` 配置写入，`ConfigService.delete()` 保存失败恢复内存旧值。
- `ProviderCredentialStore` 保存原文件快照，在同目录准备临时文件并原子替换，支持写入、删除和按字节恢复。
- `ProviderRuntimeRegistry` 原子交换客户端并同步凭证池，成功后关闭旧客户端，失败时恢复旧客户端和凭证状态。
- `ProviderApplicationService` 按 Provider ID 使用异步锁串行创建、更新、独立 Key 更新、启用/禁用和删除。
- Router 保留输入校验、现有路由引用保护、审计、发现缓存失效和广播，所有生命周期写操作统一委托应用服务。

验证命令：

```powershell
py -3.12 -m pytest tests/test_g2_04_provider_application_service.py -q --tb=short
py -3.12 -m pytest tests/test_g2_01_error_protocol.py tests/test_g2_01_provider_protocol.py tests/test_g2_02_provider_urls.py tests/test_g2_03_safe_outbound.py tests/test_g2_04_provider_application_service.py tests/test_credential_pool.py tests/test_provider_key_reading.py tests/test_degraded_mode_any_provider.py -q --tb=short
py -3.12 -m pytest -q --tb=short
py -3.12 -m ruff check web/provider_application.py web/config_service.py web/routers/models.py utils/credential_pool.py tests/test_g2_04_provider_application_service.py
py -3.12 -m compileall -q web/provider_application.py web/config_service.py web/routers/models.py utils/credential_pool.py tests/test_g2_04_provider_application_service.py
py -3.12 scripts/check_version_sync.py --ci
npm --prefix web/frontend run build
git diff --check
```

验证结果：

- G2-04 专项：`24 passed`。
- G2-01 至 G2-04、凭证池、凭证读取和自定义 Provider 降级回归：`132 passed`。
- 后端完整回归：`3081 passed, 8 skipped, 30 warnings in 351.90s`，退出码 `0`。
- 前端生产构建：`3993 modules transformed`，`built in 19.82s`，退出码 `0`；保留既有大 chunk 警告。
- Ruff、Python compileall、版本同步 `0.5.70` 和 `git diff --check`：PASS。

补偿验收：

- 创建覆盖客户端构建、配置保存、凭证发布和 runtime 发布失败，失败后配置、Key、客户端、凭证池均为空。
- 更新与独立 Key 更新覆盖配置、凭证和 runtime 失败，失败后四态与操作前快照一致，旧客户端保持可用，候选客户端关闭。
- 禁用立即移除客户端与凭证池但保留配置和加密 Key；重新启用从保留 Key 重建运行时状态。
- 删除覆盖 runtime 移除、配置删除和凭证删除失败，失败恢复完整旧状态；成功删除四态并关闭旧客户端。
- 同 Provider 并发 mutation 串行执行；凭证池快照、替换、恢复和删除均在线程锁内隔离副本。
- Router 将事务异常映射为稳定的 `PROVIDER_OPERATION_FAILED` / `persist` 协议，不向响应暴露底层异常或凭证内容。

任务边界：

- 完整引用收集和结构化 `PROVIDER_IN_USE` 引用列表属于 G2-05；G2-04 保留 Router 现有路由引用删除保护。

## G2-03 安全出站客户端

任务编号：G2-03

状态：PASS

安全决策：

- Provider URL 的格式与协议/端口策略在请求前准备，DNS 在真实连接 backend 内异步解析，校验与拨号处于同一传输边界。
- 全部 A/AAAA 结果均参与安全分类；非授权目标只要存在一个危险结果即拒绝，实际 TCP 只拨号首个已校验 pinned IP。
- HTTP `Host`、TLS SNI 与证书 hostname 校验保持原 Provider hostname；`trust_env=False` 禁止环境代理绕过安全传输。
- 重定向只允许 scheme、hostname 和 effective port 全部一致的同 origin；跨 origin 响应先关闭再拒绝。
- Provider 私网授权只读取 `PROVIDER_ALLOW_HOSTS`，不继承通用 `SSRF_ALLOW_HOSTS`。
- HTTPS 默认只允许 443；额外端口通过 `PROVIDER_ALLOWED_HTTPS_PORTS` 显式配置。HTTP 默认端口策略为 80，且仅对 `PROVIDER_ALLOW_HOSTS` 中全部解析为非公网地址的目标开放；额外端口通过 `PROVIDER_ALLOWED_HTTP_PORTS` 显式配置。

覆盖范围：

- discover、probe、OpenAI/Anthropic chat、ModelRouter MiMo/Agnes、子 Agent、XiaoliAgent、MiMoTransport 和 AgnesTransport 共用安全客户端工厂。
- Provider 替换/删除、子 Agent 热重载/注销、ModelRouter 刷新/shutdown 和 Transport shutdown 关闭旧客户端。
- 流式消费者退出或任务取消时关闭上游 stream 并重新抛出取消信号。
- `httpcore>=1.0.9,<1.1` 锁定已验证的 network backend 接口兼容范围。

验证命令：

```powershell
py -3.12 -m pytest tests/test_g2_03_safe_outbound.py -q --tb=short
py -3.12 -m pytest tests/test_g2_03_safe_outbound.py tests/test_g2_02_provider_urls.py tests/test_g2_01_provider_protocol.py tests/test_g2_01_error_protocol.py tests/test_error_classifier.py tests/test_stream_fallback_chain.py tests/test_model_switching_refactor.py tests/test_agent_routing.py tests/test_agent_behavior_fixes.py tests/test_sub_agent_timeout.py tests/test_transports.py -q --tb=short
py -3.12 -m pytest -q
py -3.12 -m ruff check security/safe_outbound.py web/custom_providers.py web/provider_urls.py web/routers/model_discovery.py web/probes.py model_router.py agent_dispatcher.py web/agent_registry.py xiaoli_agent.py transports tests/test_g2_03_safe_outbound.py
py -3.12 -m compileall -q security/safe_outbound.py web/custom_providers.py web/provider_urls.py web/routers/model_discovery.py web/probes.py model_router.py agent_dispatcher.py web/agent_registry.py xiaoli_agent.py transports
py -3.12 scripts/check_version_sync.py --ci
npm --prefix web/frontend run build
git diff --check
```

验证结果：

- G2-03 专项：`16 passed`。
- G2-01/G2-02/G2-03 与模型路由、子 Agent、Transport 相关定向回归：`129 passed`。
- 后端完整回归：`3058 passed, 8 skipped, 30 warnings in 391.98s`，退出码 `0`。
- 前端生产构建：`3996 modules transformed`，`built in 35.96s`。
- Ruff、Python compileall、版本同步 `0.5.70` 和 `git diff --check`：PASS。
- 多轮独立安全复审最终结果：Critical `0`，Important `0`。

验收证据：

- 真实 TCP listener 测试确认 DNS 仅调用一次，socket 拨号 pinned IP，HTTP Host 保持 Provider hostname。
- backend 单元测试确认 TLS `server_hostname` 强制为原 Provider hostname。
- 参数化策略测试覆盖公网 HTTP、非 allowlist 端口、私网默认拒绝、Provider 专属授权、授权域名解析公网时拒绝明文 HTTP，以及混合安全/危险 DNS 结果。
- redirect 测试覆盖跨主机拒绝与拒绝前响应释放。
- OpenAI SDK 注入测试和 Provider 生命周期测试覆盖统一安全客户端及替换/删除资源释放。

任务边界：

- Provider 配置、凭证与 runtime registry 的创建/更新/删除事务属于 G2-04，不在本任务宣称完成。

## G5-02 至 G5-06 Android 系统壳

任务编号：G5-02、G5-03、G5-04、G5-05、G5-06

状态：G5-02 PASS；G5-03 PASS；G5-04 PASS；G5-05 BLOCKED；G5-06 BLOCKED

修改文件：

- `android/app/*`：Vue 资源构建复制、SHA-256 清单、受信任 WebView、WebMessage Bridge、系统文件/分享/深链/返回/网络/通知与生命周期装配。
- `android/core/webcontainer/*`：`WebViewAssetLoader`、导航 allowlist、资源清单验证和安全 WebView 配置。
- `android/core/security/*`：Android Keystore AES-GCM token 存储、五分钟不透明会话句柄和日志脱敏。
- `android/core/bridge-api/*`：固定 Bridge 白名单、可信 origin 及文件/分享/终端参数验证。
- `android/feature/terminal-runtime/*`：远程 CLI 策略、单实例 RuntimeSupervisor、nonce/协议握手、用户停止、有限崩溃退避和阻塞态合规产物。
- `android/scripts/verify_web_assets.py`、`.github/workflows/android-apk.yml`：资源哈希与 CI 门禁。
- 2026-08-10 关键项复核修正：Bridge 装配不引用 `SecureTokenStore`、`SessionHandleManager` 或 token 字段；文件回传查询 `ContentResolver.getType` 与 `OpenableColumns.SIZE`，再限流读取并校验声明大小、实际大小和内容 MIME；网络回调增加注册代际，重建后只采信当前系统网络；Gradle 显式纳入 `src`、`public`、lockfile、package、Vite、TS 与 HTML 输入，并在打包前复核生成资源清单。
- 2026-08-10 复审剩余项修正：Activity 实际装配 `KeystoreTokenStore` 与五分钟 `SessionHandleManager`，原生完成登录并以服务端短句柄设置 HttpOnly 会话 Cookie；Vue Bridge adapter 不在 Android Web Storage 写入 bearer，Android WS 不构造 query token；`PromptInput` 消费原生选择器返回的受检字节并继续既有 multipart 上传；Activity 在首次加载前恢复 WebView 状态并在重建时保存；Android Gradle 与 CI 均从 `pyproject.toml` 读取版本。

TDD 证据：

- 先增加 Web 资源、Session handle、Bridge 参数、系统策略和 RuntimeSupervisor JVM 测试。
- 首次目标测试按预期因生产类型不存在而编译失败；补最小实现后全部转绿。
- 完整 Android 回归先捕获 Bridge allowlist 数量和 `ACCESS_NETWORK_STATE` lint 缺失，再修复并强制重跑。

测试命令：

```powershell
cd android
gradlew.bat lint test assembleDebug assembleStaging assembleRelease --rerun-tasks --no-build-cache --no-configuration-cache
cd ..
python -m unittest discover -s android/scripts -p "test_*.py" -v
python android/scripts/verify_web_assets.py android/app/build/generated/webAssets 0.5.70
python android/scripts/verify_apk.py --source-root android android/app/build/outputs/apk/debug/app-debug.apk android/app/build/outputs/apk/staging/app-staging.apk android/app/build/outputs/apk/release/app-release.apk
py -3.12 -m pytest -q --tb=short
py -3.12 scripts/check_version_sync.py --ci
py -3.12 -m ruff check . --select=E9,F63,F7,F82
cd web/frontend
npm run build
git diff --check
```

2026-08-10 关键项复核验证：

```powershell
py -3.12 -m unittest discover -s android/scripts -p "test_*.py" -v
git diff --check -- android docs/mobile .github/workflows/android-apk.yml
```

测试结果：

- Android `lint test assembleDebug assembleStaging assembleRelease` 强制重跑：`BUILD SUCCESSFUL`，515 tasks executed。
- Android/Python 资源与 APK 扫描器：`14 tests passed`；资源清单与三个 APK 全部 PASS。
- 后端全量：`3058 passed, 8 skipped, 30 warnings`。
- 前端生产构建：`3979 modules transformed`，PASS；现有大 chunk 警告未升级为失败。
- 版本同步、严格 Ruff 和 `git diff --check`：PASS。
- 关键项复核 Python 构建/安全契约：`26 tests` 全部 PASS；`git diff --check` PASS。
- 新增 Android JVM 测试已按 TDD 先确认缺少 `SelectedFileReader`、`NetworkCallbackGeneration` 时失败；当前机器只有 JDK 21/26，没有项目要求的 JDK 17，故本轮本地 Gradle JVM 测试和 APK 重建未形成新通过证据，既有 APK 哈希不得视为本轮产物。
- 本轮新增复审测试先分别因缺少前端 Bridge adapter、服务端短句柄会话、WebView save/restore 和版本单源而失败；最小实现后定向 Python/Vitest 测试转绿。Android Gradle 结果以本轮最终验证记录为准。
- 本轮最终验证：认证/WS 定向 pytest `8 passed`；Android 构建与安全契约 `30 tests` 全部通过；Bridge 与 AppLayout Vitest `7 passed`；前端 typecheck、生产 build、版本同步、严格 Ruff 和 `git diff --check` 通过。Android Gradle 已启动但本机缺少 Android SDK，配置阶段以 `SDK location not found` 阻塞，未伪报 APK/lint/JVM 新证据；完整前端套件另有两个既存 `ChatTerminal` 断言失败，与本轮改动无关。

产物路径：

- `android/app/build/generated/webAssets/asset-manifest.json`
- `android/app/build/outputs/apk/debug/app-debug.apk`：9,548,447 bytes，SHA-256 `F734C8A12E2B3F2F23DB081748BDC64BEE022623775C6732EAB963BD545D1E48`。
- `android/app/build/outputs/apk/staging/app-staging.apk`：8,500,536 bytes，SHA-256 `E2EAC78CD8AB88D04F0B7B661F02C66CACF1E96CC3C8B1A75C6B46B97763C412`。
- `android/app/build/outputs/apk/release/app-release.apk`：6,401,954 bytes，SHA-256 `036FD344EF648EA447BC471BAAFB5B7701266EDD551870EADABFA8965ABD45CC`。
- `android/feature/terminal-runtime/compliance/BOM.json`
- `android/feature/terminal-runtime/compliance/SBOM.spdx.json`
- `android/feature/terminal-runtime/compliance/NOTICE.md`

剩余风险与阻塞：

- G5-05 法务许可证义务与目标商店政策预审没有书面结论，必须由法务/渠道负责人审核；本记录不是法律结论。
- 未冻结获批 runtime 组件和 bootstrap，无法完成真实 ABI、解包空间和进程树回收验收；因此所有变体强制 `TERMINAL_RUNTIME_ENABLED=false`。
- G5-06 只有安全策略和 RuntimeSupervisor PoC；正式进程自动启动必须等 G5-05 全部 P0 门禁通过后另行启用并重跑 JVM、仪器、设备与真实进程树测试，因此状态保持 BLOCKED。
- G5-05 法务、渠道、ABI、空间和真实进程树门禁仍未关闭，状态保持 BLOCKED。
- G5-06 仍只允许禁用态 PoC，不启用正式 CLI 进程或自动启动，状态保持 BLOCKED。

关联 ADR：ADR-MOB2-001、ADR-MOB2-002、ADR-MOB2-005、ADR-MOB2-007

## G6 集成、发布和回滚预检

任务编号：G6-PREFLIGHT

状态：NO-GO

执行范围：

- 本次只执行 G6 预检，不跨越尚未完成的 G2-03 至 G5-06，也不将 G6 清单或发布候选标记为完成。
- 计划清单当前为 `76` 项完成、`148` 项未完成；验收矩阵共有 `97` 项，其中 `41` 项 P0、`52` 项 P1、`4` 项 P2，尚未形成完整逐项签署证据。
- 环境为 Windows、Python 3.12.0、Node 22.16.0、npm 10.9.4；系统 Java 为 21，未安装 Android SDK。

验证命令：

```powershell
py -3.12 -m pytest tests -q --tb=short
py -3.12 -m ruff check . --select=E9,F63,F7,F82
py -3.12 scripts/check_version_sync.py --ci
git diff --check
py -3.12 -m pytest tests/test_local_ai_retirement.py tests/test_local_embedding_retirement.py tests/test_backend_local_deploy_retirement.py tests/test_frontend_local_deploy_retirement.py tests/test_config_migrations.py tests/test_vector_dimension_migration.py -q --tb=short
npm --prefix web/frontend ci
npm --prefix web/frontend run typecheck
npm --prefix web/frontend run test
npm --prefix web/frontend run build
android\gradlew.bat lint test assembleDebug assembleStaging assembleRelease
py -3.12 -m unittest discover -s android/scripts -p "test_*.py" -v
py -3.12 android/scripts/verify_apk.py --source-root . android/app/build/outputs/apk/debug/app-debug.apk
```

结果：

- 后端全量回归失败：`3054 passed, 8 skipped, 3 failed, 30 warnings`。失败项为 `test_model_router_checks_finish_reason`、`test_try_fallback_chain_uses_registry_snapshot`、`test_fallback_chain_agnes_uses_snapshot`。
- Ruff 严格致命规则、版本同步 `0.5.70` 和 `git diff --check` 通过。
- 本地 AI/Ollama 退役、配置迁移和向量迁移定向回归 `31 passed`。
- 前端依赖安装和生产构建通过，`3979 modules transformed`；存在大于 500 kB 的 chunk 警告。
- 前端 typecheck 失败，共报告 `14` 个错误，涉及 `TopBar.vue`、`ChatView.vue`、`SettingsView.vue` 以及尚未落地的 G3 测试目标。
- 前端 Vitest 失败：`3 failed suites, 0 tests`，缺少 `useResponsiveShell`、`capabilities`、`CapabilityDrawer.vue` 等 G3 实现；没有 `test:e2e` 脚本或 Playwright 配置。
- Android APK 扫描器单元测试 `12 passed`；源码树和现有 debug APK 的凭证、本地 AI、Ollama、Python runtime、ONNX/BGE 扫描通过。
- 现有 debug APK 为 `9.1 MiB`，SHA-256 为 `947EC4EEDBB99601016BCAFC9F6FF3BD09E09C663D9ABA4DAE70090712C68C33`；包内存在 `assets/index.html` 和包含 `91` 个文件哈希的 `assets/asset-manifest.json`。
- Android lint、JVM test 和三变体 assemble 本次无法重跑：本机缺少 Android SDK；仓库没有 `src/androidTest`，因此仪器测试门禁尚不存在。
- 当前只有 debug APK；没有 staging/release APK、AAB 或 mapping 产物。staging/release 仍使用 debug signingConfig，正式发布端点仍是 `.invalid` 占位地址。
- Terminal runtime 的阻塞态空 SBOM/NOTICE 已存在，但完整应用 SBOM、许可证归档、兼容矩阵、性能基线、回滚包和回滚说明不存在。
- CI 后端全量测试、发布测试、Bandit 和 pip-audit 仍包含非阻断配置，不满足 G6 严格发布门禁。

产物路径：

- `docs/mobile/test-evidence.md`
- `android/app/build/outputs/apk/debug/app-debug.apk`
- `android/app/build/generated/webAssets/asset-manifest.json`
- `web/dist/`

阻塞项：

- 完成 G2-03 至 G5-06 的前置实现与验收，或为条件功能形成正式排除决策。
- 修复后端 3 个失败测试并恢复全量绿色。
- 完成 G3 实现，使前端 typecheck 和 Vitest 绿色，并补充移动/桌面 E2E。
- 安装可复现的 JDK 17 与 Android SDK 35 环境，补充并执行仪器测试。
- 配置真实端点、正式签名、AAB、mapping、完整 SBOM/NOTICE、许可证、兼容矩阵、性能证据和客户端/数据回滚产物。
- 将关键测试和安全扫描改为严格阻断门禁。

结论：

- G6-01、G6-02、G6-03、G6-04 和 G6-05 均不得标记完成。
- 当前版本不是发布候选，最终结论为 `NO-GO`。

## G3 共享导航与移动壳复核

任务编号：G3-01 至 G3-05

状态：PASS（无浏览器验收例外）

修改文件：`web/frontend/src/navigation/*`、`web/frontend/src/components/layout/*`、`web/frontend/src/composables/*`、`web/frontend/src/utils/focusTrap*`、`web/frontend/src/routes.ts`、`web/frontend/src/stores/chat.ts`、`web/frontend/src/views/ChatView.vue`

测试命令：

```powershell
npm test -- --run
npm run typecheck
npm run build
git diff --check
```

测试结果：

- Vitest `5 files, 24 passed`。
- `vue-tsc --noEmit` 通过。
- Vite 生产构建通过。
- `git diff --check` 通过。
- 仅缓存具名 `ChatView`，非聊天页面离开路由后卸载；断点切换不重建当前业务页面。
- 能力表覆盖全部 16 个生产路由，移动底栏固定五入口，抽屉覆盖其余入口。
- 能力抽屉与快捷状态支持初始焦点、Escape、焦点恢复及 Tab/Shift+Tab 循环。
- 通知使用独立有界事件集合，不从聊天 system 消息推导。

验收例外：

- 用户明确禁止浏览器，并批准使用代码测试替代多视口截图验收。
- NAV-001、UI-001、UI-002 在 G3 以路由覆盖、CSS 响应式规则、组件测试、typecheck 和 build 作为替代证据。
- 真实 Android 返回手势和系统窗口交互保留到 Android 系统壳验收。

剩余风险：

- 构建仍有既有大 chunk 警告。
- 不创建阶段提交，G3 与此前 worktree 未提交改动共享工作树，最终复审必须按文件范围审查。

---

## G2-02 URL 规范化

任务编号：G2-02

状态：PASS

协议决策：

- `base_url` 统一表示 API 根；根域和自定义路径前缀自动补 `/v1`，已有 `/v1` 保持不变。
- discover、OpenAI chat、Anthropic Messages、probe、Provider CRUD 和子 Agent 共用规范化与安全校验。
- 输出保留合法百分号编码，校验副本递归解码以阻断双重编码、路径穿越、编码分隔符和控制字符。
- userinfo、查询、fragment、非法或零端口、重复分隔符和点段均拒绝；IPv6 保留方括号及端口。
- 危险旧配置在启动、凭证池、懒注册和子 Agent 恢复路径隔离，不阻断其他 Provider 或服务启动。

验证命令：

```powershell
python -m pytest tests/test_g2_02_provider_urls.py tests/test_g2_01_provider_protocol.py tests/test_sub_agent_timeout.py tests/test_model_switching_refactor.py -q --tb=short
python -m pytest -q --tb=short
cd web/frontend
npm run build
```

验证结果：

- G2-02 表驱动测试 `44 passed`；相关模型切换和 Provider 回归通过。
- 后端完整回归 `3042 passed, 8 skipped, 30 warnings`。
- 前端生产构建通过，`3979 modules transformed`。
- G2-02 变更范围 Ruff、Python compileall、版本同步与 `git diff --check` 通过。
- 最终独立复审：Critical `0`，Important `0`。

任务边界：

- Provider 创建、更新和删除的跨配置/凭证/运行时事务化属于 G2-04/G2-05，不在 G2-02 混入实现。

## G2-01 稳定错误协议

任务编号：G2-01

状态：PASS

协议决策：

- 新客户端读取顶层 `code`、`message`、`stage`、`retryable` 和 `trace_id`。
- `stage` 固定为 `validate | dns | connect | tls | auth | discover | probe`。
- 兼容期保留 `detail`、嵌套 `error` 以及 AppException 历史 `error_code/details`。
- 错误响应不是可重试 mutation；客户端仅把 `retryable` 作为调用策略提示，服务端不承诺自动去重。
- 未知异常只返回安全通用消息和异常类型，不回传异常正文、上游响应或密钥。

覆盖范围：

- AppException、HTTPException、RequestValidationError、未知异常和限流中间件统一外形。
- 认证、超时、DNS、TLS、限流、模型不存在和 SSRF 映射到稳定错误码及阶段。
- Provider 发现按 `format` 分派；Anthropic 使用手动默认模型，不调用 OpenAI `/models`。
- Provider 诊断返回 `code/stage/retryable/message/latency_ms`，API、WebSocket 与持久化结果不回传上游正文。
- Anthropic Messages API 支持非流式与 SSE 流式响应，`max_tokens` 映射为 `length`，传输异常进入既有重试与 fallback 链。
- DNS、TLS、连接、超时和 HTTP 状态可从 httpx 包装链稳定分类，临时 Provider 客户端在成功与失败路径均释放。
- 前端统一请求、401、上传、语音、导出和首次运行入口优先读取顶层 `message`，并兼容旧嵌套错误。
- 响应体 `trace_id` 与 `X-Trace-Id` 响应头一致。

验证命令：

```powershell
python -m pytest tests/test_g2_01_provider_protocol.py tests/test_g2_01_error_protocol.py tests/test_error_classifier.py tests/test_stream_fallback_chain.py tests/test_rate_limit_middleware.py -q --tb=short
python -m pytest -q --tb=short
cd web/frontend
npm run build
```

验证结果：

- 错误协议、Provider 请求分类、Anthropic SSE、探针脱敏、恢复链和资源释放定向测试 `49 passed`。
- 后端完整回归 `2998 passed, 8 skipped, 30 warnings`。
- G2-01 变更范围 Ruff、Python compileall、版本同步与 `git diff --check` 通过。
- Vue TypeScript 生产构建通过。
- 最终独立复审：Critical `0`，Important `0`。

兼容与演进：

- G2 阶段仅做加法兼容，不删除 `detail`、嵌套 `error` 或历史 `error_code/details`。
- 删除兼容字段前必须有客户端版本使用证据、迁移窗口和独立移除任务。

## G1-08 完整回归与启动模式验收

任务编号：G1-08

状态：PASS

验收范围：

- 无 `EMBED_API_KEY` 时文本记忆继续可用，语义检索以 `embedding_key_missing` 明确禁用。
- 有 SiliconFlow Key 时使用 `BAAI/bge-m3` 远程向量模式，不允许本地或其他服务商回退。
- `/insight/memory-status` 同时公开文本记忆和语义检索状态。
- 其他 OpenAI-compatible Provider 的路由与凭证读取不受 Embedding 模式影响。

验证结果：

- `tests/test_g1_08_startup_modes.py`：`5 passed`。
- 后端全量：`2966 passed, 8 skipped, 30 warnings`。
- 严格 Ruff、Python compileall、版本同步、`git diff --check` 和前端生产构建通过。

剩余风险：

- 有 Key 验收使用受控替身验证协议与启动装配，不在测试中调用付费生产密钥。
- 真实 SiliconFlow 可用性、限流和网络故障属于部署环境监控，不得触发本地回退。

## G5-01 Android 工程初始化

任务编号：G5-01

状态：PASS（ADR-MOB2-007 并行例外，仅关闭 G5-01）

修改范围：

- 新建 `android/` 五模块 Kotlin DSL 工程。
- 固定 JDK 17、Gradle 8.11.1、AGP 8.9.2、Kotlin 2.1.20、compile/target SDK 35 和 min SDK 26。
- 配置 debug、staging、release 三变体，其中 staging/release 禁止明文端点，terminal runtime 保持 disabled。
- 新增独立 `.github/workflows/android-apk.yml`，严格执行 lint、JVM test、三变体 assemble、防复活扫描和三个 APK artifact 上传。
- 新增 `android/scripts/verify_apk.py` 及扫描器单元测试，使用分块流式扫描覆盖大型 entry，并扫描 Android 源码中的常见 Provider Key/Bearer token。

验证：

```powershell
android\gradlew.bat clean projects lint test assembleDebug assembleStaging assembleRelease
python -m unittest discover -s android/scripts -p "test_*.py" -v
python android/scripts/verify_apk.py --source-root android android/app/build/outputs/apk/debug/app-debug.apk android/app/build/outputs/apk/staging/app-staging.apk android/app/build/outputs/apk/release/app-release.apk
python -m pytest tests/test_local_ai_retirement.py tests/test_backend_local_deploy_retirement.py tests/test_frontend_local_deploy_retirement.py -q --tb=short
python scripts/check_version_sync.py --ci
python -m ruff check . --select=E9,F63,F7,F82
git diff --check
```

结果：

- Gradle 工程列出 `:app`、`:core:webcontainer`、`:core:security`、`:core:bridge-api`、`:feature:terminal-runtime`，完整构建 `BUILD SUCCESSFUL`。
- Android lint、四个 library module 的 debug/release JVM tests 和三个 APK assemble 全部通过。
- APK 扫描器测试 `12 passed`，覆盖大文件、测试源码、签名材料、PEM 私钥以及 OpenAI、Google、AWS、GitHub、Slack 常见凭证格式；debug、staging、release 三个 APK 均通过 Python/Ollama/AgentCore/FastAPI/ONNX/BGE 防复活扫描。
- 三个 APK 分别为 `app-debug.apk`、`app-staging.apk`、`app-release.apk`；本地验收使用 debug 签名，正式签名仍属于 G6-04。
- 本地 AI 前后端回归 `12 passed`。

剩余风险：

- 当前仓库路径含中文，Android Gradle Plugin 的 Windows 路径检查通过 `android.overridePathCheck=true` 明确放行；本地实测使用 ASCII junction 消除 Kotlin/JUnit worker 在中文路径下的类加载不稳定，GitHub Actions Linux 路径不受影响。
- G5-02 尚未集成 Vue 构建产物和 `WebViewAssetLoader`，当前 APK 是可构建安全空壳。
- release APK 当前使用 debug 签名，仅用于 G5-01 构建验收，不是发布候选。
- G5-01 依据 ADR-MOB2-007 提前并行，仅建立安全空壳和 APK CI；不得跳过 G2 至 G4 开始 G5-02。

## G0-01 工作树确认

任务编号：G0-01

状态：PASS

修改文件：

- `docs/mobile/*`
- `docs/INDEX.md`

测试命令：

```powershell
git status --short --branch
git remote -v
git log -1 --oneline
git rev-parse --show-toplevel
git rev-parse --path-format=absolute --git-dir
git rev-parse --path-format=absolute --git-common-dir
```

测试结果：

- 隔离工作树：`D:/移动Xiaoda/xiaoda-agent/.worktrees/mobile-v2-refactor`
- 分支：`refactor/mobile-v2`
- 基线提交：`9a0411e refactor: retire edge hardware support`
- 远程：`origin` 指向 `xiaoda-agent-mobile.git`
- 工作树仅包含本次 `docs/mobile/` 与 `docs/INDEX.md` 变更。
- 主目录 `.superpowers/brainstorm/` 和其他历史未跟踪文档未复制、未覆盖。

产物路径：

- `docs/mobile/test-evidence.md`

剩余风险：

- 系统默认 `python` 为 3.10.11，不满足项目 `>=3.11`；基线测试固定使用 `py -3.12`。
- 系统环境设置了 `NODE_TLS_REJECT_UNAUTHORIZED=0`，`npm ci` 输出 TLS 校验被禁用警告；依赖安装成功，但后续发布环境必须移除此设置。

关联 ADR：ADR-MOB2-001 至 ADR-MOB2-006

## G1-01 退役扫描

任务编号：G1-01

状态：EXPECTED RED

修改文件：

- `tests/test_local_ai_retirement.py`

测试结果：

- 防复活扫描能同时捕获 Ollama、本地部署前后端、本地 Embedding、BGE 模型资产、ONNX Runtime 和 tokenizers 残留。
- 当前失败是 G1 退役实施前的预期 RED，后续 G1-04 至 G1-07 逐项删除后转绿。

## G1-02 旧配置迁移

任务编号：G1-02

状态：PASS

修改文件：

- `web/config_migrations.py`
- `web/server.py`
- `tests/test_config_migrations.py`

迁移规则：

- 单个启用且配置 `default_model` 的非退役 Provider：自动替换聊天模型和所有 Ollama 路由引用。
- 多个候选或无候选 Provider：不猜测用户意图，移除失效引用并写入 `models.provider_setup_required=true`。
- 删除 `models.providers.ollama`、`local_deploy` 和 `provider_ollama.key`。
- 写入前生成 `.pre-local-ai-retirement.bak` 备份；配置写入或凭证删除失败时恢复原配置。
- 启动时在 ConfigService 单例首次加载前执行迁移，避免内存继续持有旧配置。
- 环境 Provider 和持久化 Provider 恢复均不再注册 Ollama。

验证：

```powershell
py -3.12 -m pytest tests/test_config_migrations.py tests/test_model_persistence_bugfix.py -q
py -3.12 -m ruff check web/config_migrations.py web/server.py tests/test_config_migrations.py
git diff --check
```

结果：

- 迁移与模型持久化回归：`19 passed`。
- Ruff：PASS。
- Diff whitespace：PASS。

已知非本次失败：

- `tests/test_provider_key_reading.py` 在当前 Windows DPAPI 可用环境仍假定 `encrypt()` 必然返回 `enc:v1:`，并在同一进程中受 DPAPI mock 状态影响；该问题不在 G1-02 修改面内，未通过削弱迁移测试规避。

剩余风险：

- G1-07 完成前，其他生产文件仍包含 Ollama 元数据、模型映射和降级探测特例。
- 迁移备份当前保留在配置文件同目录，发布文档需说明清理与人工恢复方式。

## G1-03 向量维度迁移工具

任务编号：G1-03

状态：PASS

修改文件：

- `scripts/migrate_vector_dimensions.py`
- `tests/test_vector_dimension_migration.py`

实现结果：

- 自动读取 `memories_vec`、`memories_child_vec`、`kg_entities_vec`、`kg_relations_vec` 的已有维度。
- 从主库完整文本源读取记录，而不是只迁移旧向量库已有 rowid，因此可补齐历史缺失向量。
- 启动前验证 `EMBED_API_KEY`、`EMBED_BASE_URL` 和 `EMBED_MODEL`。
- 在 `.rebuild` 临时库按目标维度创建四张 vec0 表并批量重编码。
- 每批成功后原子保存 checkpoint，失败后可从已完成位置继续。
- 对暂时性失败采用 1、2、4 秒指数退避，重试次数可配置。
- 替换前校验四表行数、向量维度，并对每张非空表执行一条自召回验证。
- 使用 `os.replace` 原子替换目标库；替换失败时原库保持不变。
- 原库备份固定保存为 `.pre-dimension-migration.bak`；成功后删除旧 NumPy 加速副本，下一次启动自动重建。

验证：

```powershell
py -3.12 -m pytest tests/test_vector_dimension_migration.py tests/test_config_migrations.py tests/test_model_persistence_bugfix.py -q
py -3.12 -m ruff check scripts/migrate_vector_dimensions.py tests/test_vector_dimension_migration.py
git diff --check
```

结果：

- 向量迁移、配置迁移和模型持久化回归：`24 passed`。
- Ruff：PASS。
- Diff whitespace：PASS。

环境变更：

- Python 3.12 用户环境按 `requirements.txt` 安装 `sqlite-vec 0.1.9`，用于真实 vec0 表迁移测试。

剩余风险：

- 工具要求迁移期间服务停机，避免活动连接、WAL 和并发写入破坏一致性。
- 实际用户数据库迁移仍需使用真实远程 Embedding 凭证执行；自动化测试使用确定性假 Embedder，不产生网络请求或费用。

## G1-04 前端本地部署退役

任务编号：G1-04

状态：PASS

修改范围：

- 删除 `web/frontend/src/views/LocalDeployView.vue`。
- 删除 `/local-deploy` 路由和共享侧栏入口。
- 删除中英文 `nav.localDeploy` 与 `localDeployView` 文案。
- 删除仅由本地部署入口使用的 `chip` 图标。
- 新增通用 `NotFoundView.vue` 和 catch-all 路由。
- 重新构建 `web/dist`，淘汰全部 `LocalDeployView-*` 哈希资产。

TDD 证据：

- 首次执行 `tests/test_frontend_local_deploy_retirement.py`：`5 failed`。
- 失败分别证明页面、路由导航、文案图标、404 和构建产物尚未退役。
- 实现和按顺序完成前端构建后：`5 passed`。

验证：

```powershell
npm run build
py -3.12 -m pytest tests/test_frontend_local_deploy_retirement.py tests/test_retired_edge_hardware_scan.py -q
py -3.12 -m ruff check tests/test_frontend_local_deploy_retirement.py
git diff --check
```

结果：

- Vite 生产构建：PASS，3979 个模块完成转换，5 张壁纸完成备份和恢复。
- G1-04 与边缘硬件退役回归：`9 passed`。
- 前端源码关键字扫描：无 `local-deploy`、`LocalDeploy`、`localDeployView` 或 `localDeploy` 残留。
- `web/dist/assets`：无 `LocalDeployView-*` 资产。
- 后端 `web/routers/local_deploy.py` 和 API 注册未修改，按阶段边界留给 G1-05。

已知提示：

- Vite 报告既有大 chunk 警告，最大为 `InsightView`，不影响构建成功，也不是 G1-04 引入的功能回归。
- pytest 继续报告既有 `pytest-asyncio` loop scope 弃用警告。

## G1-05 后端本地部署退役

任务编号：G1-05

状态：PASS

修改范围：

- 删除 `web/routers/local_deploy.py` 整个 Router。
- 删除 `web/server.py` 中的 Router 导入和 FastAPI 注册。
- 删除 `web/config_service.py` 默认配置中的 `local_deploy.mode`。
- 删除 `core/bootstrap.py` 对 `webui_overrides.json.local_deploy.mode` 的读取和日志。
- 删除 Router 专属的引擎启停、模式切换、设备探测和日志过滤 API。
- 调整边缘硬件退役测试，不再依赖已删除 Router 的展示型 GPU 项。

阶段边界：

- 保留 `memory/vector_store.py` 中的本地引擎实现和 server 预热，留给 G1-06。
- 保留 `core/capability_detector.py` 的 NVIDIA/AMD 检测。
- 保留 `utils/vision_service.py` 的 Vulkan GPU 选择能力。
- 继续由 G1-02 配置迁移删除旧用户配置中的 `local_deploy` 节点并生成备份。

TDD 证据：

- 首次执行后端退役门禁：`4 failed, 1 passed`。
- 失败覆盖 Router 文件、server 注册、默认配置、bootstrap 消费链和 OpenAPI 路径。
- 共享 GPU 能力门禁在 RED 阶段已通过。

验证：

```powershell
py -3.12 -m pytest tests/test_backend_local_deploy_retirement.py tests/test_config_migrations.py tests/test_frontend_local_deploy_retirement.py tests/test_retired_edge_hardware_scan.py tests/test_capability_detector.py tests/test_gpu_selection.py -q
py -3.12 -m ruff check core/bootstrap.py web/server.py web/config_service.py tests/test_backend_local_deploy_retirement.py tests/test_retired_edge_hardware_scan.py
git diff --check
```

结果：

- 后端/前端退役、配置迁移和共享 GPU 回归：`25 passed`。
- `create_app()` 与 OpenAPI 生成成功，六个 `/api/v1/local-deploy/*` 路径全部消失。
- 生产 Python 扫描无 `local_deploy_router`、`web.routers.local_deploy` 或 `/local-deploy` 残留。
- Ruff：PASS。
- Diff whitespace：PASS。

已知提示：

- pytest 继续报告既有 `pytest-asyncio` loop scope 弃用警告。

## G1-06 本地 Embedding 退役

任务编号：G1-06

状态：PASS

修改范围：

- 删除 `memory/local_embed.py`、`models/bge-small-zh-v1.5/`、`scripts/rebuild_vec_local.py` 和 `tests/test_local_embed_mode.py`。
- 删除 `VectorStore` 的本地模式、ONNX Provider、运行时切换、本地预热和本地回退。
- 删除 `onnxruntime`、`tokenizers`、PyInstaller 收集和发布产物校验。
- 固定记忆向量、工具向量和维度迁移调用 `https://api.siliconflow.cn/v1`，默认模型为 `BAAI/bge-m3`。
- 删除 `EMBED_BASE_URL`、`EMBED_MODE` 和 `LOCAL_EMBED_*`；无 `EMBED_API_KEY` 时不初始化向量存储。
- 保留 SQLite、sqlite-vec 和 NumPy 检索层，它们只存储和搜索 SiliconFlow API 返回的向量。

TDD 证据：

- 扩展 SiliconFlow-only 门禁后首次执行：`2 failed, 5 passed`。
- 失败准确捕获 `SETUP.md`、`USAGE.md`、向量基准脚本和 Tool Search 中的非固定服务商入口。
- 删除残留配置并固定 Tool Search 客户端后，退役与工具混合检索测试转绿。

验证：

```powershell
py -3.12 -m pytest tests/test_local_embedding_retirement.py tests/test_vector_dimension_migration.py tests/test_kg_v2_search.py tests/test_context_governance.py tests/test_tool_search_hybrid.py tests/test_backend_local_deploy_retirement.py tests/test_frontend_local_deploy_retirement.py tests/test_config_migrations.py tests/test_model_persistence_bugfix.py tests/test_retired_edge_hardware_scan.py -q
py -3.12 -m ruff check memory/vector_store.py core/bootstrap.py web/server.py scripts/migrate_vector_dimensions.py scripts/bench_vec_search.py tool_engine/tool_search.py tests/test_local_embedding_retirement.py tests/test_vector_dimension_migration.py tests/test_kg_v2_search.py tests/test_tool_search_hybrid.py
py -3.12 -m py_compile memory/vector_store.py core/bootstrap.py web/server.py scripts/migrate_vector_dimensions.py tool_engine/tool_search.py
git diff --check
```

结果：

- 退役与 Tool Search 专项回归：`18 passed`。
- 完整 G1-06 相关回归：`69 passed`。
- Ruff：PASS，`All checks passed!`。
- Python 编译检查：PASS。
- Diff whitespace：PASS。
- 生产、配置、打包和发布范围扫描无 `EMBED_MODE`、`LOCAL_EMBED_*`、`EMBED_BASE_URL`、本地 Provider、BGE-small、ONNX Runtime、tokenizers 或 OpenAI 默认向量模型残留。

剩余风险：

- 真实 SiliconFlow 调用依赖用户凭证、网络和服务配额；自动化测试不发起收费网络请求。

## G1-07 Ollama 退役

任务编号：G1-07

状态：PASS

修改范围：

- 删除 Provider metadata、默认模型、模型名映射、跨 Provider fallback 和 token cap 环境覆盖。
- 删除 ModelRouter 的模型翻译、零成本定价、默认模型与凭证池格式特判。
- 删除 Setup 向导字段、连通性测试、无 Key 占位凭证和自动注册。
- 删除 server 降级模式与凭证池中的环境注册逻辑。
- 删除模型发现中的永久免费特判。
- 删除 `.env.example` 全部专属变量，并清理当前架构文档中的可选部署表述。
- 保留 `web/config_migrations.py` 与 `tests/test_config_migrations.py`，只用于迁移并清除旧用户配置。
- 保留通用自定义 Provider 的本地 URL 安全校验，但移除专属品牌耦合。

TDD 证据：

- 扩展生产扫描范围后首次执行：`1 failed, 1 passed`。
- 门禁捕获 89 处生产残留，覆盖环境、metadata、路由、Setup、凭证池、模型发现和当前架构文档。
- 实现后同一门禁：`2 passed`。

验证：

```powershell
py -3.12 -m pytest tests/test_local_ai_retirement.py tests/test_config_migrations.py tests/test_degraded_mode_any_provider.py tests/test_model_health.py tests/test_model_router_truncation.py tests/test_model_route_validation.py tests/test_model_persistence_bugfix.py tests/test_preference_discovery.py -q
py -3.12 -m ruff check model_router.py web/server.py web/routers/setup.py web/routers/model_discovery.py web/routers/models.py utils/credential_pool.py security/ssrf_guard.py setup_wizard.py tests/test_local_ai_retirement.py tests/test_degraded_mode_any_provider.py
py -3.12 -m py_compile model_router.py web/server.py web/routers/setup.py web/routers/model_discovery.py web/routers/models.py utils/credential_pool.py security/ssrf_guard.py setup_wizard.py
git diff --check
```

结果：

- G1-07、配置迁移、ModelRouter、模型发现及 G1-04 至 G1-06 联合回归：`69 passed`。
- Ruff：PASS，`All checks passed!`。
- Python 编译与 Provider metadata JSON 解析：PASS。
- Diff whitespace：PASS。
- 生产、配置、前端、脚本、发布和当前文档范围扫描：零专属引用。

已知非本次失败：

- `tests/test_provider_key_reading.py` 在 Windows DPAPI 可用环境仍假定加密结果必为 `enc:v1:`，并受同进程 DPAPI mock 状态影响；本轮执行结果为该文件 `2 failed, 4 passed`，其余选择集 `52 passed`。该问题在 G1-02 已记录，与 Ollama 退役无关。

## 基线修复

状态：PASS

根因：

1. `websockets 13.1` 支持从 `websockets.exceptions` 直接导入异常类，但不保证 `websockets.exceptions` 是顶层包属性；`cli.py` 使用了不稳定访问方式。
2. 工作区集成测试硬编码 `/tmp/any.txt`，Windows 上该路径不属于 pytest 临时工作区，导致安全沙箱先于工作区边界拒绝请求。

修改文件：

- `cli.py`
- `tests/test_cli_ws_keepalive.py`
- `tests/test_tool_executor_workspace.py`

验证：

```powershell
py -3.12 -m pytest tests/test_cli_ws_keepalive.py tests/test_tool_executor_workspace.py -q --tb=short
py -3.12 -m pytest tests -k "auth or websocket or ws_hub or chat" -q --tb=short
py -3.12 -m ruff check cli.py tests/test_cli_ws_keepalive.py tests/test_tool_executor_workspace.py
```

结果：

- 目标测试：`23 passed`。
- 基线选择集：`70 passed, 1 skipped, 2868 deselected`。
- Ruff：PASS。

## G0-03 决策冻结

任务编号：G0-03

状态：PASS

确认结果：

- `docs/mobile/` 六份权威文档已阅读。
- 旧 Compose 业务 UI 方案已被 v2 取代。
- Termux 仅允许承载远程 CLI，不运行端内 AgentCore。
- 本地 AI、ONNX 本地 Embedding、内置 BGE 和 Ollama 必须退役。
- 除退役项外，现有业务能力入口全部保留并通过方案 C 分层。

架构复述：

> 移动端复用共享 Vue WebUI，通过 Android 安全系统壳连接远端 FastAPI/AgentCore，并可选择只承载远程 CLI 的终端运行时；端内不运行 AgentCore、本地模型或 Ollama。

关联 ADR：ADR-MOB2-001 至 ADR-MOB2-006

## G0-02 基线证据

任务编号：G0-02

状态：PASS WITH KNOWN FAILURES

修改文件：

- `docs/mobile/implementation-plan-v2.md`
- `docs/mobile/test-evidence.md`

测试命令：

```powershell
py -3.12 scripts/check_version_sync.py --ci
py -3.12 -m pytest tests/test_smoke.py -q --tb=short
py -3.12 -m pytest tests -k "auth or websocket or ws_hub or chat" -q --tb=short
npm ci
npm run build
```

测试结果：

- 版本同步：PASS，全部为 `0.5.70`。
- Smoke：PASS，`17 passed`。
- Auth/WS/Chat 相关选择集：`66 passed, 1 skipped, 4 failed, 2868 deselected`。
- 前端依赖：PASS，按 `package-lock.json` 安装 129 个包。
- 前端构建：PASS，3979 modules transformed。
- 构建警告：`InsightView`、Three.js 等 chunk 超过 500 kB；属于既有性能基线。
- 环境警告：`NODE_TLS_REJECT_UNAUTHORIZED=0` 禁用了 npm TLS 校验。

既有失败：

1. `tests/test_cli_ws_keepalive.py` 三项失败：当前安装的 `websockets` 不暴露 `websockets.exceptions` 属性，测试和 `cli.py` 的访问方式与运行版本不兼容。
2. `tests/test_tool_executor_workspace.py::TestExecuteIntegration::test_unauthorized_execute_returns_fail`：Windows 环境下 `/tmp/any.txt` 先被安全沙箱拒绝，返回“路径不被允许”，旧断言期待“工作目录”。
3. 以上失败在本轮生产代码修改前产生，已与后续重构失败隔离。

引用快照：

- 扫描目录：`web`、`memory`、`core`、`config`、`tests`、`scripts`、`.github`。
- 扫描模式：Ollama、本地部署、本地 Embedding、BGE、ONNX、tokenizers。
- 当前命中文件：23。
- 当前命中行：193。
- 生产路由：20 个，其中登录/设置流程 3 个、业务路由 17 个；`local-deploy` 是待退役业务路由。
- 主要命中：`LocalDeployView.vue` 43 行、`web/server.py` 25 行、`web/routers/local_deploy.py` 21 行、`web/routers/setup.py` 16 行、发布工作流 16 行、`memory/local_embed.py` 12 行。

产物路径：

- `docs/mobile/test-evidence.md`
- 前端构建结果由验证后恢复，未保留在 Git 工作树中。

剩余风险：

- 基线选择集不是全量 2939 项测试；G1 完成后仍需运行目标测试与全量回归。
- 既有 4 项失败必须继续作为已知基线，除非单独修复。
- npm TLS 环境设置必须在发布门禁前清理。

关联 ADR：ADR-MOB2-001 至 ADR-MOB2-006

## G4 Pages, terminal, and wallpaper

### G4-01 Responsive page coverage

Task: G4-01

Status: PASS

Changed files:

- `web/frontend/src/styles/mobile-pages.css`
- `web/frontend/src/App.vue`
- `web/frontend/src/styles/mobile-pages.test.ts`
- `web/frontend/src/test-setup.ts`
- `web/frontend/vite.config.ts`
- `tests/test_g4_mobile_frontend_contract.py`

Evidence:

- Shared mobile rules explicitly cover all 16 production routes.
- Phone layouts are single-column, tablet layouts retain useful density, and desktop rules are not overridden.
- Tables and tabs use controlled horizontal scrolling; mobile modals and workflow editing use full-screen or near-full-screen layouts.
- Primary touch targets are at least 48px and include safe-area, focus-visible, landscape, and reduced-motion rules.
- Playwright captured all 16 routes at 360x800, 390x844, 412x915, 844x390, 768x1024, and 1440x900.

Commands:

```powershell
cd web/frontend
npm run typecheck
npm test
npm run build
cd ../..
py -3.12 -m pytest tests/test_g4_mobile_frontend_contract.py -q
```

Results:

- TypeScript: PASS.
- Vitest: `27 passed`, including 3 responsive-page contract tests.
- Vite production build: PASS; 3994 modules transformed.
- Python frontend contract: `3 passed`.
- Artifacts: `output/playwright/g4-routes-*-contact.png` and `output/playwright/g4-viewport-contact-sheet.png`.

### G4-02 Mobile terminal sheet

Task: G4-02

Status: PASS

Changed files:

- `web/frontend/src/components/chat/ChatTerminal.vue`
- `web/ws_hub.py`
- `tests/test_g4_terminal_sessions.py`
- `web/frontend/src/i18n/zh.ts`
- `web/frontend/src/i18n/en.ts`

Evidence:

- Desktop keeps the right-side terminal; mobile uses a draggable bottom sheet with 50 and 90 percent snap points.
- VisualViewport, orientation, and safe-area changes only fit/resize the current xterm session and do not regenerate its SID.
- `v-show` preserves the xterm DOM and multiple sessions; closing an active session requires confirmation.
- A real component unmount sends terminal kill; WebSocket disconnect remains the server-side fallback.
- The server validates SID format, connection ownership, shell allowlist, input bytes, terminal dimensions, and per-connection/global session limits.
- Windows recursively terminates the process tree with psutil; Unix terminates the PTY process group and reaps it with waitpid.

Commands:

```powershell
py -3.12 -m pytest tests/test_g4_terminal_sessions.py tests/test_ws_broadcast_backpressure.py tests/test_ws_heartbeat.py -q
```

Results:

- Terminal lifecycle/security: `4 passed`.
- WebSocket regression: `5 passed`.
- Artifact: `output/playwright/terminal-sheet-390x844.png`.

### G4-03 Wallpaper data extension

Task: G4-03

Status: PASS

Changed files:

- `web/wallpaper_config.py`
- `agent_dispatcher.py`
- `web/agent_registry.py`
- `web/config_service.py`
- `web/routers/agents.py`
- `web/frontend/src/stores/agents.ts`
- `web/frontend/src/views/AgentsView.vue`
- `tests/test_g4_wallpaper_config.py`

Evidence:

- Added `wallpaper_focus`, `wallpaper_overlay`, and `wallpaper_motion` with defaults `{x: 0.5, y: 0.5}`, `0.28`, and `auto`.
- Legacy records containing only a wallpaper URL receive defaults without changing the URL.
- API validation rejects out-of-range focus/overlay values and unknown motion modes.
- Main-agent writes use `ConfigService.set_many()` so a save failure rolls back all wallpaper fields.
- Upload writes the new file first and removes older uploads only after configuration succeeds; failure removes the new file and keeps the previous wallpaper.
- The Agent editor supports click-to-focus, X/Y sliders, overlay strength, motion choice, and top/content/bottom obstruction preview.

Command:

```powershell
py -3.12 -m pytest tests/test_g4_wallpaper_config.py -q
```

Result: `9 passed`.

### G4-04 Wallpaper rendering

Task: G4-04

Status: PASS

Changed files:

- `web/frontend/src/components/layout/AgentBackdrop.vue`
- `web/frontend/src/stores/agents.ts`
- `tests/test_g4_mobile_frontend_contract.py`

Evidence:

- The background is a fixed `100lvh` layer and does not track VisualViewport keyboard height.
- Wallpaper focus maps to `background-position`; global tint plus top/content/bottom local masks protect text contrast.
- High/medium/low tiers disable drift, transitions, and extra layers based on GPU marker, device memory, and CPU count.
- `prefers-reduced-motion` and the persisted motion preference both disable decorative motion.
- `memorypressure`, hidden visibility, and `pagehide` release preload references and inactive layers.

Final verification:

- Ruff: PASS.
- Python targeted suite: `32 passed`.
- TypeScript: PASS.
- Vitest: `27 passed`.
- Production build: PASS.
- `git diff --check`: PASS.

Remaining risk:

- Playwright used authenticated API mocks to validate layout. Real Android IME, cutout, large-data, and OS memory-pressure behavior remains part of G6-02/G6-03 device validation.
- Vite still reports the pre-existing large-chunk warning (largest chunk: InsightView); it does not fail the G4 build.

## G2-05 to G2-09 Provider completion

Date: 2026-08-10

Status: PASS

Scope:

- G2-05: reference collection covers configured/runtime model routes, configured/runtime chat model, and all agents; referenced providers return a conflict with references, replacement candidates, and migration operations before deletion.
- G2-06: discovery caches each provider independently with separate success/failure TTLs, returns per-provider status and warnings, merges manual model IDs, classifies non-chat models, and records declared/inferred/user capability evidence.
- G2-07: diagnostics report DNS, TLS, authentication, discovery, and chat stages with stage-specific timeouts; temporary clients close explicitly and upstream response bodies are not returned.
- G2-08: the Provider UI is split into list, editor, diagnostics, model picker, and references components; API keys are replace-only, normalized URLs are shown, test-before-save and manual IDs are supported, and the mobile editor uses a full-screen `100dvh` layout.
- G2-09: Provider backend and frontend gates run strictly in CI without `continue-on-error`.

Primary changed files:

- `web/provider_references.py`
- `web/provider_diagnostics.py`
- `web/_discovery_cache.py`
- `web/routers/model_discovery.py`
- `web/routers/models.py`
- `web/frontend/src/stores/providers.ts`
- `web/frontend/src/components/providers/ProviderList.vue`
- `web/frontend/src/components/providers/ProviderEditor.vue`
- `web/frontend/src/components/providers/ProviderDiagnostics.vue`
- `web/frontend/src/components/providers/ProviderModelPicker.vue`
- `web/frontend/src/components/providers/ProviderReferencesDialog.vue`
- `web/frontend/src/views/ModelsView.vue`
- `.github/workflows/ci-tests.yml`

Automated tests:

- `tests/test_g2_05_provider_references.py`
- `tests/test_g2_06_provider_discovery.py`
- `tests/test_g2_07_provider_diagnostics.py`
- `tests/test_g2_09_provider_ci_contract.py`
- `web/frontend/src/components/providers/ProviderComponents.test.ts`

Commands and results:

```powershell
py -3.12 -m pytest tests/test_g2_01_error_protocol.py tests/test_g2_01_provider_protocol.py tests/test_g2_02_provider_urls.py tests/test_g2_03_safe_outbound.py tests/test_g2_04_provider_application_service.py tests/test_g2_05_provider_references.py tests/test_g2_06_provider_discovery.py tests/test_g2_07_provider_diagnostics.py tests/test_g2_09_provider_ci_contract.py -q
```

Result: `154 passed`.

```powershell
py -3.12 -m ruff check web/_discovery_cache.py web/provider_references.py web/provider_diagnostics.py web/routers/model_discovery.py web/routers/models.py tests/test_g2_05_provider_references.py tests/test_g2_06_provider_discovery.py tests/test_g2_07_provider_diagnostics.py tests/test_g2_09_provider_ci_contract.py tests/test_g2_01_error_protocol.py
```

Result: PASS.

```powershell
cd web/frontend
npm run typecheck
npm test
npm run build
```

Results: TypeScript PASS; Vitest `33 passed`; production build PASS. Vite retains the pre-existing large-chunk warning, which is non-blocking for G2.

Additional checks:

- CI workflow YAML parse: PASS.
- `git diff --check`: PASS.
- A 100-run diagnostics resource test verifies every temporary client is closed (`opened == closed == 100`).

Environment note:

- The validated backend environment is Python 3.12. The machine's separate Python 3.13 environment lacks the optional `prometheus_client` package, so two server-import tests fail there before exercising G2 behavior; this is an environment dependency issue, not a G2 regression.

## G5 Android system shell execution refresh

Date: 2026-08-10

Status: G5-01 through G5-04 PASS; G5-05 and G5-06 BLOCKED by external P0 gates.

Environment:

- JDK: OpenJDK 17.0.14 (`C:\Users\lenovo\.codex\tools\jdk17-conda\Library`).
- Gradle: 8.11.1.
- Android SDK: 35 (`D:\AndroidSDK`); NDK 22.1.7171670 is available for the isolated terminal research module.
- The repository was temporarily exposed through ASCII drive `X:` because Kotlin/Gradle caches on this Windows host could not reliably mix the non-ASCII workspace path with earlier `W:`/`X:` cache roots. This mapping is only a local verification workaround and is not part of the project.

Corrections made during this refresh:

- Replaced the hard-coded Android web asset version with the canonical `[project].version` from `pyproject.toml`; CI resolves the same version through `scripts/project_version.py`.
- Restored WebView save/restore before loading a fresh shell and retained deep-link precedence.
- Added document-start runtime configuration so bundled assets keep the trusted `appassets` origin while REST and WebSocket clients connect to the build-variant remote endpoint.
- Added credentialed CORS for the immutable Android asset origin, REST support for the five-minute short handle, and Android WebSocket authentication through a subprotocol header instead of a URL query.
- Completed the fixed Bridge contract for `authenticate`, `restoreSession`, `clearSession`, file selection, sharing, and disabled terminal operations.
- Wired Android Keystore token storage to five-minute WebView session handles without returning the bearer token to JavaScript or persisting it in Web Storage.
- Bound JavaScript replies to the injected `XiaodaNative.onmessage` channel, added request correlation and timeout cleanup, and restored the native session before route/auth decisions.
- Corrected the native file bridge so only bounded, content-inspected bytes are returned to the Web layer.
- Added the pinned JVM `org.json:json:20251224` test dependency so `AssetManifestVerifier` exercises real JSON behavior instead of Android's unmocked stub.
- Hardened remote CLI endpoint policy against userinfo, query strings, fragments, private/local endpoints, invalid nonce input, and invalid protocol versions.
- Kept the Termux candidate as an isolated research AAR: the app has no dependency on `:feature:terminal-runtime`, all public runtime methods return `disabled/canStart=false`, and the three APKs contain no Termux entries.
- Removed APK scanner false positives caused by random file-suffix bytes inside DEX data while retaining path-based runtime payload rejection and content-based runtime/secret scanning.

Android build command:

```powershell
$env:JAVA_HOME='C:\Users\lenovo\.codex\tools\jdk17-conda\Library'
$env:ANDROID_HOME='D:\AndroidSDK'
$env:ANDROID_SDK_ROOT='D:\AndroidSDK'
X:\android\gradlew.bat -p X:\android lint test assembleDebug assembleStaging assembleRelease '-Pkotlin.incremental=false' --no-build-cache --no-configuration-cache --no-daemon --max-workers=4
```

Result: `BUILD SUCCESSFUL in 1m 54s`; `514 actionable tasks` (`93 executed`, `421 up-to-date`). Targeted forced JVM/app/terminal checks also passed with incremental Kotlin compilation disabled to avoid stale mixed-root caches.

Security, frontend, and build contracts:

```powershell
python -m unittest discover -s android/scripts -p "test_*.py" -v
python android/scripts/verify_web_assets.py android/app/build/generated/webAssets "$(python scripts/project_version.py)"
python android/scripts/verify_apk.py --source-root android android/app/build/outputs/apk/debug/app-debug.apk android/app/build/outputs/apk/staging/app-staging.apk android/app/build/outputs/apk/release/app-release.apk
py -3.12 -m pytest tests/test_android_webview_auth.py tests/test_metrics_endpoint.py tests/test_rate_limit_middleware.py -q
py -3.12 scripts/check_version_sync.py --ci
py -3.12 -m ruff check scripts/project_version.py tests/test_android_webview_auth.py web/routers/auth.py web/ws_hub.py web/server.py --select=E9,F63,F7,F82
cd web/frontend
npm run typecheck
npm test
npm run build
```

Results:

- Android Python contracts: `32 tests`, PASS.
- Bundled web asset manifest and hashes: PASS.
- Android source tree and debug/staging/release APK scans: PASS.
- APK archive inspection: no Termux path or library entries in debug, staging, or release.
- Android WebView auth plus middleware regressions: `23 passed`.
- Frontend TypeScript: PASS; G5-owned platform tests: `7 passed`; the combined current-worktree suite: `44 passed`; production build: PASS.
- Version synchronization (`0.5.70`), strict Ruff subset, and `git diff --check`: PASS.
- Local connected Android tests were not run because no device or AVD is installed; `.github/workflows/android-apk.yml` retains `connectedCheck` as a blocking emulator CI gate.

Fresh APK artifacts:

- `android/app/build/outputs/apk/debug/app-debug.apk`: 9,577,283 bytes; SHA-256 `A7885936F361A531EB4178DE57457DC402E5BE2E99DE81B325E8745DBE2F0CC7`.
- `android/app/build/outputs/apk/staging/app-staging.apk`: 8,519,992 bytes; SHA-256 `7B449A5869337FE84739F011631C641C7C8E335BBC3451FBF91695D4D0626FAF`.
- `android/app/build/outputs/apk/release/app-release.apk`: 6,429,142 bytes; SHA-256 `8D0B265702C1E172EC4786CCAA487491A1C64B44ADE980B9469A81BCEAE8994C`.

Remaining P0 blockers:

- The pinned Termux candidate and native shim are research inputs only; component/bootstrap approval has not been granted for product packaging.
- Legal license obligations and target-store policy review have no written approval.
- Installed/unpacked size and real device process-tree cleanup still require approved runtime packaging and device evidence.
- Consequently G5-05 and G5-06 remain blocked, `canStart=false`, `TERMINAL_RUNTIME_ENABLED=false` for debug/staging/release, and the application APKs do not link or package the terminal runtime module.

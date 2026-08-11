# 移动端架构重构实施计划 v2

## 0. 执行规则

### 0.1 状态

- `[ ]` 未开始。
- `[~]` 进行中。
- `[x]` 已完成且有证据。
- `[!]` 阻塞。
- `[-]` 取消并有 ADR。

### 0.2 每项关闭证据

每个任务必须记录：

```text
任务编号：
状态：
修改文件：
测试命令：
测试结果：
产物路径：
剩余风险：
关联 ADR：
```

### 0.3 Git 规则

- 每一阶段单独分支或独立逻辑提交。
- 不把删除本地 AI、Provider 重构和移动 UI 混进一个不可审查提交。
- 未经用户明确要求不得提交或推送。
- 提交前检查暂存 diff、测试证据和秘密扫描。

## G0 文档与基线冻结

### G0-01 确认工作树

- [x] 运行 `git status --short --branch`。
- [x] 记录当前分支、远程和未跟踪文件。
- [x] 不覆盖 `.superpowers/brainstorm` 和历史文档。
- [x] 确认实施是在目标仓库而不是旧 worktree。

**验收**：工作树来源明确，非本任务改动有清单。

### G0-02 建立基线证据

- [x] 运行版本同步检查。
- [x] 运行后端核心测试。
- [x] 运行前端 build。
- [x] 记录既有失败和环境问题。
- [x] 保存当前路由、Provider、本地 AI 引用扫描结果。

**停止条件**：无法区分既有失败与新增失败。

### G0-03 冻结决策

- [x] 阅读 `docs/mobile` 六份文档。
- [x] 确认旧移动方案已被 v2 取代。
- [x] 移动端终端及其研究 runtime 均已取消；桌面 Web 终端保留（ADR-MOB2-010）。
- [x] 确认本地 AI 与 Ollama 都要删除。
- [x] 确认所有其他功能入口保留。

**验收**：实现者可以用一句话复述目标架构，且不包含端内 AgentCore。

## G1 本地 AI 与 Ollama 退役

### G1-01 先写退役扫描测试

- [x] 新建 `tests/test_local_ai_retirement.py`。
- [x] 定义生产目录扫描范围。
- [x] 定义历史文档和迁移测试 allowlist。
- [x] 让测试先因现有引用失败。

**验收**：测试能同时捕获 Ollama、本地部署页面、本地 Embedding 和模型资产。

### G1-02 设计配置迁移

- [x] 列出所有 Ollama 与 local deploy 配置键。
- [x] 定义单 Provider、多 Provider、无 Provider 三种迁移结果。
- [x] 写配置备份和回滚测试。
- [x] 写占位凭证删除测试。
- [x] 写启动恢复不再注册 Ollama 的测试。

**验收**：旧用户配置升级后不会指向不存在的 Provider。

### G1-03 实现向量迁移工具

- [x] 读取向量维度和表清单。
- [x] 验证远程 Embedding 配置。
- [x] 备份数据库。
- [x] 在临时库批量重编码。
- [x] 实现断点和限流退避。
- [x] 校验行数、向量和抽样召回。
- [x] 原子替换并支持恢复。

**验收**：512→目标维度迁移成功；中途失败恢复原库。

### G1-04 删除前端本地部署

- [x] 删除路由。
- [x] 删除侧栏入口。
- [x] 删除页面。
- [x] 删除中英文文案。
- [x] 删除移动能力表中的相关候选项；当前没有独立能力表，已从共享导航事实源删除。
- [x] 验证深链访问返回明确 404 或迁移提示。

**验收**：桌面和移动导航均不存在本地部署入口。

### G1-05 删除后端本地部署

- [x] 删除 router 导入和注册。
- [x] 删除 local deploy API。
- [x] 删除 local deploy config schema。
- [x] 删除本地引擎启动、停止和设备探测 API；VectorStore 内部实现按阶段边界留给 G1-06。
- [x] 删除日志过滤路径。

**验收**：`/api/v1/local-deploy/*` 不再存在，服务正常启动。

### G1-06 删除本地 Embedding

- [x] 删除 LocalEmbedProvider。
- [x] 删除 VectorStore 本地分支。
- [x] 删除模型资产。
- [x] 删除 ONNX/tokenizers 专属依赖。
- [x] 删除发布物模型检查。
- [x] 调整 bootstrap 为 SiliconFlow/disabled。
- [x] 删除旧重建脚本并保留 SiliconFlow 远程迁移脚本。
- [x] 固定向量 API 为 `https://api.siliconflow.cn/v1`，删除 `EMBED_BASE_URL`。
- [x] 无 `EMBED_API_KEY` 时关闭语义检索，不回退本地模型。

**验收**：安装包、Docker 镜像和源码不包含 ONNX 模型与 runtime。

### G1-07 删除 Ollama

- [x] 删除 metadata。
- [x] 删除 Setup 字段和测试。
- [x] 删除 server 自动注册和恢复。
- [x] 删除 ModelRouter 特判。
- [x] 删除免费成本与发现特判。
- [x] 删除 `.env.example` 变量。
- [x] 更新当前文档。

**验收**：生产扫描零命中；旧配置迁移测试通过。

### G1-08 回归

- [x] 启动无远程 Embedding 的降级模式。
- [x] 启动有远程 Embedding 的完整模式。
- [x] 验证文本记忆仍可用。
- [x] 验证语义检索状态可见。
- [x] 验证其他 Provider 不受影响。

**门禁**：G1 全部通过才能开始 Provider 大重构。

**关闭证据**：启动模式验收 `5 passed`，后端全量回归 `2966 passed, 8 skipped`，严格 Ruff、Python compileall、版本同步和前端生产构建通过；详见 `test-evidence.md`。

## G2 自定义服务商重构

### G2-01 错误协议

- [x] 定义稳定错误码、stage 和 retryable。
- [x] 统一 FastAPI 错误外形。
- [x] 修改前端 API 读取顶层 `message`。
- [x] 保持旧客户端可读 `detail` 的兼容期。

**验收**：认证、超时、DNS、TLS、限流、模型不存在和 SSRF 均有稳定结果。

**关闭证据**：统一处理 AppException、HTTPException、请求校验、未知异常和限流中间件；协议矩阵与历史兼容测试通过，前端生产构建通过，详见 `test-evidence.md`。

### G2-02 URL 规范化

- [x] 明确 base URL 是 API 根还是站点根。
- [x] 处理末尾斜杠和已有 `/v1`。
- [x] 拒绝 userinfo、非法端口和危险编码。
- [x] 支持自定义路径前缀。
- [x] 保证 discover 与 chat 使用同一规范化结果。

**验收**：根域、`/v1`、路径前缀、IPv6 和非法输入表驱动测试通过。

**关闭证据**：统一 API 根规范化用于 Provider CRUD、OpenAI/Anthropic chat、discover、probe、启动恢复、凭证池和子 Agent；表驱动及完整回归通过，详见 `test-evidence.md`。

### G2-03 安全出站客户端

- [x] 将 DNS 校验和真实连接合并。
- [x] 使用 pinned IP，同时保持原 Host/SNI。
- [x] 禁止跨主机重定向。
- [x] 收紧私网和宿主别名豁免。
- [x] 对端口和协议建立 allowlist。
- [x] 统一用于发现、探针和聊天。

**验收**：DNS rebinding 真实连接测试通过。

**关闭证据**：安全传输层在真实 `connect_tcp()` 前异步解析并校验全部 A/AAAA 结果，只拨号 pinned IP，同时保持原 Provider `Host` 与 TLS SNI；跨 origin 重定向、环境代理、未授权私网、明文公网 HTTP 和非 allowlist 端口均被阻断。discover、probe、OpenAI/Anthropic chat、ModelRouter、子 Agent、XiaoliAgent 与 Transport 共用安全入口；专项 `16 passed`、相关回归 `129 passed`、后端全量 `3058 passed, 8 skipped`、前端生产构建及静态门禁通过，详见 `test-evidence.md`。

### G2-04 Provider 应用服务

- [x] 抽离 repository、credential store 和 runtime registry。
- [x] 实现创建事务。
- [x] 实现更新事务。
- [x] 实现删除事务。
- [x] 故障注入每个阶段。
- [x] 验证无孤儿配置、密钥和客户端。

**验收**：所有故障点回到操作前状态。

**关闭证据**：Provider 创建、更新、独立 Key 更新、启用/禁用和删除统一由应用服务按 ID 串行协调配置、原子凭证文件、运行时客户端与凭证池；逐阶段故障注入验证失败恢复操作前四态，专项 `24 passed`、G2-01 至 G2-04 及相关回归 `132 passed`、后端全量 `3081 passed, 8 skipped`，前端生产构建及静态门禁通过，详见 `test-evidence.md`。

### G2-05 引用完整性

- [x] 收集 RouteRegistry 引用。
- [x] 收集聊天模型引用。
- [x] 收集全部 Agent 配置引用。
- [x] 删除前返回引用列表。
- [x] 禁用时立即停止新调用。

**验收**：被引用 Provider 不可被静默删除或假禁用。

### G2-06 模型发现

- [x] 按 Provider 分片缓存。
- [x] 区分成功和失败 TTL。
- [x] 返回每个 Provider 状态。
- [x] 支持手动模型。
- [x] 分类展示非聊天模型。
- [x] 标记能力证据来源。

**验收**：一个 Provider 故障不影响其他 Provider，且错误不再表现为空模型列表。

### G2-07 连接测试

- [x] 分开验证 DNS、TLS、认证、模型发现和聊天 probe。
- [x] 临时客户端显式关闭。
- [x] 增加分阶段超时。
- [x] 过滤上游敏感正文。
- [x] 连续执行 100 次资源不增长。

**验收**：UI 能定位失败阶段，服务端无连接泄漏。

### G2-08 Provider 前端

- [x] 拆分 Provider 列表、编辑器、诊断和模型选择器。
- [x] API Key 只替换不回填。
- [x] 展示规范化 URL。
- [x] 支持先测试后保存。
- [x] 支持手动模型 ID。
- [x] 显示引用冲突和迁移操作。
- [x] 提供移动全屏编辑体验。

**验收**：360dp 下可以完成创建、测试、发现、保存、编辑、禁用和删除。

### G2-09 Provider CI

- [x] 新增 CRUD 集成测试。
- [x] 新增事务故障注入。
- [x] 新增安全出站测试。
- [x] 新增发现与错误映射测试。
- [x] 加入 strict CI。

**门禁**：关键 Provider 测试不得 continue-on-error。
**G2 closure evidence (2026-08-10)**: Provider reference protection, per-provider discovery cache, staged diagnostics, split responsive UI, and strict CI gates are implemented. The G2 backend suite passes with `154 passed`; Ruff and workflow YAML validation pass; frontend typecheck, all `33` Vitest tests, and the production build pass. Detailed commands and file-level evidence are recorded in `test-evidence.md`.

## G3 共享导航与移动壳

### G3-01 导航事实源

- [x] 新建 `capabilities.ts`。
- [x] 录入全部现有生产路由。
- [x] 为每项定义分组、排序、图标和移动位置。
- [x] SideBar 改为读取能力表。
- [x] 路由与能力表建立一致性测试。

**验收**：新增或删除路由时一致性测试会失败。

### G3-02 响应式壳

- [x] 将桌面与移动壳统一为单一 ResponsiveShell，避免两套壳漂移。
- [x] 实现移动壳结构与桌面壳结构的稳定切换。
- [x] AppLayout 只负责响应式壳和共享背景。
- [x] 宽度变化不销毁业务 Store。
- [x] 横竖屏切换不丢失页面状态。

**验收**：断点切换不重复初始化 Chat 或 WS，移动断点不挂载终端。

### G3-03 底部五导航

- [x] 聊天、Agent、记忆、工具、设置。
- [x] 使用极光玻璃 SVG。
- [x] 48dp 热区和安全区。
- [x] 选中、按下、禁用和焦点状态。
- [x] 屏幕阅读器标签。

**验收**：单手可达、无误触、状态不只靠颜色。

### G3-04 全部能力抽屉

- [x] 左上角入口。
- [x] 四类能力分组。
- [x] 支持搜索。
- [x] 当前路由高亮。
- [x] 跳转后自动关闭。
- [x] 所有现有页面均可达。

**验收**：路由覆盖测试为 100%。

### G3-05 快捷状态

- [x] 当前 Agent。
- [x] WS 连接状态。
- [x] 当前 Provider/模型。
- [x] 通知和快捷设置。
- [x] 离线、降级和模型未配置状态。

**验收**：状态来源真实，不用静态假数据。

任务编号：G3-01 至 G3-05
状态：已完成
修改文件：`web/frontend/src/navigation/*`、`web/frontend/src/components/layout/*`、`web/frontend/src/composables/*`、`web/frontend/src/routes.ts`
测试命令：`npm test -- --reporter=verbose`；`npm run typecheck`；`npm run build`；`git diff --check`
测试结果：5 个测试文件、24 个测试通过；类型检查、生产构建和 diff 检查通过；测试输出无失败
产物路径：`web/dist/`
剩余风险：生产构建仍报告既有大 chunk 警告；根据用户批准的无浏览器验收例外，本阶段以路由覆盖、响应式规则、组件生命周期、键盘焦点、typecheck 和构建替代多视口截图，真实设备返回手势留在 Android 系统壳验收
关联 ADR：ADR-MOB2 导航与共享 WebUI 决策

## G4 页面和壁纸

### G4-01 逐页移动适配

对 `change-spec-v2.md` 的页面表逐项执行：

- [x] 消除固定宽度和不可见横向内容。
- [x] 将复杂编辑器改为全屏或 Sheet。
- [x] 表格提供卡片或可控横向滚动。
- [x] 操作按钮进入触控可达位置。
- [x] 错误、空状态和加载状态完整。
- [x] 保留桌面布局质量。

**验收**：每个路由在四个移动视口和桌面视口截图通过。

**Closure evidence**: Shared responsive rules cover all 16 production routes. Playwright produced a 16-route matrix at 360x800, 390x844, 412x915, 844x390, 768x1024, and 1440x900 under `output/playwright/g4-routes-*-contact.png`.

### G4-02 移动终端（已取消）

- [-] Under ADR-MOB2-009, production mobile terminal FAB/Sheet/subscription remains canceled; only native research packaging is retained.
- [x] `ChatTerminal` 仅在桌面 Web 挂载；移动断点和 Android WebView 均不挂载。
- [x] 桌面 Web 终端组件、WebSocket terminal 协议与服务端终端保持不变。

**验收**：360dp、390dp、412dp 与 Android WebView 不出现终端 DOM、FAB、Sheet 或终端 Bridge；桌面宽度终端不回归。

**取消证据**：产品明确决定“移动端不需要终端”；对应 Android runtime、Bridge 和移动 Sheet 代码已删除，防复活契约纳入 G5/CI。

### G4-03 壁纸数据扩展

- [x] 增加焦点、遮罩和动效字段。
- [x] 兼容旧配置。
- [x] API 验证范围。
- [x] 上传后焦点编辑。
- [x] 默认壁纸迁移。

**验收**：旧用户壁纸不丢失，新字段可回滚。

**关闭证据**：`wallpaper_focus`、`wallpaper_overlay` 和 `wallpaper_motion` 具备稳定默认值与范围校验；旧 URL-only 记录保持兼容。主体通过一次 `ConfigService.set_many()` 原子提交四字段；自定义 Agent 补齐字段模型、原子 JSON 持久化和完整运行时/文件快照，保存失败不留下混合更新；上传失败删除新文件并保留旧配置。专项 `13 passed`，与 G4 前端契约合并 `17 passed`，Ruff 通过，详见 `test-evidence.md`。

### G4-04 壁纸渲染

- [x] 背景不随键盘缩放。
- [x] 局部磨砂。
- [x] 亮暗对比度适配。
- [x] 性能三级降级。
- [x] 减少动画偏好。
- [x] 低内存时资源释放。

**验收**：关键文字可读，交互流畅，无明显背景跳动。

**Closure evidence**: The backdrop is a stable fixed `100lvh` layer with focus positioning, global/local masks, high/medium/low degradation, reduced-motion handling, and inactive-layer release on memory pressure or page hiding.

## G5 Android 系统壳

### G5-01 工程初始化

- [x] 创建 Kotlin DSL 工程。
- [x] 建立四个模块（`:app`、`:core:webcontainer`、`:core:security`、`:core:bridge-api`）。
- [x] 配置 debug/staging/release。
- [x] 固定 JDK、AGP 和依赖目录。
- [x] 加入 lint、test、assemble CI。

**验收**：空壳三变体可构建。

**关闭证据**：JDK 17、Gradle 8.11.1、AGP 8.9.2、Kotlin 2.1.20、SDK 35；`lint test assembleDebug assembleStaging assembleRelease` 通过，三个 APK 经防复活扫描通过，详见 `test-evidence.md`。

**并行例外**：本任务依据 ADR-MOB2-007 经用户明确批准提前执行，只关闭 G5-01 安全空壳，不授权开始 G5-02；G2 至 G4 仍按原阶段顺序执行。

### G5-02 Web 资源集成

- [x] 前端 build 产物复制到 Android assets。
- [x] WebViewAssetLoader 提供受信任 origin。
- [x] 构建时校验资源哈希。
- [x] 禁止运行时下载替换主 UI。
- [x] 错误页可显示版本和诊断 ID。

**验收**：离线可打开 UI 壳，在线后连接远端服务。

**关闭证据**：Gradle 在 `preBuild` 前构建 Vue、复制 `web/dist`、生成并验证 SHA-256 清单；主 UI 固定从 `https://appassets.androidplatform.net/index.html` 加载，三变体 APK 包含内置 UI，详见 `test-evidence.md`。

### G5-03 认证和 Bridge

- [x] Token 进入 Keystore 保护存储。
- [x] Web 页面只获得短期会话句柄。
- [x] Bridge 来源校验。
- [x] 文件与分享接口参数校验；终端接口不存在。
- [x] 日志脱敏。

**验收**：Web Storage、URL、日志和崩溃报告不含明文 token。

**关闭证据**：Activity 已真实装配 AES-GCM Android Keystore，并由原生登录后向服务端换取五分钟不透明句柄；Web 仅接收 handle，REST/WS 通过 HttpOnly Cookie 认证，Android Web Storage 与 WS URL 均不含 bearer；受信任 origin WebMessage Bridge、前端 adapter、固定方法白名单和参数验证测试通过，详见 `test-evidence.md`。

### G5-04 系统能力

- [x] 文件选择和上传。
- [x] 分享。
- [x] 深链。
- [x] 返回手势。
- [x] 网络状态。
- [x] 通知权限和通知跳转。
- [x] 前后台连接策略。

**验收**：系统行为符合 Android 生命周期，不使用伪保活。

**关闭证据**：SAF 文件选择已由 `PromptInput` Bridge adapter 消费，并将受检字节恢复为 `File` 后复用图片/文档 multipart 上传；系统分享、`xiaoda://app` 深链、Web 历史返回、WebView save/restore、网络回调、Android 13 通知权限和前后台连接策略已接入；无 Service、WakeLock 或后台保活，详见 `test-evidence.md`。

### G5-05 移动端终端 runtime（已取消）

- [-] 不再冻结、引入或审核 Termux/bootstrap 组件。
- [x] 删除 `:feature:terminal-runtime`、Termux 源码、PTY/JNI/NDK shim、RuntimeSupervisor、BOM/SBOM/NOTICE 和组件验证脚本。
- [x] 删除 research APK、NDK 安装、组件验证和 artifact 上传 CI。
- [x] Gradle 工程仅保留 `:app` 与三个 `:core` 模块。

**验收**：源码树、Gradle、CI 和 debug/staging/release APK 均不存在移动终端 runtime。

### G5-06 远程 CLI 自动启动（已取消）

- [-] 不实现或保留远程 CLI 自动启动、nonce/协议握手、崩溃退避、状态页或进程树管理 PoC。
- [x] Bridge allowlist 不包含 `openTerminal`、`getRuntimeStatus`、`stopRuntime`、`setSheetOpen` 或通用命令执行接口。
- [x] Android Vite 构建在编译期排除 `ChatTerminal`/xterm chunk，移动断点和 Android WebView 也不挂载终端。
- [x] 桌面 Web 终端和服务端 terminal 协议保持不变。

**取消证据**：2026-08-10 用户明确要求移动端砍掉终端。ADR-MOB2-010 废止 ADR-MOB2-009 的研究例外，G5-05/G5-06 从 BLOCKED 改为 CANCELED。

### G5-07 移动端本地核心（进行中）

- [x] Android 使用独立的 Mobile Vite 入口，APK 不再打包或启动远程服务版页面。
- [x] 删除 Android 的远程服务地址、远程登录、短期会话句柄和 Cookie 认证路径。
- [x] Provider 元数据保存在设备本地，API Key 由 Android Keystore AES-GCM 加密保存且不返回 WebView。
- [x] 支持 OpenAI-compatible 与 Anthropic Provider、模型列表和 SSE 流式聊天。
- [x] 支持本地会话历史、基础 Agent、系统提示词、图片、纯文本、PDF 和结构校验后的 DOCX 选择与保存。
- [x] 建立多 Agent、长期记忆、定时任务、浏览器自动化、工具替代层、插件和复杂文档处理的 Kotlin 能力注册接口。
- [ ] 实现向量化长期记忆和多 Agent 实际编排。
- [ ] 实现 WorkManager 定时任务、受限浏览器自动化和本地插件执行模型。
- [ ] 实现 DOCX/PDF 本地文本抽取、分块和复杂文档问答。

**当前验收**：安装 APK 后无需部署 Xiaoda/FastAPI 服务；用户在设备内配置云模型 Provider、API Key 和模型即可建立本地会话并发起流式聊天。移动端仍不包含本地大模型、Python runtime、FastAPI、Termux、PTY 或终端能力。

**实施证据**：`MobileApp.vue`/`MobileLocalView.vue` 为移动专用入口；`LocalAiController`、`ProviderClient`、`LocalStateStore` 和 `KeystoreSecretStore` 构成本地核心。2026-08-11 已通过前端 typecheck、Local Bridge 单测、Android Python 合同测试、Gradle `lint test assembleDebug assembleStaging assembleRelease` 及三变体 APK 防复活扫描。
## G6 集成、发布和回滚

### G6-01 全量测试

- [ ] 后端全量 pytest。
- [ ] Ruff 和版本同步。
- [ ] 前端 typecheck、单测、build、E2E。
- [ ] Android lint、test、assemble、仪器测试。
- [ ] 敏感信息扫描。
- [ ] 本地 AI/Ollama 防复活扫描。

### G6-02 性能

- [ ] 冷启动。
- [ ] Chat 首屏。
- [ ] 长会话滚动。
- [ ] 图谱和仪表盘降级。
- [ ] 壁纸和粒子性能。
- [ ] 内存压力恢复。

### G6-03 兼容

- [ ] 最低 Android 版本。
- [ ] 当前 Android 稳定版本。
- [ ] 刘海、打孔、手势导航。
- [ ] 深色/浅色和字体缩放。
- [ ] 弱网、断网、切网。
- [ ] 服务端旧版本和能力不匹配。

### G6-04 发布物

- [ ] 签名 AAB/APK。
- [ ] 前端资源哈希。
- [ ] SBOM 和许可证归档。
- [ ] 混淆映射与 native symbols。
- [ ] 版本兼容矩阵。
- [ ] 回滚包和回滚说明。

### G6-05 最终验收

- [ ] `acceptance-matrix-v2.md` 全部 P0/P1 通过。
- [ ] 例外项有负责人、原因和到期日。
- [ ] 文档与代码一致。
- [ ] 新上下文按 handoff runbook 可独立复现验证。

**完成条件**：所有门禁通过后才允许标记发布候选。

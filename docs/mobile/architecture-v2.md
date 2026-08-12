# Xiaoda Agent 移动端架构重构 v2

## 1. 决策摘要

### 1.1 主决策

采用“共享 WebUI + 内嵌 Python 后端 + Android 安全系统壳”的架构。移动端不提供终端；桌面 Web 终端保持现有能力。

```text
Android App
  ├─ Android System Shell
  │   ├─ 认证令牌安全存储（Keystore）
  │   ├─ 文件选择、分享、通知、深链
  │   ├─ 生命周期和网络状态
  │   └─ 内嵌 Python 后端（Chaquopy）
  │       └─ 127.0.0.1:8765 上运行原 web.server（FastAPI + AgentCore 等价）
  └─ Bundled Vue WebUI
      ├─ 方案 C 移动导航
      ├─ 全部现有业务页面
      ├─ REST / WebSocket Client → 内嵌后端
      └─ 移动端不挂载终端 UI
```

### 1.2 为什么替代旧方案

旧方案要求完整原生 Compose UI，只开放少量移动端能力。当前产品决策要求保留全部现有功能入口，并与外部 WebUI 尽量一致。继续复制原生页面会产生三类长期问题：

- WebUI 与 Compose 页面功能漂移。
- 每个后端能力需要维护两套交互、状态和测试。
- MCP、插件、工作流、仪表盘等管理页面迁移成本远高于移动壳适配。

因此旧 ADR-MOBILE-001 中“远端 AgentCore”已被 ADR-MOB2-011（内嵌 Python 后端）取代；“完整原生 Compose 业务 UI”被本方案取代。

## 2. 架构目标

### 2.1 业务目标

- 最大化保留现有功能，不因移动化削减 Agent、记忆、工具、MCP、插件、邮箱、媒体、工作流、计划任务、健康、仪表盘等能力。
- 删除移动产品中没有意义的本地 AI 部署入口和运行时。
- 将自定义服务商升级为清晰、可靠、可诊断的主要模型接入方式。
- 移动端与桌面端保持统一视觉语言、统一路由、统一协议和统一功能行为。

### 2.2 工程目标

- 单一导航事实源。
- 单一 Provider 事实模型。
- 单一 Chat/Wallpaper 数据链路；桌面 Terminal 独立保留。
- 所有高风险边界可自动验收。
- 新上下文只依赖仓库文档即可接管。

### 2.3 非目标

- 不在 Android 端运行本地模型推理（Ollama/ONNX/BGE 已退役；语义向量仅调用远程 Embedding API）。
- 内嵌 Python 后端在 `127.0.0.1` 运行原 `web.server`（FastAPI + AgentCore 等价，含 SQLite/向量检索与插件）；不另行引入独立后端服务。
- 不保证后台永久 WebSocket。
- 不在移动端提供终端 UI、终端 Bridge、Termux、PTY 或远程 CLI 自动启动，也不保留研究构建。
- 不在本轮重写全部桌面 WebUI 页面。

## 3. 技术栈

### 3.1 共享 WebUI

| 能力 | 技术 | 约束 |
|---|---|---|
| UI 框架 | Vue 3.5 + TypeScript 5.6 | 保持 Composition API 与现有组件风格 |
| 构建 | Vite 5.4 | Android 壳加载固定构建产物，不加载任意远程脚本 |
| 路由 | Vue Router 4.4 | 桌面与移动共享路由定义和能力元数据 |
| 状态 | Pinia 2.2 | 不复制移动专属业务 Store |
| 组件 | Naive UI 2.40 | 对移动抽屉、Sheet、表单做封装 |
| 桌面终端 | xterm.js 6 | 仅在桌面 Web 挂载；移动端不显示、不初始化 |
| 图表 | ECharts、3d-force-graph、Three.js | 移动端按性能档位降级 |
| 内容 | markdown-it、highlight.js | 保持现有消息渲染链 |

### 3.2 服务端

| 能力 | 技术 | 约束 |
|---|---|---|
| API | Python 3.11+、FastAPI、Pydantic | 保持 `/api/v1` 与 Envelope 约定 |
| 实时连接 | WebSocket | Chat 与 Terminal 共享连接管理但隔离消息类型 |
| Provider | OpenAI SDK + httpx | 自定义 OpenAI-compatible 为主路径 |
| 持久化 | SQLite、aiosqlite、sqlite-vec | 退役本地 Embedding 后仍可保留向量存储 |
| 安全 | CredentialVault、SSRF Guard | 出站请求必须真正使用安全解析结果 |
| 测试 | pytest、pytest-asyncio | Provider 和迁移门禁必须进入严格 CI |

### 3.3 Android 系统壳

| 能力 | 建议技术 | 约束 |
|---|---|---|
| 语言 | Kotlin | 不引入端内 Python |
| UI 容器 | 单 Activity + Android WebView | 业务 UI 由共享 Vue 构建产物提供 |
| Web 资源 | WebViewAssetLoader | 禁止 `file://` 暴露与任意跨域文件访问 |
| Web 能力 | AndroidX WebKit | 固定安全配置和版本能力检测 |
| 安全存储 | Android Keystore + 加密存储封装 | Token 不进入普通 SharedPreferences |
| 网络 | WebView 网络层或受控原生代理 | Release 仅允许 HTTPS/WSS |
| 文件 | Storage Access Framework | 只返回用户明确选择的 URI |
| 通知 | Android Notification API | 不伪造后台常驻连接 |

Android 依赖版本在创建工程时以当期稳定版和官方兼容矩阵为准，文档不硬编码未来会失效的版本号。

## 4. 模块边界

### 4.1 WebUI 模块

```text
web/frontend/src/
├─ navigation/
│  └─ capabilities.ts
├─ components/layout/
│  ├─ AppLayout.vue
│  ├─ DesktopShell.vue
│  ├─ MobileAppShell.vue
│  ├─ MobileBottomNav.vue
│  ├─ CapabilityDrawer.vue
│  ├─ QuickStatusSheet.vue
│  └─ AgentBackdrop.vue
├─ components/chat/
│  └─ ChatTerminal.vue
├─ composables/
│  ├─ useResponsiveShell.ts
│  ├─ useViewportInsets.ts
│  └─ useWallpaperPerformance.ts
└─ views/
   └─ existing views
```

`capabilities.ts` 是导航唯一事实来源，至少包含：

```ts
type CapabilityEntry = {
  routeName: string
  path: string
  labelKey: string
  icon: string
  group: 'primary' | 'orchestration' | 'extensions' | 'operations' | 'about'
  mobilePlacement: 'bottom' | 'drawer' | 'settings'
  order: number
  enabled: boolean
}
```

禁止 `SideBar.vue`、`MobileBottomNav.vue` 和 `CapabilityDrawer.vue` 分别硬编码一套入口。

### 4.2 服务端模块

```text
Provider API
  -> ProviderApplicationService
      -> ProviderRepository
      -> CredentialStore
      -> ProviderRuntimeRegistry
      -> SecureOutboundClientFactory
      -> ProviderDiagnostics
```

Provider 创建、更新、删除必须由应用服务协调，路由层不得继续直接编排 JSON、密钥文件和运行时客户端。

### 4.3 Android 模块

```text
:app
  -> :core:webcontainer
  -> :core:security
  -> :core:bridge-api
```

- `:app`：Activity、启动路由、依赖装配。
- `:core:webcontainer`：WebView 安全配置、资源加载、导航策略。
- `:core:security`：Token、安全存储、证书和日志脱敏。
- `:core:bridge-api`：最小 JS Bridge 契约。

Web 页面不得获得任意命令执行、任意文件路径或任意 Android Intent 能力。

## 5. 方案 C 导航

### 5.1 一级底栏

| 入口 | 路由 | 页面职责 |
|---|---|---|
| 聊天 | `/` | 会话、模型、附件、TTS |
| Agent | `/settings/agents` | Agent、人格、权限、壁纸 |
| 记忆 | `/insight` | 记忆、画像、情绪、事件、知识图谱 |
| 工具 | `/settings/tools` | Skills 与工具状态 |
| 设置 | `/settings/system` | 系统、模型、服务商、外观与账户聚合 |

### 5.2 全部能力抽屉

- 智能体与编排：Agent、工作流、计划任务、洞察。
- 扩展与连接：MCP、插件、邮箱、媒体。
- 运维与信息：健康、仪表盘、免责声明、赞助。
- 模型与服务商：自定义服务商、模型发现、路由配置。

底栏与抽屉允许重复高频入口，重复的是入口，不是页面实现。

### 5.3 顶部与角落

- 左上角：全部能力抽屉。
- 中上部：当前 Agent、处理状态。
- 右上角：连接、当前服务商、通知、快捷设置。
- 长列表页面：主要新增操作放右下角 FAB；批量操作进入顶部上下文栏。

## 6. 图标与壁纸

### 6.1 极光玻璃图标

- SVG 24dp 视口。
- 触控区至少 48dp。
- 统一圆角端点和视觉重量。
- 默认月白细线，选中时边缘发光，不依赖颜色单独表达状态。
- 禁止 Emoji 作为正式产品图标。
- 图标必须有无障碍标签。

### 6.2 壁纸模型

壁纸记录扩展为：

```text
url
focus_x: 0.0..1.0
focus_y: 0.0..1.0
overlay_strength: 0.0..1.0
motion_mode: full | reduced | static
```

显示规则：

- 壁纸始终使用 cover，不因键盘或系统栏变化缩放。
- 顶栏、消息、输入栏和底栏使用局部磨砂。
- 使用 safe-area inset 避开刘海和手势区。
- 根据局部亮度调整文字和遮罩。
- 省电、高温、低性能设备冻结动态效果。
- 尊重 `prefers-reduced-motion` 和系统动画缩放设置。

## 7. 本地 AI 与 Ollama 退役边界

### 7.1 删除

- `/local-deploy` 页面、导航、API 和配置模式。
- `memory/local_embed.py` 与本地 ONNX 推理路径。
- BGE-small-zh-v1.5 内置模型资产。
- `onnxruntime`、`tokenizers` 的专属依赖和发布检查。
- `OLLAMA_BASE_URL`、`OLLAMA_DEFAULT_MODEL`、`OLLAMA_MODEL_MAP`、Ollama Provider metadata。
- Ollama 自动注册、模型翻译、成本特判、健康特判和 Setup 字段。
- 移动端目录选择器和任意宿主路径选择。

### 7.2 保留

- 远端 FastAPI/AgentCore 服务部署。
- Docker 与服务器构建基础设施。
- OpenAI-compatible 自定义服务商。
- 远程 Embedding 能力和 sqlite-vec 存储。
- 普通服务器 GPU 能力，只要不作为移动端本地部署入口。
- 受控工作区与工具审批。

### 7.3 数据迁移

本地 BGE 输出 512 维，目标远程 Embedding 可能是 1024 维。迁移不得直接复用不同维度的向量表。

迁移策略：

1. 启动前检测现有向量维度与目标模型维度。
2. 维度相同则可继续使用，但必须记录模型 ID。
3. 维度不同则备份数据库并执行全量重编码。
4. 没有远程 Embedding 配置时，保留文本记忆但禁用语义检索，并在 UI 明确提示。
5. 迁移失败时恢复备份，不得留下部分重编码数据库。

## 8. 自定义服务商目标架构

### 8.1 Provider 数据模型

```text
id
label
protocol: openai_compatible | anthropic
base_url
models_path
chat_path
default_model
enabled
request_timeout
connect_timeout
extra_headers_allowlist
created_at
updated_at
credential_state
```

密钥不进入模型对象，只暴露 `configured/missing/corrupt` 状态。

### 8.2 创建流程

```text
Validate Input
  -> Normalize URL
  -> Validate Secure Target
  -> Test Authentication/Protocol
  -> Discover Models or Accept Manual Model
  -> Prepare Credential
  -> Persist Config + Credential
  -> Register Runtime Client
  -> Invalidate Discovery Cache
  -> Return Diagnostics
```

任一步失败都回滚到创建前状态。

### 8.3 诊断模型

每次发现或连接测试返回：

```text
status
stage: validate | dns | connect | tls | auth | discover | probe
error_code
message
retryable
latency_ms
models
warnings
```

稳定错误码至少包含：

- `AUTH_FAILED`
- `RATE_LIMITED`
- `TIMEOUT`
- `DNS_FAILED`
- `TLS_FAILED`
- `CONNECTION_FAILED`
- `MODEL_NOT_FOUND`
- `INVALID_RESPONSE`
- `SSRF_BLOCKED`
- `CREDENTIAL_CORRUPT`
- `PROVIDER_IN_USE`

### 8.4 安全出站

- URL 校验、DNS 解析和实际连接必须由同一个安全出站客户端完成。
- 禁止校验后由 SDK 再次独立解析 DNS。
- 默认拒绝私网、回环、链路本地、元数据地址和未授权端口。
- 本地目标仅可由显式管理员 allowlist 开启。
- 禁止跨主机重定向。
- 日志不得记录 Authorization、API Key、完整上游响应正文。

## 9. 终端架构

### 9.1 桌面 Web 终端

现有 xterm.js、WebSocket terminal 协议和服务端进程所有权仅保留给桌面 Web：

- 桌面端保留右侧终端面板和既有多会话行为。
- 移动断点不挂载 `ChatTerminal`，Android WebView 无论窗口宽度都不挂载终端。
- 移动端不得出现终端 FAB、Sheet、PTY、shell、CLI 自动启动或终端 Bridge。
- 服务端与桌面 Web 的终端实现不因本决策删除，仍需保持会话归属、进程树回收和限流门禁。

### 9.2 移动端终端彻底移除

2026-08-10 的最终产品决定是：移动端不需要终端，研究实现也不再保留。

- 删除 `:feature:terminal-runtime`、Termux vendored source、PTY/JNI/NDK shim 和 RuntimeSupervisor。
- 删除 research APK、Gradle opt-in 属性、组件验证脚本、BOM/SBOM/NOTICE 与 CI NDK 步骤。
- Bridge 不包含终端、运行时、Sheet 状态或任意命令执行方法。
- Android Vite 构建通过 `VITE_XIAODA_MOBILE_BUILD=1` 在编译期排除 `ChatTerminal`/xterm chunk；移动断点和 Android WebView 也不挂载终端。桌面 Web 终端及服务端 terminal 协议保持不变。
- CI 以四模块工程、源码扫描和三变体 APK 扫描阻止移动终端复活。

## 10. 安全边界

- Release 只允许 HTTPS/WSS。
- Token 不进入 URL、日志或普通 Web Storage；Android 壳通过受控桥接注入短期会话。
- JS Bridge 使用固定方法白名单和来源校验。
- WebView 禁用任意文件访问、调试和混合内容。
- Provider 密钥仅存在服务端 CredentialVault。
- 桌面 Web 终端和 Agent 工具执行是两个信任域；移动端不暴露终端。
- 高风险工具继续走现有审批，不因移动 UI 缩短审批链。
- 上传使用系统选择器和 MIME/大小校验。

## 11. 关键 ADR

### ADR-MOB2-001 共享 WebUI

- 状态：接受。
- 决策：移动端复用 Vue WebUI，Android 只提供系统壳。
- 后果：功能一致性提高；必须强化 WebView 安全和移动响应式质量。

### ADR-MOB2-002 远端业务内核（已被取代）

- 状态：被 ADR-MOB2-011 取代。
- 原决策：AgentCore、模型、工具、记忆均在远端服务。
- 原后果：移动端依赖网络；离线只提供缓存和只读状态。
- 取代原因：产品改为“完全离线单机版”，业务内核随应用内嵌，不再依赖远端服务。

### ADR-MOB2-011 内嵌 Python 后端

- 状态：接受（2026-08-12）。
- 决策：移动端采用“完全离线单机版”形态，通过 Chaquopy 在 Android 内嵌 Python 3.11 运行时，于 `127.0.0.1:8765` 启动原 `web.server`（FastAPI + AgentCore 等价），WebUI 走 loopback 访问内嵌后端；不再连接远端 AgentCore 服务。
- 后果：APK 体积增大（约 50MB+，含 Python 运行时与依赖）；本地 SQLite/向量检索/插件随应用存储于私有目录；`network_security_config` 需放行 `127.0.0.1`/`localhost` 明文；Chaquopy 依赖须用 Android 交叉编译轮子（arm64-v8a/x86_64）。
- 边界：本地模型推理（Ollama/ONNX/BGE）仍退役，语义向量仅调用远程 Embedding API；移动端仍不提供终端能力。

### ADR-MOB2-003 退役本地 AI

- 状态：接受。
- 决策：删除 Ollama 和 ONNX 本地 Embedding；全部语义向量只允许调用 SiliconFlow API。
- 后果：需要 SiliconFlow `EMBED_API_KEY` 和向量维度迁移；无密钥时保留文本记忆并关闭语义检索，不允许本地或其他服务商回退。

### ADR-MOB2-004 全功能分层导航

- 状态：接受。
- 决策：所有现有业务入口保留，通过方案 C 分层。
- 后果：需要逐页移动适配，不能只适配 Chat。

### ADR-MOB2-005 自定义服务商优先

- 状态：接受。
- 决策：OpenAI-compatible Provider 是主要扩展入口。
- 后果：Provider 事务、安全出站、诊断和测试成为 P0。

### ADR-MOB2-006 可选终端承载（已废止）

- 状态：被 ADR-MOB2-008、ADR-MOB2-009 和最终的 ADR-MOB2-010 依次取代。
- 当前结论：移动端不提供、也不研究终端承载。

### ADR-MOB2-007 Android 骨架可提前并行

- 状态：接受。
- 决策：经用户明确批准，G5-01 的 Android 安全空壳与独立 APK CI 可在 G1-08 收口期间并行完成。
- 范围：仅允许固定工具链、四模块边界、三变体、安全默认值和 APK 防复活门禁。
- 限制：不得开始 G5-02，不得依赖未冻结的 Provider、导航、移动页面或壁纸协议；G1-08 与 G2 至 G4 的阶段门禁仍然有效。
- 后果：G5-01 可独立关闭，但 G5 阶段不得继续推进，直到前置阶段按原顺序全部通过。

### ADR-MOB2-008 移动端终端移除

- 状态：原决定有效，最终范围由 ADR-MOB2-010 明确为“研究实现也删除”。
- 决策：生产移动 UI/Bridge 不暴露终端；桌面 Web 终端和服务端协议不变。

### ADR-MOB2-009 开源 Termux 隔离研究（已废止）

- 状态：被 ADR-MOB2-010 取代。
- 原决策：允许 opt-in debug research APK 验证 Termux terminal-emulator。
- 废止原因：产品明确决定移动端不需要终端，不再为未进入产品的能力维护源码、NDK、供应链和 CI 成本。

### ADR-MOB2-010 移动端终端研究撤销

- 状态：接受（2026-08-10）。
- 决策：删除移动端终端 UI、Termux/PTY runtime、远程 CLI PoC、研究 APK、供应链材料和全部终端 Bridge/Sheet 接口。
- 保留：桌面 Web 的 `ChatTerminal`、terminal WebSocket 协议和服务端终端能力。
- 后果：G4-02、G5-05、G5-06 标记为取消；移动端验收改为“能力不存在且不可复活”。

## 12. 架构风险登记

| 风险 | 等级 | 缓解 | 阻断条件 |
|---|---|---|---|
| 512/1024 向量维度迁移 | Critical | 备份、全量重编码、回滚 | 无恢复演练不得删除本地模型 |
| Provider DNS rebinding | Critical | 安全出站客户端闭环 | 无真实连接测试不得发布 |
| Provider 三份状态分裂 | Critical | 应用服务事务与故障注入 | 无回滚测试不得发布 |
| WebView Bridge 权限扩大 | High | 最小白名单、来源校验 | 可执行任意命令则停止 |
| 移动端终端能力误复活 | High | 四模块契约、Bridge allowlist、源码/APK 扫描 | 任一终端模块、API、NDK 或研究产物出现则阻断 |
| 全功能页面移动适配遗漏 | High | 路由覆盖矩阵 | 任一路由不可达不得完成 |
| 壁纸导致可读性不足 | Medium | 局部遮罩和对比度测试 | 关键文字不达标则阻断 UI |
| 后台连接不可靠 | Medium | 明确前台连接策略 | 禁止承诺永久后台在线 |

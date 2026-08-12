# Xiaoda Android 全功能本地化迁移矩阵

> 最后更新：2026-08-12  
> 目标：允许针对 Android 重写实现，但不以“不兼容”为理由删除原有能力。除用户已明确要求移除的移动端虚拟终端/PTY 外，所有功能必须在手机本地完成编排、存储和执行；模型与搜索等第三方 API 仅作为用户主动配置的外部能力。

## 完成判定

任何条目只有同时具备以下证据才可标记“完成”：

1. 原版中文 WebUI 对应入口仍存在；
2. API、WebSocket、后台任务或工具契约可在 Android 本地服务中执行；
3. 数据写入应用私有目录，重启后仍可恢复；
4. 真机或模拟器端到端测试通过，而不是仅通过 JVM 单测或 APK 构建；
5. Android 不支持原桌面实现时，已有等价 Kotlin/Android 或纯 Python 适配实现。

## 当前运行底座

| 项目 | 原实现 | Android 目标实现 | 当前状态 | 验收证据 |
|---|---|---|---|---|
| 中文 WebUI | Vue/Vite `web/frontend` | 原版构建产物打入 WebView | 已保留 | 前端构建、页面清单、截图 |
| REST / WebSocket | FastAPI + Uvicorn | Chaquopy 嵌入 Python，在 `127.0.0.1` 启动原 `web.server` | 核心链路已验证 | Android 模拟器验证 `/ping`、OpenAPI 原路由、鉴权 WebSocket 连接与 Agent 最终回复 |
| Python 业务源码 | 仓库根模块与包 | 构建时完整同步进 APK Python 源集 | 施工中 | APK 内容检查、模块导入测试 |
| 私有数据目录 | `~/.ai-agent` / 外置数据盘 | App 私有 `files/xiaoda/.ai-agent` | 核心持久化已验证 | 数据库、Provider 配置、加密凭证、图片和文档均落入私有目录；兼容迁移早期误写入 Chaquopy 解包目录的数据 |
| 机密信息 | 文件凭据 + WebUI | Android Keystore 保存主令牌，本地后端凭据目录保存 provider key | 部分已有 | API Key 保存/恢复/删除测试 |
| 移动端虚拟终端 | PTY / subprocess shell | **按用户要求移除，不迁移** | 已决策 | UI 无终端入口、WS 无终端启动 |

## 功能矩阵

| 领域 | 必须保留的原能力 | 原代码入口 | Android 适配策略 | 状态 |
|---|---|---|---|---|
| 首次设置 | 免责声明、初始化向导、用户资料、密码 | `SetupWizardView`、`UserProfileSetupView`、`setup.py`、`auth.py` | 本地 API 与私有配置目录 | 待端到端 |
| 模型配置 | Provider、API Key、Base URL、模型发现、模型选择、路由覆盖、凭证池 | `ModelsView`、`models.py`、`model_discovery.py`、`model_router.py` | 原 Python 路由；Key 由本地凭证保险库加密，首次新增 Provider 后原地重初始化 Agent | 核心链路已端到端；模型发现/诊断仍待全量验收 |
| 聊天 | 流式输出、中断、重试、工具调用、图片/文档消息 | `ChatView`、`chat.py`、`ws_hub.py`、`chat_processor.py` | 本地 WebSocket + Android 文件选择桥 | WebSocket、完整 Agent、41 项工具注入和最终回复已端到端；带工具调用时的逐 token 推送仍待补齐 |
| 会话 | 新建、列表、切换、历史、导出、恢复 | `chat.py`、数据库层 | SQLite 写入 App 私有目录，Android 分享导出 | 新建、消息落库、列表、历史、删除已端到端；导出和进程重启恢复仍待验收 |
| Agent | Agent 列表、人格、系统提示词、显示名、路由、启停 | `AgentsView`、`agents.py`、`agent_dispatcher.py` | 原配置/调度器本地运行 | 待端到端 |
| 多 Agent | 子 Agent 委派、并行 DAG、任务编排、冲突处理 | `delegation.py`、`parallel_dag.py`、`task_orchestrator.py` | 原 asyncio 调度；子进程型步骤改为进程内执行器 | 待适配 |
| 工作流 | 工作流 CRUD、节点、运行、状态 | `WorkflowView`、`workflows.py` | 原本地工作流引擎 | 待端到端 |
| 长期记忆 | 情景/语义/情绪/偏好/永久记忆、蒸馏、主动召回 | `memory/*`、`InsightView`、`insight.py` | SQLite + NumPy 索引；不可用原生向量扩展时使用本地等价索引 | 待适配 |
| 向量与检索 | sqlite-vec、NumPy 索引、重排、图谱、多跳检索、FTS 降级 | `vector_store.py`、`numpy_index.py`、`kg_search.py` | 优先 Android 可用本地向量实现；FTS 仅是故障降级而非删除 | 待适配 |
| 学习与成长 | XP、学习反馈、自省、梦想整合、自我模型、健康信号 | `core/xp_system.py`、`learning_loop.py`、`dream_*`、`self_*` | 原后台协程，接入 Android 生命周期/WorkManager | 待适配 |
| 定时任务 | 创建、编辑、删除、执行、提醒、恢复 | `ScheduleView`、`schedule.py`、`schedule_tool.py` | Android WorkManager/AlarmManager 唤醒本地任务 | 待重写 |
| 工具系统 | 注册、权限、启停、参数 schema、审批、修复、执行记录 | `ToolsView`、`tools.py`、`tool_engine/*` | 原工具注册表；系统能力通过 Android bridge 实现 | 待适配 |
| Python 工具 | 安全代码执行、计算与受控脚本 | `code_tools_v2.py` | 在嵌入解释器内隔离执行；禁止桌面 shell 逃逸 | 待重写 |
| 文件工具 | 工作区读写、搜索、压缩、导出、上传 | `file_tools_v2.py`、`workspace.py` | App 私有工作区 + Storage Access Framework | 待适配 |
| 文档处理 | PDF、Word、PPT、Excel、HTML、OCR/图片 | `document_tools.py` | Chaquopy 可用库 + Android 原生解析补位 | 依赖打包中 |
| 图片与媒体 | 图片上传、壁纸、贴纸、二维码、媒体库 | `MediaView`、`media.py`、Pillow/qrcode | Pillow + Android 图片解码/分享 | 依赖打包中 |
| 语音/TTS | TTS、参考音频、SILK/音频输出 | `tts_tools.py`、媒体路由 | Android MediaCodec/AudioTrack 替代不可用桌面编解码 | 待重写 |
| 网络搜索 | 多搜索源、国内搜索、Tavily、网页抓取 | `multi_search_tools.py`、`domestic_search_tools.py`、`web_tools_v2.py` | 本地工具编排，用户 API Key/网络请求 | 待端到端 |
| 浏览器自动化 | 网页打开、读取、交互、自动化 | `web_browse_*` | Android Custom Tabs/WebView 自动化服务；不依赖桌面 Playwright 浏览器进程 | 待重写 |
| 插件 | 发现、安装、启用、权限、插件工具 | `PluginsView`、`plugins.py`、`plugins/*` | App 私有插件目录；签名/权限校验；Python 插件进程内加载 | 待适配 |
| 市场 | 插件/能力市场浏览与安装 | `market.py`、`market/*` | 本地下载、校验、安装 | 待适配 |
| MCP | MCP 配置、连接、工具暴露 | `McpView`、`mcp.py`、bootstrap MCP | 支持 HTTP/SSE MCP；stdio MCP 改为 Android 可承载的进程内/远程连接器 | 待重写 |
| 邮件 | 邮箱配置、读取、发送、管理 | `MailView`、`mail_manage.py`、`mail_tools.py` | Python 网络协议或 Android Account/Intent 适配 | 待适配 |
| 微信/QQ 通道 | 连接状态、二维码、消息适配 | `wechat.py`、`wechat_bot_adapter.py`、`qq_bot_adapter.py` | 保留云协议型适配；桌面客户端注入型能力改为 Android 可用协议实现 | 待审计 |
| 健康与诊断 | 探针、系统信息、模型/TTS/MCP 测试、报告 | `HealthView`、`health.py`、`doctor/*` | Android 系统信息提供器 + 原探针 | 待适配 |
| 可观测性 | 日志、指标、SLA、错误码、追踪 | `metrics.py`、`sla_exporter.py`、`slo_tracker.py` | 私有日志目录，本地诊断导出 | 待适配 |
| 配置热更新 | 配置保存、重载、权限模式、安全规则 | `SettingsView`、`config_reloader.py` | FileObserver/显式重载替代桌面 watchdog | 待适配 |
| 后台运行 | 后台任务、自唤醒、恢复、通知 | `background_tasks.py`、`self_wake.py` | Foreground Service + WorkManager + 通知渠道 | 待重写 |
| 系统集成 | 重启、打开目录、系统统计 | `system.py`、`system_tools.py` | Android Intent、Storage Access Framework、系统 API | 待重写 |

## 2026-08-12 端到端证据

- Android 本地创建 OpenAI 兼容 Provider，API Key 以 `enc:v1:` 写入 App 私有凭证目录，明文未落盘。
- 更新聊天路由后，`GET /models/chat-model` 返回用户选择；配置持久化到 `webui_overrides.json`。
- 修复“只有 MiMo Key 才初始化 Agent”的旧限制：仅配置自定义 Provider 时会立即完成 `AgentCore` 重初始化，无需重启 App。
- Android 内置假 Provider 实际接收模型请求；HTTP Chat 与鉴权 WebSocket 均经过完整 Agent 流程并返回结果。
- 会话消息写入 `files/xiaoda/.ai-agent/data/db/agent.db`，随后可通过会话历史接口读取。
- 图片与 Markdown 文档 multipart 上传后字节一致，文件位于 `files/xiaoda/.ai-agent/data/media/upload`。
- 尚未把本条标为完整聊天验收：当前携带工具定义的主调用走非流式 `route`，需要继续实现“工具调用 + 逐 token 推送”同时成立。
## Android 依赖兼容策略

| 依赖类型 | 示例 | 策略 |
|---|---|---|
| 纯 Python | FastAPI、Uvicorn、httpx、OpenAI、aiosqlite、jieba | 直接打入 APK；无 wheel 的纯 Python 包随源码归档打包 |
| Chaquopy Android 原生轮子 | NumPy、Pillow、PyYAML、cryptography、psutil、lxml | 固定到仓库提供的 Android 版本，并分别验证 arm64-v8a/x86_64 |
| 无 Android 轮子但可替代 | sqlite-vec、rapidfuzz、watchdog | 保留接口，换 NumPy/SQLite/Kotlin FileObserver 等本地实现 |
| 桌面进程/GUI 专属 | pywebview、Playwright 浏览器进程、PTY、系统 shell | pywebview 被 Android WebView 替代；浏览器、任务、文件能力用 Android API 重写；PTY 按用户要求移除 |
| 外部服务协议 | LLM Provider、搜索、邮箱、HTTP MCP | 编排与数据仍在手机本地，只在用户配置后调用目标 API |

## 当前迭代验收顺序

1. APK 中确认包含原 Python 源码、解释器和 arm64/x86_64 原生库；
2. 冷启动后 `127.0.0.1:8765` 可监听，原 `web.server` 完成 lifespan；
3. 原版中文 WebUI 能完成设置、登录、Provider/API Key 保存与模型发现；
4. WebSocket 流式聊天、会话恢复、图片和文档上传通过；
5. 逐域启用矩阵中的其余能力，每一项补充自动化与真机证据；
6. 全矩阵完成前不发布“完整本地版”Release。

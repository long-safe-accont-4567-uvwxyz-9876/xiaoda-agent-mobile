# 移动端架构重构变更规格 v2

## 1. 变更范围

本规格定义生产代码、配置、依赖、数据、测试、CI 和文档需要发生的变化。历史设计文档保留，但必须标注已被 v2 决策取代。

## 2. 变更总表

| 变更域 | 当前状态 | 目标状态 | 优先级 |
|---|---|---|---|
| 本地部署 UI | 独立路由和侧栏入口 | 完整删除 | P0 |
| 本地 Embedding | ONNX BGE 默认 local | 远程 Provider 或明确禁用语义检索 | P0 |
| Ollama | Provider 特例 | 完整删除 | P0 |
| 自定义 Provider | 可用但诊断和事务不足 | 主模型接入路径 | P0 |
| WebUI 导航 | 桌面侧栏为主 | 桌面侧栏 + 方案 C 移动壳 | P0 |
| 终端 | 桌面右侧面板 | 桌面面板 + 移动底部 Sheet | P1 |
| 壁纸 | URL + cover | 焦点、局部遮罩、安全区、性能档 | P1 |
| Android | 旧文档定义完整 Compose UI | WebUI 系统壳 | P1 |
| 文档 | 旧方案与新决策冲突 | `docs/mobile` 为唯一权威来源 | P0 |

## 3. 本地部署与本地 Embedding

### 3.1 删除文件候选

实施前再次运行引用扫描，确认没有新增依赖后删除：

```text
web/frontend/src/views/LocalDeployView.vue
web/routers/local_deploy.py
memory/local_embed.py
scripts/rebuild_vec_local.py
models/bge-small-zh-v1.5/
tests/test_local_embed_mode.py
```

### 3.2 修改文件

| 文件 | 变更 |
|---|---|
| `web/frontend/src/routes.ts` | 删除 `/local-deploy` |
| `web/frontend/src/components/layout/SideBar.vue` | 删除本地部署项；后续改读共享能力表 |
| `web/frontend/src/i18n/zh.ts` | 删除本地部署文案 |
| `web/frontend/src/i18n/en.ts` | 删除本地部署文案 |
| `web/server.py` | 删除 local deploy router 导入和注册 |
| `core/bootstrap.py` | 删除 `EMBED_MODE=local` 和本地回退 |
| `memory/vector_store.py` | 删除本地 Provider 和热切换分支 |
| `web/config_service.py` | 删除 `local_deploy.mode`，增加旧配置迁移 |
| `.env.example` | 删除 local embed 变量，说明远程 embedding |
| `requirements.txt` | 删除仅供本地推理的 `onnxruntime`、`tokenizers` |
| `pyproject.toml` | 校准依赖真相源，不引入上述依赖 |
| `requirements.lock` | 按正式安装策略重新生成 |
| `.github/workflows/build-release.yml` | 删除模型与 native runtime 打包检查 |
| `Dockerfile` | 确认不再复制模型资产或安装专属依赖 |

### 3.3 配置迁移

新增一次性迁移：

1. 读取 `webui_overrides.json`。
2. 发现 `local_deploy.mode` 时记录迁移事件。
3. 删除该键或迁移到 `embedding.mode=remote|disabled`。
4. 若远程 Embedding 未配置，则设置 `embedding.mode=disabled`。
5. UI 显示语义检索不可用，而不是启动失败。
6. 写入配置前创建备份，失败恢复原文件。

### 3.4 数据迁移

新增脚本建议：

```text
scripts/migrate_embeddings_to_remote.py
```

脚本步骤：

1. 只读打开原数据库并识别向量表和维度。
2. 校验目标 Provider、模型和输出维度。
3. 创建带时间戳备份。
4. 在临时数据库中创建目标维度表。
5. 分批读取记忆、子块、KG 实体和 KG 关系文本。
6. 调用远程 Embedding，支持限流重试和断点。
7. 校验行数、空向量、范数和抽样检索质量。
8. 原子替换数据库。
9. 失败时保留原库并删除临时文件。

## 4. Ollama 退役

### 4.1 生产代码删除面

| 文件 | 删除内容 |
|---|---|
| `model_router.py` | Ollama 模型翻译、零成本、默认模型、流式/非流式特判 |
| `web/server.py` | 环境导入、启动恢复、降级模式特判 |
| `web/routers/setup.py` | Ollama 测试、保存和自动注册 |
| `web/routers/model_discovery.py` | Ollama 免费标记 |
| `config/provider_metadata.json` | Ollama Provider、模型、cap 和 fallback |
| `.env.example` | 全部 `OLLAMA_*` 变量 |
| `setup_wizard.py` | Ollama 字段 |
| `web/model_health.py` | 因 metadata 删除而同步调整的收集逻辑 |

### 4.2 用户配置迁移

启动迁移必须处理：

- `models.providers.ollama`
- `models.chat_model.provider=ollama`
- `models.routes.*.client=ollama`
- `provider_ollama.key`
- `DEFAULT_PROVIDER=ollama`

迁移规则：

1. 配置中存在 Ollama 时先寻找启用且凭证有效的自定义 Provider。
2. 若只有一个可用 Provider，迁移聊天模型和路由到该 Provider 的默认模型。
3. 若有多个候选，不自动猜测，清空失效引用并在 UI 显示迁移待办。
4. 若无候选，进入“模型未配置”状态，不静默回退到未知服务商。
5. 删除占位凭证前先完成配置写盘并验证。
6. 迁移过程不记录旧凭证内容。

### 4.3 防复活扫描

生产目录必须对以下模式零命中，历史文档和迁移测试可进入显式 allowlist：

```text
ollama
OLLAMA_
local-deploy
local_deploy
LocalDeploy
LocalEmbed
bge-small-zh-v1.5
onnxruntime
tokenizers
```

## 5. 自定义服务商重构

### 5.1 新增后端组件

建议新增：

```text
web/providers/schemas.py
web/providers/service.py
web/providers/repository.py
web/providers/runtime_registry.py
web/providers/diagnostics.py
web/providers/url_normalizer.py
web/providers/secure_transport.py
```

职责：

- `schemas.py`：请求、响应、诊断和稳定错误码。
- `service.py`：事务编排和引用完整性。
- `repository.py`：ConfigService 与 CredentialVault 组合访问。
- `runtime_registry.py`：内存客户端生命周期。
- `diagnostics.py`：发现、探针、延迟和错误分类。
- `url_normalizer.py`：base URL、models path、chat path 规范化。
- `secure_transport.py`：DNS、安全目标、连接、重定向和超时策略。

### 5.2 API 变更

保留兼容路径，逐步升级响应：

```http
GET    /api/v1/models/providers
POST   /api/v1/models/providers
PUT    /api/v1/models/providers/{id}
DELETE /api/v1/models/providers/{id}
POST   /api/v1/models/providers/{id}/test
POST   /api/v1/models/providers/{id}/discover
GET    /api/v1/models/providers/{id}/references
```

创建和更新支持 `validate_only=true`，便于表单先验证再保存。

### 5.3 Provider 事务

创建：

1. 校验 ID、协议和字段长度。
2. 规范化 URL。
3. 通过安全出站层进行连接测试。
4. 加密准备密钥，但不覆盖旧状态。
5. 生成配置和运行时客户端候选。
6. 写临时配置与临时凭证。
7. 原子提交配置和凭证。
8. 注册客户端。
9. 失效缓存。
10. 任何失败执行补偿并验证无孤儿文件。

更新：

1. 快照旧配置、凭证状态和客户端。
2. 构建并验证新候选。
3. 原子替换持久化状态。
4. 切换运行时客户端。
5. 失败恢复全部旧状态。

删除：

1. 收集路由、聊天模型、Agent 和其他引用。
2. 有引用时返回 `PROVIDER_IN_USE` 和引用列表。
3. 注销运行时客户端。
4. 删除配置和凭证。
5. 任何失败恢复运行时与持久化状态。

### 5.4 模型发现

- 每个 Provider 单独缓存。
- 成功缓存 30 分钟，失败缓存 30–60 秒。
- 一个 Provider 失败不影响其他 Provider。
- 支持手动模型，不强制 `/models` 存在。
- 发现结果包含状态、阶段、延迟和警告。
- 将 embedding、TTS、图像、视频模型分类展示，不简单丢弃。
- 模型能力标记区分“服务端声明”“规则推断”“用户覆盖”。

### 5.5 前端改造

`ModelsView.vue` 拆分建议：

```text
views/ModelsView.vue
components/providers/ProviderList.vue
components/providers/ProviderEditor.vue
components/providers/ProviderConnectionTest.vue
components/providers/ProviderModelPicker.vue
components/providers/ProviderDiagnostics.vue
components/providers/ProviderReferencesDialog.vue
stores/providers.ts
```

移动交互：

- Provider 列表为一级页面。
- 编辑器使用全屏 Sheet 或独立详情路由。
- API Key 只允许替换，不回填。
- URL 输入提供自动补全 `/v1` 的建议，但保存前展示最终规范化地址。
- “测试连接”和“发现模型”分开展示阶段结果。
- 允许手动填写模型 ID。
- 错误用稳定错误码映射本地化文案，不依赖原始上游字符串。

## 6. 共享导航与移动壳

### 6.1 新增文件

```text
web/frontend/src/navigation/capabilities.ts
web/frontend/src/components/layout/DesktopShell.vue
web/frontend/src/components/layout/MobileAppShell.vue
web/frontend/src/components/layout/MobileBottomNav.vue
web/frontend/src/components/layout/CapabilityDrawer.vue
web/frontend/src/components/layout/QuickStatusSheet.vue
web/frontend/src/composables/useResponsiveShell.ts
web/frontend/src/composables/useViewportInsets.ts
```

### 6.2 修改文件

| 文件 | 变更 |
|---|---|
| `routes.ts` | 路由 meta 引用能力 ID；删除 local deploy |
| `AppLayout.vue` | 按断点选择桌面/移动壳 |
| `SideBar.vue` | 从能力表生成桌面入口 |
| `TopBar.vue` | 移动端三段式顶部栏 |
| `theme.css` | safe-area、Sheet、玻璃层、键盘变量 |
| `sumeru-tokens.css` | 底栏高度、48dp 触控、极光玻璃 token |
| `SumeruIcon.vue` | 增加统一 SVG 图标集 |
| `zh.ts`、`en.ts` | 能力分组、移动导航和可访问文案 |

### 6.3 响应式断点

- `< 768px`：移动壳。
- `768px–1023px`：紧凑壳，可根据横屏切换侧栏。
- `>= 1024px`：桌面壳。

断点只能决定布局，不得决定业务能力是否存在。

## 7. 页面适配清单

| 页面 | 移动适配重点 |
|---|---|
| Chat | 工具栏收敛、输入区安全区、会话抽屉、终端 FAB |
| Insight | 图谱降级、Tab 横向滚动、列表优先 |
| Schedule | 日历与任务列表切换、编辑 Sheet |
| Media | 单列素材、上传 FAB、播放器全宽 |
| Health | 指标单列、详情折叠 |
| Dashboard | 图表单列、横向滚动或替代摘要 |
| Agents | 列表—详情、权限分组、壁纸焦点编辑 |
| Models | Provider 列表—编辑—诊断三层 |
| Tools | 搜索、分组、危险操作确认 |
| MCP | Server 列表、详情 Sheet、日志折叠 |
| Plugins | 插件列表、权限与状态清晰 |
| Mail | 账户、规则、状态分层 |
| Settings | 聚合目录，二级设置页面 |
| Workflows | 工作流卡片、编辑器横屏/全屏 |
| Disclaimer/Sponsor | 可读宽度、外链安全 |

## 8. 终端变更

### 8.1 Web 终端

修改 `ChatTerminal.vue`：

- 抽离终端会话状态与容器布局。
- 移动端以底部 Sheet 展示。
- Sheet 支持 50%、90% 两档或拖拽。
- 监听 VisualViewport，键盘出现时调整终端可用高度。
- 屏幕旋转仅执行 fit/resize，不重建 session。
- FAB 避开底栏和手势区。
- 关闭前提示会话影响。

### 8.2 服务端终端

修改 `web/ws_hub.py` 前先建立测试：

- 连接归属校验。
- 非法 `term_sid` 拒绝。
- 断线进程树回收。
- 输入和输出大小限制。
- 并发会话数量限制。
- Windows subprocess 和 Unix PTY 一致退出语义。

## 9. 壁纸变更

### 9.1 API 与持久化

扩展 Agent UI 配置：

```json
{
  "main_wallpaper": "/media/wallpapers/a.webp",
  "wallpaper_focus": {"x": 0.5, "y": 0.35},
  "wallpaper_overlay": 0.28,
  "wallpaper_motion": "reduced"
}
```

旧配置无新字段时使用默认值，保证向后兼容。

### 9.2 前端

`AgentBackdrop.vue`：

- 将焦点映射为 `background-position`。
- 保留预加载与交叉淡化。
- 根据性能档位关闭滤镜、粒子或转场。
- 失败回退默认壁纸。

`AgentsView.vue`：

- 上传后提供焦点选择器。
- 预览刘海、顶栏、消息区、底栏遮挡。
- 提供遮罩强度和动效选项。

## 10. Android 系统壳

### 10.1 工程结构

```text
android/
├─ app/
├─ core/webcontainer/
├─ core/security/
├─ core/bridge-api/
├─ feature/terminal-runtime/
├─ build-logic/
└─ gradle/libs.versions.toml
```

### 10.2 WebView 安全配置

- 使用 `WebViewAssetLoader` 加载内置前端资源。
- 禁止通用文件 URL 访问。
- 禁止 mixed content。
- Release 禁用 WebView 调试。
- 外部链接交给系统浏览器并做协议 allowlist。
- 下载和上传通过明确桥接。
- Bridge 只向受信任 origin 暴露。
- 页面导航离开受信任 origin 时立即撤销 Bridge。

### 10.3 Bridge 最小接口

```text
getInsets()
pickFile(accept, maxBytes)
shareText(text)
setSecureToken(tokenHandle)
openTerminal()
getRuntimeStatus()
stopRuntime()
```

不得提供 `runCommand(string)`、`readFile(path)` 或 `openIntent(uri)` 这类通用能力。

### 10.4 终端 runtime

实现前必须先完成：

1. 组件和 bootstrap BOM。
2. 许可证与源码对应关系。
3. 目标应用商店政策预审。
4. ABI、包体和安装空间预算。
5. RuntimeSupervisor 状态机。
6. 单实例、进程树回收和异常恢复 PoC。

任一项未通过，正式包禁用 `feature:terminal-runtime`，Web 终端仍可连接远端服务端终端。

## 11. 测试与 CI 变更

### 11.1 后端新增测试

```text
tests/test_local_ai_retirement.py
tests/test_ollama_migration.py
tests/test_embedding_migration.py
tests/test_provider_crud.py
tests/test_provider_transactions.py
tests/test_provider_discovery.py
tests/test_provider_diagnostics.py
tests/test_provider_secure_transport.py
tests/test_provider_references.py
tests/test_terminal_lifecycle.py
tests/test_wallpaper_metadata.py
```

### 11.2 前端测试栈

新增前先确认版本兼容：

- Vitest。
- Vue Test Utils。
- jsdom 或 happy-dom。
- Playwright 用于移动视口端到端测试。

增加脚本：

```text
typecheck
test
test:e2e
```

### 11.3 Android 测试

- JVM 单元测试：Bridge 输入校验、导航策略、Token handle。
- Robolectric 或仪器测试：WebView 配置和生命周期。
- Compose 仅用于系统壳 UI 时测试启动、错误页和终端宿主。
- Macrobenchmark：冷启动、页面切换、滚动和壁纸性能。

### 11.4 CI 门禁

- 本地 AI/Ollama 扫描不得允许失败。
- Provider 安全与事务测试进入 strict job。
- 前端必须执行安装、typecheck、单测和 build。
- 移动视口 E2E 至少覆盖五底栏、全部能力抽屉和全部路由。
- Android lint、test、assemble、依赖和许可证检查通过。
- 不再对关键测试使用 `continue-on-error` 或 `|| true`。

## 12. 文档变更

必须更新：

```text
README.md
SETUP.md
USAGE.md
docs/ARCHITECTURE.md
docs/API.md
.env.example
docs/mobile/*
```

必须删除当前文档中的以下错误表述：

- 默认本地 BGE。
- 可选 Ollama 部署。
- 移动端完整 Compose 业务 UI 是当前方向。
- 移动端首版不保留任何管理能力。

历史计划保留原文，但顶部增加“已被 ADR-MOB2 系列取代”的标记。


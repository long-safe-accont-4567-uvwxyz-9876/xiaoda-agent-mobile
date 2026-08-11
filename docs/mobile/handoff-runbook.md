# 移动端重构接管运行手册

## 1. 给新上下文的第一段指令

可直接复制给新的开发上下文：

```text
你正在接管 Xiaoda Agent 移动端架构重构。先阅读 docs/mobile/README.md、architecture-v2.md、change-spec-v2.md、implementation-plan-v2.md、acceptance-matrix-v2.md、handoff-runbook.md。不要使用仓库外旧移动方案作为当前事实源。目标架构是：共享 Vue WebUI + 远端 FastAPI/AgentCore + Android 安全系统壳；移动端不提供终端，桌面 Web 终端保持不变。必须删除本地 AI、ONNX 本地 Embedding、内置 BGE 和 Ollama；必须保留其余现有功能入口并使用方案 C 分层导航；自定义 OpenAI-compatible Provider 是 P0 优化项。先检查 git 状态和当前任务编号，只执行 implementation-plan-v2.md 中一个未完成任务；先写失败测试，再改实现，再按 acceptance-matrix-v2.md 验证。未经明确要求不要提交或推送。
```

## 2. 接管必做检查

### 2.1 仓库身份

在仓库根目录执行：

```powershell
git status --short --branch
git remote -v
git log -1 --oneline
```

确认：

- 当前目录是目标仓库。
- 当前分支符合任务安排。
- 未跟踪文件归属明确。
- 不覆盖其他人的未提交修改。

### 2.2 文档真相源

只把以下目录作为当前移动重构真相源：

```text
docs/mobile/
```

仓库外：

```text
D:\移动Xiaoda\xiaoda-agent-mobile-refactor-plan.md
D:\移动Xiaoda\xiaoda-agent-mobile-implementation-checklist.md
```

属于旧方案输入。遇到冲突时，以 `docs/mobile` 为准。

### 2.3 当前技术基线

- 后端：Python 3.11+、FastAPI、Pydantic、WebSocket、SQLite。
- 前端：Vue 3、TypeScript、Vite、Vue Router、Pinia、Naive UI、xterm.js。
- Android：`android/` 四模块 Kotlin DSL 系统壳已按 ADR-MOB2-007 提前完成 G5-01，使用 JDK 17、Gradle 8.11.1、AGP 8.9.2、Kotlin 2.1.20 和 SDK 35；这不授权开始 G5-02。
- 产品版本基线：`0.5.70`，实施时先重新确认。

## 3. 任务领取规则

1. 打开 `implementation-plan-v2.md`。
2. 找到当前阶段第一个 `[ ]` 或 `[~]` 项。
3. 检查所有前置任务是否 `[x]`。
4. 一次只领取一个可独立验证任务。
5. 将该项标为 `[~]` 并记录操作者/分支。
6. 先增加能失败的测试。
7. 实现最小变更。
8. 运行目标测试和相关回归。
9. 按验收矩阵保存证据。
10. 全部通过后改为 `[x]`。

禁止跨阶段“顺手改完”，尤其禁止把 Provider 安全重构与移动 UI 混在一起。ADR-MOB2-007 只豁免 G5-01 安全空壳，当前下一任务按阶段顺序选择 G2-04。

## 4. 推荐实施切片

### 切片 A：退役扫描与迁移框架

- 任务：G1-01、G1-02。
- 主要文件：测试、配置迁移模块。
- 不删除生产代码，先固定退役标准。

### 切片 B：向量迁移

- 任务：G1-03。
- 主要文件：迁移脚本、向量存储测试。
- 必须使用数据库副本。

### 切片 C：本地 AI/Ollama 删除

- 任务：G1-04 至 G1-08。
- 分为前端、后端、依赖/资产、Ollama 四个逻辑提交。

### 切片 D：Provider 内核

- 任务：G2-01 至 G2-05。
- 先错误协议和安全出站，再做事务。
- 当前：G2-03 已关闭，下一任务是 G2-04 Provider 应用服务。

### 切片 E：Provider 体验

- 任务：G2-06 至 G2-09。
- 模型发现、连接诊断、前端和 CI。

### 切片 F：方案 C 壳

- 任务：G3 全部。
- 先能力事实源，再移动壳。

### 切片 G：逐页适配

- 任务：G4-01。
- 每次处理 1–3 个相邻页面并保存多视口截图。

### 切片 H：移动页面和壁纸

- 任务：G4-01、G4-03、G4-04。
- G4-02 移动终端已按 ADR-MOB2-010 取消；只保留桌面 Web 终端。

### 切片 I：Android 壳

- 任务：G5-01 至 G5-04。
- Android 壳不包含终端 runtime 或终端 Bridge。

### 切片 J：移动端终端移除

- G5-05、G5-06 已取消，不再作为阻塞项或条件功能。
- 验收重点是模块、构建开关、Bridge、移动 UI 和 APK 中不存在终端能力。
- `web/frontend/src/components/chat/ChatTerminal.vue` 与服务端 terminal 协议仅供桌面 Web 使用。

## 5. 关键代码入口

| 领域 | 当前入口 |
|---|---|
| 前端路由 | `web/frontend/src/routes.ts` |
| 桌面布局 | `web/frontend/src/components/layout/AppLayout.vue` |
| 桌面导航 | `web/frontend/src/components/layout/SideBar.vue` |
| 顶部状态 | `web/frontend/src/components/layout/TopBar.vue` |
| Chat | `web/frontend/src/views/ChatView.vue` |
| 桌面 Web 终端 | `web/frontend/src/components/chat/ChatTerminal.vue`（移动端不得挂载） |
| 壁纸 | `web/frontend/src/components/layout/AgentBackdrop.vue` |
| Agent 壁纸编辑 | `web/frontend/src/views/AgentsView.vue` |
| Provider UI | `web/frontend/src/views/ModelsView.vue` |
| Provider API | `web/routers/models.py` |
| 模型发现 | `web/routers/model_discovery.py` |
| Provider 探针 | `web/probes.py` |
| Provider 客户端 | `web/custom_providers.py` |
| Provider 安全出站 | `security/safe_outbound.py` |
| 模型路由 | `model_router.py` |
| 配置 | `web/config_service.py` |
| 凭证 | `web/_provider_keys.py`、`security/credential_vault.py` |
| 通用 SSRF/IP 分类 | `security/ssrf_guard.py` |
| WS/PTY | `web/ws_hub.py` |
| 本地部署 API | `web/routers/local_deploy.py` |
| 本地 Embedding | `memory/local_embed.py`、`memory/vector_store.py` |
| 启动装配 | `core/bootstrap.py`、`web/server.py` |

## 6. 基线命令

以下是建议命令，实际运行前先确认仓库脚本和环境：

```powershell
python scripts/check_version_sync.py --ci
python -m pytest tests -q --tb=short
python -m ruff check .
npm --prefix web/frontend run build
git diff --check
```

前端测试栈落地后追加：

```powershell
npm --prefix web/frontend run typecheck
npm --prefix web/frontend run test
npm --prefix web/frontend run test:e2e
```

Android 工程落地后追加：

```powershell
android\gradlew.bat lint test assembleDebug assembleStaging assembleRelease
python android\scripts\verify_apk.py android\app\build\outputs\apk\debug\app-debug.apk android\app\build\outputs\apk\staging\app-staging.apk android\app\build\outputs\apk\release\app-release.apk
```

不要调用真实付费模型进行常规测试。使用 MockTransport、Fake Provider 或专用测试服务。

## 7. 搜索与防误删

### 7.1 本地 AI/Ollama 搜索词

```text
ollama|OLLAMA_|local-deploy|local_deploy|LocalDeploy|LocalEmbed|bge-small-zh-v1.5|onnxruntime|tokenizers
```

使用专门测试实现扫描，不要只靠人工命令。历史文档、迁移测试和退役说明需要 allowlist。

### 7.2 删除依赖前

删除任何依赖前必须：

1. 搜索 import 和运行时动态导入。
2. 检查 `requirements.txt`、`pyproject.toml`、lock、Docker 和 CI。
3. 检查 PyInstaller/发布脚本和 package data。
4. 运行受影响测试。
5. 检查是否被其他能力复用。

`numpy` 和 `sqlite-vec` 不能因为删除本地模型就直接删除，它们可能有其他用途。

## 8. 常见错误预防

### 8.1 把“本地部署”误解为服务器部署

本轮只删除本地 AI 推理、Ollama 和对应 UI，不删除 FastAPI、Docker、服务器启动和远程 CLI。

### 8.2 只删页面不删运行时

删除 `/local-deploy` 页面并不等于删除本地 Embedding；删除 Ollama Provider也不等于删除 ONNX。必须分别验收。

### 8.3 忘记向量维度

512 维旧库不能直接切到 1024 维模型。任何 Provider 切换前先检查维度。

### 8.4 Provider 校验与连接分离

只调用 `validate_url()` 后再让 SDK 独立解析 DNS 不安全。真实连接必须消费安全解析结果。

G2-03 已通过 `security/safe_outbound.py` 合并连接阶段异步 DNS 校验与 pinned IP 拨号。新增 Provider 出站路径必须复用 `build_safe_http_client()` 或 `build_openai_client()`，不得直接创建普通 `httpx.AsyncClient` 或 `AsyncOpenAI`。

管理员网络策略：

```text
PROVIDER_ALLOW_HOSTS=provider.internal,host.docker.internal
PROVIDER_ALLOWED_HTTP_PORTS=80,8080
PROVIDER_ALLOWED_HTTPS_PORTS=443,8443
```

- 所有值均为逗号分隔；host 使用不带 scheme、路径和端口的 hostname，端口范围为 1–65535。
- 默认不授权任何私网或宿主别名；HTTPS 默认只允许 443，HTTP 默认端口策略为 80。
- `PROVIDER_ALLOW_HOSTS` 是 Provider 专属授权，不能用 `SSRF_ALLOW_HOSTS` 替代。
- 显式授权不允许公网明文 HTTP；HTTP 目标的全部 DNS 结果仍必须属于非公网地址。

### 8.5 Provider 三态分裂

配置 JSON、密钥文件和内存客户端必须事务化。任何失败都要恢复三者。

### 8.6 复制移动业务页面

Android 壳不重写 Agent、Models、MCP 等业务 UI。优先适配共享 WebUI。

### 8.7 误恢复移动端终端

移动端终端已由 ADR-MOB2-010 正式取消。不得重新加入 Termux、PTY、远程 CLI、终端 Bridge、移动 FAB/Sheet 或 research APK；桌面 Web 终端不受影响。

### 8.8 隐藏功能代替保留功能

所有非退役生产页面必须能从移动导航访问。不能因为布局困难直接隐藏。

## 9. 遇到冲突时的决策顺序

1. 用户当前明确决策。
2. `docs/mobile/architecture-v2.md` 的接受 ADR。
3. `change-spec-v2.md` 的边界。
4. `implementation-plan-v2.md` 的任务顺序。
5. 当前生产代码事实。
6. 旧移动文档和历史计划。

如果必须改变 1–4：

- 停止实现。
- 新增 ADR，写明上下文、选择、替代项和后果。
- 同步更新变更规格、实施计划和验收矩阵。
- 再继续编码。

## 10. 任务完成后的交接摘要

每次会话结束前输出并写入证据：

```text
完成任务：
未完成任务：
当前分支：
最后提交：
修改文件：
已运行验证：
通过结果：
已知失败：
数据迁移状态：
下一任务编号：
阻断项：
```

## 11. 当前状态

- 文档设计：已完成。
- 生产实现：G1、G2-01、G2-02、G2-03 已完成；G2-04 至 G4 尚未完成。
- Android 工程：G5-01 按 ADR-MOB2-007 提前完成，四模块和 debug/staging/release 三变体可构建。
- 移动端终端：已按 ADR-MOB2-010 删除；桌面 Web 终端保留。
- G2-03 验证：专项 `16 passed`、相关定向 `129 passed`、后端全量 `3058 passed, 8 skipped`、前端生产构建和静态门禁通过，最终安全复审 Critical `0` / Important `0`。
- 下一步：G2-04 Provider 应用服务；先抽离 repository、credential store 与 runtime registry，再以故障注入实现创建事务。G5-02 必须等待 G2 至 G4 全部通过。

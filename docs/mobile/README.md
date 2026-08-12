# Xiaoda Agent 移动端重构文档入口

## 文档状态

- 状态：设计冻结，等待实施。
- 决策日期：2026-08-09。
- 适用版本基线：Xiaoda Agent `0.5.70`。
- 权威目录：`docs/mobile/`。
- 旧文档：仓库外的 `xiaoda-agent-mobile-refactor-plan.md` 与 `xiaoda-agent-mobile-implementation-checklist.md` 仅作为历史输入，不再作为实施依据。

## 接管顺序

任何新会话、开发者或自动化 Agent 接管时，必须按以下顺序阅读：

1. `docs/mobile/README.md`
2. `docs/mobile/architecture-v2.md`
3. `docs/mobile/change-spec-v2.md`
4. `docs/mobile/implementation-plan-v2.md`
5. `docs/mobile/acceptance-matrix-v2.md`
6. `docs/mobile/handoff-runbook.md`

没有读完前六份文档，不得开始删除模块、改 Provider、改桌面终端协议或引入 Android 依赖。

## 最终产品决策

1. 移动端复用现有 Vue 3 WebUI，不再复制一套完整 Compose 业务 UI。
2. 桌面与移动使用同一套路由、页面、API 和状态模型，只切换导航外壳与响应式布局。
3. 移动端采用方案 C：底部五入口、左上全部能力抽屉、右上快捷状态；移动端不提供终端。
4. 所有现有业务能力继续保留入口；只删除本地 AI 部署、Ollama 和移动端目录选择。
5. Android 壳负责安全存储、系统返回、文件选择、通知、分享和深链，并通过内嵌 Python 后端（Chaquopy）在 `127.0.0.1` 承载原 `web.server` 业务内核，不提供终端 Bridge。
6. Termux、PTY、远程 CLI 自动启动、研究 APK 和移动终端 UI 均不进入移动端；桌面 Web 终端继续保留（ADR-MOB2-010）。
7. 自定义服务商成为模型接入主路径，优先优化 OpenAI-compatible Provider。
8. 默认图标体系为 A“极光玻璃”；壁纸完整保留并支持焦点、安全区和性能降级。

## 不可违反的边界

- 禁止在 Android 内嵌的 Python 后端中运行本地模型推理（Ollama/ONNX/BGE）；允许在 `127.0.0.1` 内嵌原 `web.server` 承载业务内核（ADR-MOB2-011）。
- 禁止恢复 Ollama 专属 Provider、配置或 UI。
- 禁止恢复 ONNX 本地 Embedding、内置 BGE 模型或本地部署页面。
- 禁止恢复移动端 Termux、PTY、远程 CLI、终端 Bridge、终端 FAB/Sheet 或研究 APK。
- 禁止为移动端复制第二套 Chat Store、Agent API 或壁纸目录；桌面终端后端保持单一实现。
- 禁止删除 Docker、FastAPI 启动和服务器部署基础设施；它们属于远端服务运行能力，不是移动端本地 AI 部署。
- 禁止让移动导航组件各自维护路由清单；导航元数据必须只有一个事实来源。
- 禁止在日志、错误、配置 JSON、URL 或前端状态中暴露 Provider 密钥和认证令牌。

## 阶段门禁

```text
G0 文档与基线冻结
  -> G1 本地 AI/Ollama 退役
  -> G2 自定义服务商可靠性与安全
  -> G3 共享导航和移动壳
  -> G4 页面移动适配与壁纸
  -> G5 Android 安全系统壳
  -> G6 集成、发布和回滚验收
```

任何阶段失败时停止后续阶段。禁止用“后面再补测试”绕过门禁。唯一已批准例外是 ADR-MOB2-007：G5-01 安全空壳与 APK CI 可提前并行，但不得据此开始 G5-02 或放宽 G1 至 G4 的关闭条件。

## 文档维护规则

- 架构边界变化：更新 `architecture-v2.md` 并新增 ADR。
- 文件、API、配置和依赖变化：更新 `change-spec-v2.md`。
- 实施顺序或任务拆分变化：更新 `implementation-plan-v2.md`。
- 验收口径变化：更新 `acceptance-matrix-v2.md`。
- 接管命令、环境或已知失败变化：更新 `handoff-runbook.md`。
- 每个已完成任务必须在实施计划中记录修改文件、验证命令、结果和剩余风险。

## 完成定义

只有同时满足以下条件，才能宣布移动端重构完成：

- 本地 AI、Ollama 和本地部署导航的生产引用扫描为零。
- 自定义服务商 CRUD、模型发现、连接测试、调用和错误诊断通过自动化测试。
- 现有业务页面全部能从移动导航访问。
- 360dp、390dp、412dp 和桌面宽度下没有不可达操作。
- 移动端无终端入口或运行时；桌面终端回归、壁纸、软键盘、安全区和旋转场景通过验收。
- Android 壳不包含 AgentCore、本地模型和 Provider 密钥。
- 后端、前端、Android、文档和发布门禁全部通过。

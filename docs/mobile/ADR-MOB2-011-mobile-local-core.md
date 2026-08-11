# ADR-MOB2-011：移动端改为 Android 原生本地核心

- 状态：Accepted / Implementation in progress
- 日期：2026-08-11
- 取代：G5-02/G5-03 中“移动端依赖远程 Xiaoda/FastAPI 服务”的运行时路径

## 决策

Android APK 不再要求用户部署 Xiaoda 服务端。移动端采用独立的 Vue 入口作为受信任 UI，所有模型请求、Provider 配置、密钥、会话、附件和后续高级能力均由 Kotlin 本地核心负责。

“本地核心”不等于本地大模型或手机内服务器：APK 不嵌入 Python、FastAPI、Docker、Termux、PTY 或本地模型 runtime。模型推理由用户选择的云 Provider 完成，Android 原生网络层直接调用 HTTPS API。

## 安全边界

1. API Key 只进入 Android 原生层，由 Android Keystore 生成的 AES-GCM 密钥加密保存。
2. WebView 只能看到 `hasApiKey`，不能读取 API Key、Authorization header 或 Provider 原始响应头。
3. Bridge 使用固定方法白名单和固定 `appassets` origin；不提供通用命令、文件路径、Intent 或终端接口。
4. Release/Staging Provider 地址必须使用 HTTPS；Debug 仅额外允许明确的模拟器/回环开发地址。
5. APK 继续执行敏感信息、Python runtime、终端和本地模型防复活扫描。

## 第一阶段能力

- Provider/API Key 设置
- 模型读取与选择
- OpenAI-compatible/Anthropic 流式聊天
- 本地会话历史
- 基础 Agent 与系统提示词
- 图片、纯文本、PDF、DOCX 文件选择和本地保存

## 后续 Kotlin 能力

多 Agent、长期记忆与向量检索、WorkManager 定时任务、受限浏览器自动化、工具替代层、本地插件和复杂文档处理必须通过明确的 Kotlin 接口逐项实现，不得通过恢复 Python runtime 或移动终端绕过。

## 结果

APK 可以形成“下载安装 → 配置 Provider/API Key/模型 → 直接聊天”的闭环。高级能力在本地 Kotlin 实现完成前显示明确状态，不伪装成已可用能力。
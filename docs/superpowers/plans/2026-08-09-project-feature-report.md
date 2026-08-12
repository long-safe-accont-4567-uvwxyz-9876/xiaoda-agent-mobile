# Xiaoda Agent Project Feature Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一份完整覆盖 Xiaoda Agent 产品、源码模块、前端、API、数据、扩展和工程能力的单文件交互式 HTML 报告。

**Architecture:** 使用一个自包含 HTML 文件承载语义化静态正文、结构化模块数据、原生 SVG、CSS 主题和无依赖 JavaScript。静态正文保证脚本禁用时仍可阅读，结构化数据统一渲染模块百科并驱动搜索、分类筛选、折叠和统计。

**Tech Stack:** HTML5、CSS3、原生 JavaScript、内联 SVG、浏览器 Clipboard/IntersectionObserver API。

---

### Task 1: 建立单文件报告骨架

**Files:**
- Create: `d:\移动Xiaoda\xiaoda-agent-project-report.html`

- [ ] **Step 1: 创建语义化页面结构**

加入 `header`、`aside`、`main` 和 12 个带稳定 ID 的章节，设置中文语言、UTF-8、viewport、项目版本 `0.5.70` 与生成日期 `2026-08-09`。

- [ ] **Step 2: 实现须弥草元素视觉令牌**

在 `:root` 定义森林背景、草绿、嫩芽绿、智慧金、文本、边框和玻璃面板变量；实现响应式双栏布局、模块卡片、统计块、标签、表格、时间线和打印样式。

- [ ] **Step 3: 加入本地 SVG 视觉元素**

使用内联 SVG 绘制草元素徽记与系统分层架构，不引用外部图片或字体。

### Task 2: 写入完整项目内容

**Files:**
- Modify: `d:\移动Xiaoda\xiaoda-agent-project-report.html`

- [ ] **Step 1: 写入项目总览与规模统计**

呈现定位、技术栈、版本、接入方式、核心能力以及后端包、根级模块、Web 路由、前端页面和测试规模。

- [ ] **Step 2: 写入架构和运行链路**

描述进程入口、FastAPI 生命周期、AgentCore 装配、请求上下文、记忆检索、模型调用、工具验收循环、结果后处理和后台持久化。

- [ ] **Step 3: 写入结构化模块数据**

内嵌覆盖全部生产后端包、根级 Python 模块、Web 支撑模块、前端页面、组件、Store、路由组、工具分类和工程配套模块的数据数组；每项包含职责、能力、依赖、入口、文件和注意事项。

- [ ] **Step 4: 写入数据、扩展、配置和风险章节**

覆盖 SQLite/FTS/sqlite-vec/KG/FSRS、工具/MCP/插件/市场/工作流、环境变量/WebUI 覆盖/Workspace、部署通道、测试 CI、故障注入、评测、复杂区域和阅读路线。

### Task 3: 实现交互功能

**Files:**
- Modify: `d:\移动Xiaoda\xiaoda-agent-project-report.html`

- [ ] **Step 1: 渲染模块百科**

通过 `renderCards()` 将结构化数据转为可折叠卡片，为每张卡生成可搜索文本、分类属性、文件路径和能力标签。

- [ ] **Step 2: 实现搜索与筛选**

通过 `applyFilters()` 同时处理关键字与分类，更新可见卡片和命中数；无结果时显示明确空状态。

- [ ] **Step 3: 实现导航与阅读控制**

使用 `IntersectionObserver` 高亮当前目录；实现移动目录、全部展开/折叠、主题切换、打印和返回顶部。

- [ ] **Step 4: 实现路径复制降级**

优先使用 `navigator.clipboard.writeText()`，失败时使用临时 textarea 与 `document.execCommand('copy')`，并显示短暂状态反馈。

### Task 4: 静态与浏览器验证

**Files:**
- Verify: `d:\移动Xiaoda\xiaoda-agent-project-report.html`

- [ ] **Step 1: 检查单文件与离线约束**

确认文件存在且非空，检索并确保不存在 `http://`、`https://`、CDN、外部脚本、外部样式或远程图片引用。

- [ ] **Step 2: 检查关键覆盖**

确认 `agent_core`、`core`、`memory`、`db`、`tool_engine`、`tools`、`emotion`、`security`、`transports`、`plugins`、`web`、`chaos`、`evaluation`、`quality`、全部前端页面名和主要路由组均出现在报告中。

- [ ] **Step 3: 浏览器桌面验证**

打开本地文件，检查控制台、页面首屏、目录、搜索、筛选、折叠、主题切换、复制和打印入口。

- [ ] **Step 4: 浏览器移动端验证**

调整为窄屏视口，确认目录抽屉、卡片、表格、统计和架构图无不可用遮挡或横向页面溢出。

- [ ] **Step 5: 修复发现的问题并复验**

针对控制台错误、缺失内容、交互失效或布局溢出更新 HTML，并重复对应检查直至通过。

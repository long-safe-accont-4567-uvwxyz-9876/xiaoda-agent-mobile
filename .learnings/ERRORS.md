# Errors

## [ERR-20260810-012] wallpaper-import-order

**Logged**: 2026-08-10T23:16:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
新增原子持久化依赖后，标准库 import 顺序不符合 Ruff 规则。

### Error
```text
I001 Import block is un-sorted or un-formatted
```

### Context
- `copy` 被放在 `hashlib` 后面。
- 功能测试通过，但静态门禁失败。

### Suggested Fix
按项目 Ruff 排序规则排列标准库 imports，并重跑定向检查。

### Metadata
- Reproducible: yes
- Related Files: web/agent_registry.py

### Resolution
- **Resolved**: 2026-08-10T23:17:00+08:00
- **Notes**: 已调整 import 顺序。

---

## [ERR-20260810-011] terminal-reconnect-red-test

**Logged**: 2026-08-10T22:55:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: frontend

### Summary
终端断线后前端保留永久失效的会话标签，重连时状态无法收敛。

### Error
```text
expected terminal tabs to have length 0 after ws_connected but got 1
```

### Context
- 定向组件测试先触发 `ws_disconnected`，再触发 `ws_connected`。
- 组件只监听断线事件，没有重连清理或恢复策略。

### Suggested Fix
重连后清理服务端已回收的 disconnected 会话，并释放本地 xterm 资源。

### Metadata
- Reproducible: yes
- Related Files: web/frontend/src/components/chat/ChatTerminal.vue, web/frontend/src/components/chat/ChatTerminal.test.ts

### Resolution
- **Resolved**: 2026-08-10T22:57:00+08:00
- **Notes**: 新增 `ws_connected` 状态收敛处理，定向红测试用于验证。

---

## [ERR-20260810-010] multi-file-stale-patch-context

**Logged**: 2026-08-10T20:49:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
跨文件补丁中测试文件已被并行修改，旧上下文未匹配，但另一文件仍成功修改。

### Error
```text
Failed to find expected lines in nativeBridge.test.ts
```

### Context
- 补丁同时修改前端测试和 Python 工具文件。
- 测试文件在补丁应用前已更新为正确的端口回调方式。

### Suggested Fix
高频变化文件在组合补丁前重新读取，并在部分成功后分别核对每个文件状态。

### Metadata
- Reproducible: no
- Related Files: web/frontend/src/platform/nativeBridge.test.ts, tools/file_tools_v2.py
- See Also: ERR-20260810-008

### Resolution
- **Resolved**: 2026-08-10T20:49:00+08:00
- **Notes**: 已确认测试文件目标修改存在，工具文件修改也已单独复核。

---

## [ERR-20260810-001] Android 本地构建缺少 SDK

**Logged**: 2026-08-10T20:43:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Android Gradle 验证在配置阶段因本机未配置 Android SDK 而阻塞。

### Error
`SDK location not found. Define ANDROID_HOME or android/local.properties sdk.dir.`

### Context
- 命令：`android\\gradlew.bat lint test assembleDebug`
- JDK 已可启动 Gradle，但无法解析 Android SDK。

### Suggested Fix
在本机安装 SDK 35 并配置 `ANDROID_HOME`，或依赖已配置 SDK/JDK 17 的严格 CI 重跑。

### Metadata
- Reproducible: yes
- Related Files: android/build.gradle.kts, .github/workflows/android-apk.yml

---

Command failures and integration errors.

---

## [ERR-20260810-009] nonexistent-target-test

**Logged**: 2026-08-10T19:42:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
终端回归命令引用了仓库中不存在的 `tests/test_ws_hub.py`。

### Error
```text
ERROR: file or directory not found: tests/test_ws_hub.py
```

### Context
- 尝试把 G4 定向测试与假定存在的 WebSocket 汇总测试一起执行。
- 仓库没有该文件，终端行为测试集中在 `tests/test_g4_terminal_sessions.py`。

### Suggested Fix
运行前先按文件模式定位现有测试，不推测测试文件名。

### Metadata
- Reproducible: yes
- Related Files: tests/test_g4_terminal_sessions.py

### Resolution
- **Resolved**: 2026-08-10T19:42:00+08:00
- **Notes**: 已确认不存在同名测试，改用 G4 定向测试和前端完整测试验证。

---

## [ERR-20260810-006] android-jdk17-verification

**Logged**: 2026-08-10T19:30:00+08:00
**Priority**: medium
**Status**: pending
**Area**: tests

### Summary
Android 关键项复核无法在当前本机重跑 Gradle JVM 测试，项目固定 JDK 17，但环境只有 JDK 21/26。

### Error
```text
Cannot find a Java installation matching languageVersion=17
```

### Context
- JDK 21 可启动 Gradle，但项目 `jvmToolchain(17)` 找不到匹配编译器。
- JDK 26 与当前 Gradle/Kotlin 组合不兼容。
- 尝试下载临时 JDK 17 时网络吞吐不可用，未修改项目工具链要求。

### Suggested Fix
在固定 JDK 17 的 CI 或已安装 JDK 17 的机器运行 `android\gradlew.bat lint test assembleDebug assembleStaging assembleRelease connectedCheck`。

### Metadata
- Reproducible: yes
- Related Files: android/build.gradle.kts, android/app/build.gradle.kts

---

## [ERR-20260810-008] stale-patch-context

**Logged**: 2026-08-10T19:03:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
Provider 路由在读取后继续变化，组合补丁中的旧上下文无法匹配。

### Error
```text
Failed to find expected lines in web/routers/models.py
```

### Context
- 补丁假设创建记录固定写入 enabled=True，但当前文件已支持请求 enabled 和 manual_models。

### Suggested Fix
修改高频变化文件前重新读取精确区域，并拆分跨文件补丁。

### Metadata
- Reproducible: no
- Related Files: web/routers/models.py

### Resolution
- **Resolved**: 2026-08-10T19:03:00+08:00
- **Notes**: 已重新读取并按当前实现生成补丁。

---

## [ERR-20260810-007] async-test-shared-task-leak

**Logged**: 2026-08-10T18:28:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
新增 setup 测试未等待模块共享后台任务，后续测试跨事件循环等待时失败。

### Error
```text
RuntimeError: got Future attached to a different loop
```

### Context
- `save_keys()` 将任务加入模块级 `_reinit_tasks`。
- 每个调用 `save_keys()` 的测试都必须等待自己触发的后台任务完成。

### Suggested Fix
测试返回前遍历并等待 `_reinit_tasks` 中未完成任务。

### Metadata
- Reproducible: yes
- Related Files: tests/test_credential_save_no_double_bot.py, web/routers/setup.py

### Resolution
- **Resolved**: 2026-08-10T18:28:00+08:00
- **Notes**: 新增用例已等待后台任务，避免污染后续事件循环。

---

## [ERR-20260810-006] pytest-node-id-class-mismatch

**Logged**: 2026-08-10T18:22:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
专项测试命令猜错测试类名，pytest 未收集目标用例。

### Error
```text
ERROR: not found: tests/test_credential_save_no_double_bot.py::TestSaveKeysTaskCreation::...
```

### Context
- 实际类名是 `TestSaveKeysSingleTask`。
- 修改既有测试文件后应先精确搜索类名，再拼接 node id。

### Suggested Fix
使用搜索结果中的真实类名执行定向测试。

### Metadata
- Reproducible: yes
- Related Files: tests/test_credential_save_no_double_bot.py

### Resolution
- **Resolved**: 2026-08-10T18:22:00+08:00
- **Notes**: 已改用真实类名重跑。

---

## [ERR-20260810-005] optional-botpy-test-dependency

**Logged**: 2026-08-10T17:46:00+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
setup 相关回归文件在收集夹具时依赖未安装的可选 botpy，无法在当前环境执行。

### Error
```text
ModuleNotFoundError: No module named 'botpy'
```

### Context
- G2-04 专项本身 39 项全部通过。
- 额外执行 `test_credential_save_no_double_bot.py` 时，自动夹具导入 QQ adapter 失败。

### Suggested Fix
在包含 QQ 可选依赖的项目环境运行该回归，或让测试夹具对缺失 botpy 使用项目已有 stub。

### Metadata
- Reproducible: yes
- Related Files: tests/test_credential_save_no_double_bot.py, qq_bot_adapter.py

---

## [ERR-20260810-004] tdd-setup-bypass-red-test

**Logged**: 2026-08-10T17:41:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
G2-04 setup 旁路测试按目标异步接口调用现有同步函数，失败时写入了用户配置目录。

### Error
```text
TypeError: object NoneType can't be used in 'await' expression
```

### Context
- 失败准确暴露 `_auto_register_providers` 尚未委托异步应用服务。
- 旧同步实现先执行了配置、凭证和 runtime 写入，测试隔离不足导致真实用户配置产生副作用。

### Suggested Fix
将 setup 自动注册改为异步应用服务入口；此类 RED 测试必须先隔离配置目录或完全替换旧副作用依赖。

### Metadata
- Reproducible: yes
- Related Files: web/routers/setup.py, tests/test_g2_04_provider_application_service.py

### Resolution
- **Resolved**: 2026-08-10T17:41:00+08:00
- **Notes**: 测试已确认目标缺口，后续实现删除三态直写并通过共享服务完成注册。

---

## [ERR-20260810-002] partial-multi-file-patch

**Logged**: 2026-08-10T16:10:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Android 审查修复的多文件补丁因测试名上下文猜测而部分应用。

### Error
```text
Failed to find expected lines in BridgeRequestValidatorTest.kt
```

### Context
- 未先读取该测试文件便使用了推测的函数名作为补丁上下文。

### Suggested Fix
批量补丁前读取所有目标文件，失败后确认已应用部分并只重试失败文件。

### Metadata
- Reproducible: yes
- Related Files: android/core/bridge-api/src/test/kotlin/com/xiaoda/agent/bridge/BridgeRequestValidatorTest.kt

### Resolution
- **Resolved**: 2026-08-10T16:12:00+08:00
- **Notes**: 读取实际内容后使用精确上下文补入失败测试。

---

## [ERR-20260810-001] android-bootstrap-environment

**Logged**: 2026-08-10T01:30:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
Android G5-01 本地验证环境缺少 Android SDK、Gradle，且 Gradle 官方分发地址当前不可达。

### Error
```text
gradle: command not found
Android SDK candidate paths do not exist
Invoke-WebRequest: 无法连接到远程服务器
```

### Context
- 目标工作树为 `refactor/mobile-v2`。
- 已安装 JDK 21 和 Python 3.12，但没有 Android SDK 或 Gradle Wrapper JAR。
- 尝试从 Gradle 官方分发地址下载 8.11.1 失败。

### Suggested Fix
优先使用可达镜像引导固定 Gradle Wrapper，并通过命令行工具安装 SDK 35；最终仍以 Wrapper 和 CI 固定版本验证。

### Metadata
- Reproducible: yes
- Related Files: android/gradle/wrapper/gradle-wrapper.properties

### Resolution
- **Resolved**: 2026-08-10T06:00:00+08:00
- **Notes**: 修复嵌套错误的 Wrapper JAR，安装临时 JDK 17 与 Android SDK 35，并用 ASCII junction 完成 lint、测试和三变体 APK 构建验证。

---

## [ERR-20260809-002] partial-multi-file-patch

**Logged**: 2026-08-09T23:22:00+08:00
**Priority**: low
**Status**: resolved
**Area**: config

### Summary
多文件补丁因 `.env.example` 上下文不精确而部分应用。

### Error
```text
Failed to find expected lines in .env.example
```

### Context
- G1-07 同时清理 Provider metadata、环境示例和架构文档。
- metadata 与架构修改成功，环境示例未修改。

### Suggested Fix
补丁失败后立即重新读取目标文件，只对失败文件应用精确补丁，并确认其他文件的部分修改状态。

### Metadata
- Reproducible: yes
- Related Files: .env.example, config/provider_metadata.json, docs/ARCHITECTURE.md

### Resolution
- **Resolved**: 2026-08-09T23:22:00+08:00
- **Notes**: 重新读取 `.env.example` 后按实际内容精确删除 Ollama 配置段。

---

## [ERR-20260809-001] ruff-import-order

**Logged**: 2026-08-09T23:10:00+08:00
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Ruff 要求 `pathlib` 标准库导入排在 `re` 之前。

### Error
```text
I001 Import block is un-sorted or un-formatted
```

### Context
- G1-06 测试静态检查。
- 涉及 `tests/test_local_embedding_retirement.py`。

### Suggested Fix
使用项目 Ruff 配置自动整理导入并重新运行完整静态检查。

### Metadata
- Reproducible: yes
- Related Files: tests/test_local_embedding_retirement.py

### Resolution
- **Resolved**: 2026-08-09T23:10:00+08:00
- **Notes**: Ruff 自动整理后通过目标文件检查。

---

## [ERR-20260810-003] subagent-wrong-worktree

**Logged**: 2026-08-10T14:55:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
子任务声称修改指定 worktree，实际将第二轮 G3 修复写入主工作区。

### Error
```text
worktree 未出现 focusTrap 文件，主工作区出现对应文件和 ChatView 变更。
```

### Context
- 子任务提示包含“指定 worktree”，但未给出绝对路径。
- 返回的文件链接省略了 `.worktrees/mobile-v2-refactor`。
- 主代理在复核时通过双路径 Grep/Glob 发现错位。

### Suggested Fix
所有子任务提示必须写出完整 worktree 绝对路径；返回后立即同时检查目标 worktree 与主工作区的关键文件状态，再接受结果。

### Metadata
- Reproducible: yes
- Related Files: web/frontend/src/views/ChatView.vue, web/frontend/src/utils/focusTrap.ts

### Resolution
- **Resolved**: 2026-08-10T14:58:00+08:00
- **Notes**: 已清理主工作区误写并将修复精确应用到指定 worktree。

---

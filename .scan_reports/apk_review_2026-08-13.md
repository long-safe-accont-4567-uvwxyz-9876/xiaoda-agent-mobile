# APK 安全/卫生审查报告

- 审查对象：`xiaoda-agent-release`（CI run#44，commit `95f1cb4`）
- 审查日期：2026-08-13
- 结论：**已修复 P1（配置冲突）、P2（打包卫生）、P3（cookie 一致性）**；两项 P3 项经核实为误报/已满足，无需改动；历史 text_utils bug 已在源码中确认修复。

---

## P1 配置冲突 / 逻辑不一致（已修复）

### 1.1 `allowed_paths` / `forbidden_paths` 自相矛盾
- 位置：`config/agents/xiaoli.json`
- 冲突：`allowed_paths` 含 `config/agents/xiaoli_personality.md`，但 `forbidden_paths` 含 `config/agents/*_personality.md`。路径校验逻辑（`tool_engine/tool_call_handler.py#_check_path_whitelist`）**黑名单优先于白名单**，通配符规则会先命中，导致白名单中的自身人格文件永远被拒。
- 修复：将 `forbidden_paths` 中的通配符 `config/agents/*_personality.md` 改为显式列出**其他 4 个** agent 的人格文件（`xiaoda/xiaoke/xiaolang/xiaolian_personality.md`），既放行自身人格文件，又保留"不得读取他人人格文件"的安全约束。

### 1.2 跨 Agent 调用约束不对称
- 位置：`config/agents/xiaoke.json`、`xiaolang.json`、`xiaolian.json`
- 问题：三者均排除 `call_xiaoda`/`call_xiaoli`，但互相之间未排除，"禁止互调"规则不完整。
- 修复：
  - `xiaoke`：补充 `call_xiaolang`、`call_xiaolian`
  - `xiaolang`：补充 `call_xiaoke`、`call_xiaolian`
  - `xiaolian`：补充 `call_xiaoke`、`call_xiaolang`

---

## P2 发布打包卫生（已修复）

- 位置：`android/app/build.gradle.kts` `stagePythonRuntime.exclude`
- 问题：release 包内打包了大量开发/CI 残留（`.github/workflows/`、`Dockerfile`、`README.md`、`SETUP.md`、`USAGE.md`、`CLAUDE.md`、`_git_push.sh`、`_run.bat/ps1`、`_test_out*.txt`、`_pip_out.txt`、`audit_*.md`、`BUGFIX_PLAN_*.md`、`RAG-OPTIMIZATION-SPEC.md`、`.env.example` 等），既增体积又暴露项目结构与构建流程。
- 修复：追加根级排除模式（Ant glob 仅匹配仓库根，不影响 `config/` 子目录运行时数据）：
  - `.github/**`、`Dockerfile`、`docker-compose*.yml`
  - `*.md`、`*.sh`、`*.bat`、`*.ps1`
  - `_test_out*.txt`、`_pip_out.txt`、`.env.example`

---

## P3 安全 / 健壮性

### 3.1 DUMP 权限 —— 误报，无需改动
- 源 `AndroidManifest.xml` **未声明** `<uses-permission android:name="android.permission.DUMP"/>`。
- `merged_manifest` 中的 `DUMP` 出现在 `ProfileInstallReceiver` 的 `android:permission` 属性上，这是 **androidx.profileinstaller 库**为 receiver 添加的**调用方保护属性**（限制仅有系统调试权限的调用者才能触发），并非应用申请权限，不扩大攻击面。
- 移除会破坏 profile 安装优化且无安全收益，故不改。

### 3.2 allowBackup —— 已满足，无需改动
- 源 `AndroidManifest.xml` 已显式 `android:allowBackup="false"`，`adb backup` 无法提取应用数据。

### 3.3 Cookie 配置一致性 —— 已修复
- 位置：`config/mobile_contract.json` + `MainActivity.kt#sessionCookie`
- 问题：`mobile_contract.json` 声明 `same_site="none"`，但 `MainActivity.kt` **硬编码 `SameSite=Lax`**，忽略了 build.gradle 读 contract 生成的 `BuildConfig.SESSION_COOKIE_SAME_SITE` 字段，配置与实现不一致。
- 隐患：`SameSite=None` 在 HTTP（`usesCleartextTraffic` 明文）下必须配 `Secure` 才生效，而 cookie 是发给本地 `http://127.0.0.1` 后端，加 `Secure` 反而无效。
- 修复：
  - `mobile_contract.json`：`same_site` 改为 `lax`（HTTP 下有效、无需 `Secure`）。
  - `MainActivity.kt`：`sessionCookie` 改用 `BuildConfig.SESSION_COOKIE_SAME_SITE`，让配置真正生效。

---

## 补充项核实

### text_utils 英文推理判空 bug —— 已修复（源码确认）
- 历史问题：`utils/text_utils.py` 中 `_FULL_REASONING_PATTERNS` 用 `re.DOTALL` 按"中文占比 <3%"整段判空，导致英文推理后接的正常回复被整段误删 → `empty_reply`。
- 当前源码（CI 打包的直接来源）：
  - 改为按行清洗（`_CHINESE_REASONING_LINE_PATTERN`），只删推理行、保留正常回复行；
  - 英文判空条件收紧为三重：以大写字母开头 + 长度 > 200 + 中文占比 < 1%（较历史 < 3% 更保守）。
- 结论：**已修复**，无需反编译 `.pyc` 复核（源码即打包来源）。

### 密钥/凭据泄露 —— 未发现
- `.env.example` 的 key 均为空占位；`_git_push.sh` 等脚本无硬编码凭据。

---

## 修复文件清单
| 文件 | 改动 |
|------|------|
| `config/agents/xiaoli.json` | forbidden 通配符改为显式列他人人格文件 |
| `config/agents/xiaoke.json` | excluded_tools 补 `call_xiaolang/xiaolian` |
| `config/agents/xiaolang.json` | excluded_tools 补 `call_xiaoke/xiaolian` |
| `config/agents/xiaolian.json` | excluded_tools 补 `call_xiaoke/xiaolang` |
| `config/mobile_contract.json` | `same_site: none → lax` |
| `android/app/src/main/kotlin/com/xiaoda/agent/MainActivity.kt` | cookie 改用 `BuildConfig.SESSION_COOKIE_SAME_SITE` |
| `android/app/build.gradle.kts` | exclude 追加根级开发/CI 残留模式 |

## 待办
- [ ] 提交并推送以上改动
- [ ] 验证 CI 全绿（配置/构建层面改动，需 on-device 测试确认无回归）
# G2-04 Provider Application Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Provider 创建、更新、独立 Key 更新、启用/禁用和删除在配置、凭证、运行时客户端与凭证池之间具备补偿事务。

**Architecture:** 新增 repository、credential store、runtime registry 与 application service 四个边界。应用服务按 Provider ID 串行协调候选状态、提交和逆序补偿，Router 只保留 HTTP 校验、引用检查和提交后副作用。

**Tech Stack:** Python 3.12、FastAPI、asyncio、Path、现有 ConfigService、credential_vault、ModelRouter、CredentialPool、pytest、pytest-asyncio

---

### Task 1: 写入失败测试骨架

**Files:**
- Create: `tests/test_g2_04_provider_application_service.py`

- [ ] 为内存 repository、临时凭证目录、假客户端、假 runtime registry 和假凭证池建立 fixture。
- [ ] 编写创建成功及配置保存失败测试，断言四态全有或全无。
- [ ] 运行 `py -3.12 -m pytest tests/test_g2_04_provider_application_service.py -q --tb=short`，确认因应用服务模块缺失而失败。

### Task 2: 建立存储与运行时边界

**Files:**
- Create: `web/provider_application.py`
- Modify: `web/config_service.py`
- Modify: `web/_provider_keys.py`
- Modify: `utils/credential_pool.py`

- [ ] 实现 `ProviderRepository.get/set/delete/restore`，补齐 `ConfigService.delete()` 保存失败的内存回滚。
- [ ] 实现凭证文件 snapshot、原子 write/delete/restore，复用 `_encode_key()` 和现有文件命名。
- [ ] 为 `CredentialPool` 增加线程安全的 provider snapshot、replace 和 remove 操作。
- [ ] 实现 runtime registry 的候选客户端构建、客户端交换、凭证池同步和异步关闭。
- [ ] 运行 Task 1 测试，确认边界测试通过。

### Task 3: 实现创建事务

**Files:**
- Modify: `web/provider_application.py`
- Modify: `tests/test_g2_04_provider_application_service.py`

- [ ] 先增加客户端构建、配置保存、凭证发布和 runtime 发布各阶段失败测试。
- [ ] 实现按 Provider ID 的异步锁和 `create()` 补偿事务。
- [ ] 保证失败关闭候选客户端，成功状态包含配置、Key、客户端与凭证池。
- [ ] 运行 G2-04 专项确认创建矩阵通过。

### Task 4: 实现更新、Key 与启停事务

**Files:**
- Modify: `web/provider_application.py`
- Modify: `tests/test_g2_04_provider_application_service.py`

- [ ] 增加更新配置与独立 Key 更新的逐阶段故障注入测试。
- [ ] 增加禁用立即移除客户端/凭证池、重新启用恢复客户端测试。
- [ ] 实现 `update()` 与 `set_key()`，提交成功后关闭旧客户端，失败恢复旧四态。
- [ ] 增加同 Provider 并发 mutation 串行测试。
- [ ] 运行 G2-04 专项确认更新矩阵通过。

### Task 5: 实现删除事务

**Files:**
- Modify: `web/provider_application.py`
- Modify: `tests/test_g2_04_provider_application_service.py`

- [ ] 增加配置删除、凭证删除和 runtime 移除失败测试。
- [ ] 实现 `delete()`，失败恢复完整旧状态，成功关闭旧客户端。
- [ ] 保持引用检查在 Router，避免提前实现 G2-05。
- [ ] 运行 G2-04 专项确认删除矩阵通过。

### Task 6: Router 接入与兼容回归

**Files:**
- Modify: `web/routers/models.py`
- Test: `tests/test_g2_04_provider_application_service.py`

- [ ] 增加 Router 创建、更新、Key 更新、禁用和删除通过应用服务的测试。
- [ ] 删除 Router 内直接写 Key、配置和 runtime 的路径。
- [ ] 保持现有 API 路径、Envelope 数据、审计、缓存失效和广播语义。
- [ ] 验证输入校验及现有路由引用删除保护不变。

### Task 7: 专项、全量与文档门禁

**Files:**
- Modify: `docs/mobile/implementation-plan-v2.md`
- Modify: `docs/mobile/acceptance-matrix-v2.md`
- Modify: `docs/mobile/test-evidence.md`
- Modify: `docs/mobile/handoff-runbook.md`

- [ ] 运行 G2-04 专项和 G2-01 至 G2-03 相关回归。
- [ ] 运行 `py -3.12 -m pytest -q`。
- [ ] 运行 Ruff、compileall、版本同步、前端生产构建和 `git diff --check`。
- [ ] 独立复审 Critical 与 Important 问题并修复。
- [ ] 记录精确证据后关闭 G2-04，下一任务保持 G2-05。

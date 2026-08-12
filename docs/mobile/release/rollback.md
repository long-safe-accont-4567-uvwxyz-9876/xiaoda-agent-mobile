# 移动端回滚包与回滚说明

版本基线：`0.5.70`。本文档定义客户端回滚与数据回滚的步骤、产物与验证。

## 1. 回滚类型

| 类型 | 适用 | 对应验收 |
|---|---|---|
| 客户端回滚 | APK 安装异常 / 新版本崩溃 | REL-005（上一稳定包可重新安装） |
| 数据回滚 | 配置迁移 / 向量维度迁移失败 | REL-004（配置和向量迁移可恢复） |

## 2. 回滚包（Release Artifact）

每次发布必须归档以下产物到 `android/app/build/release-artifacts/`：

| 产物 | 说明 |
|---|---|
| `app-<variant>.apk` | 上一稳定 APK（installable rollback unit） |
| `<app>.aab` | 商店分发的签名字符串（若启用） |
| `SHA256SUMS` | 三变体 APK 校验和（CI 生成） |
| `sbom.spdx.json` | 依赖与许可证清单 |
| `NOTICE` | 许可证归档 |
| `mapping-<variant>.txt` | release R8 混淆映射（崩溃符号还原） |
| `asset-manifest.json` | 前端资源哈希（含在 APK assets） |

上一稳定包保留在发布渠道（GitHub Release / 应用商店旧版本），用户可重新安装降级。

## 3. 客户端回滚步骤

1. 确认需回滚：启动崩溃、核心功能不可用、安全回归。
2. 从发布渠道获取上一稳定 APK（保留 `SHA256SUMS` 校验）。
3. 卸载当前版本（`adb uninstall com.xiaoda.agent` 或用户手动卸载）。
   - 注意：卸载会清除应用私有数据；如需保留数据，先做 §4 备份。
4. 安装上一稳定 APK（`adb install -r` 或引导用户安装）。
5. 验证：冷启动、登录/会话、核心路由可访问。

> 同签名策略：回滚包必须与当前包使用同一签名，否则 Android 拒绝降级安装。
> G6-04 已启用项目测试 keystore（`android/keystore/xiaoda-release.jks`，gitignore 排除）对 release/staging 签名（`CN=Xiaoda Agent`，V2 签名经 `apksigner verify --print-certs` 验证）。同个 keystore 签名的历史包可跨版本降级安装；后续正式发布需替换为真实签名并保留原 keystore 以维持可回滚。

## 4. 数据回滚

### 4.1 配置迁移回滚

- 配置写入前备份原配置（`ConfigService` 保存失败恢复内存旧值）。
- 回滚：恢复备份文件 → 重启服务。
- 验证：`tests/test_config_migrations.py` 通过。

### 4.2 向量维度迁移回滚

- 迁移前备份原向量索引。
- 迁移失败：恢复备份 → 保持原维度 → 不删除本地模型。
- 验证：`tests/test_vector_dimension_migration.py` 通过；迁移工具见 `scripts/migrate_vector_dimensions.py`。

### 4.3 迁移断点限流

- 云 Embedding 重编码支持断点续传与限流；失败不静默吞掉，记录告警。

## 5. 回滚验证

本地已验证：

```powershell
py -3.12 -m pytest tests/test_config_migrations.py tests/test_vector_dimension_migration.py -q
# => PASS
```

设备级回滚（真机安装/卸载降级）需 G6-03 设备门禁确认。

## 6. 发布负责人签署

- 构建、签名、回滚和制品通过（REL 验收 §14 `.`）。
- 回滚演练结果记录到 `test-evidence.md`。
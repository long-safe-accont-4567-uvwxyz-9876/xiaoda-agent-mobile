# 边缘硬件能力完整退役 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从生产代码、默认配置、部署配置和当前文档中完整退役边缘硬件能力，同时保留普通 PC GPU 与 Windows、Linux、Docker、Web 支持。

**Architecture:** 保留现有能力探测器作为普通电脑系统画像入口，只缩减其职责；路由层取消硬件专属分类，硬件知识问题回归通用技术问答；默认配置、部署和当前文档同步移除已经不存在的能力声明。历史计划与审计文件保持不变。

**Tech Stack:** Python 3.11、pytest、Ruff、JSON、Docker Compose、Markdown

---

## 文件结构

- `core/capability_detector.py`：仅保留平台、CPU、内存、PC GPU 和通用工具探测。
- `config.py`：删除板卡、总线、传感器、摄像头专属路由词。
- `agent_dispatcher.py`：删除 `hardware` 分类规则和公开任务类型说明。
- `config/agent_routing.json`、`config/agent_routing_v2.json`：删除硬件任务映射与组合。
- `config/agents/xiaoke.json`、`config/agents/xiaolian.json`：删除不存在的硬件工具排除项。
- `tests/test_capability_detector.py`：新增普通 PC 能力画像边界测试。
- `tests/test_agent_routing.py`：更新路由期望并加入硬件词不再专门分类的回归测试。
- `requirements.txt`、`docker-compose.yml`：删除失效依赖和设备直通说明。
- `README.md`、`SETUP.md`、`USAGE.md`、`docs/ARCHITECTURE.md`、`docs/juejin-article.md`：清理当前产品能力与部署描述。

### Task 1: 锁定能力画像边界

**Files:**
- Create: `tests/test_capability_detector.py`
- Modify: `core/capability_detector.py`

- [ ] **Step 1: 编写失败测试**

```python
from core.capability_detector import CapabilityProfile


def test_prompt_segment_keeps_pc_system_and_gpu_only():
    profile = CapabilityProfile(
        platform_os="Windows",
        platform_arch="AMD64",
        hostname="desktop",
        processor="Intel Core",
        has_gpu=True,
        gpu_name="NVIDIA GeForce RTX",
        gpu_memory_mb=8192,
        has_cuda=True,
        cuda_version="555.0",
    )
    segment = profile.to_prompt_segment("D:/xiaoda-data")
    assert "Windows" in segment
    assert "NVIDIA GeForce RTX" in segment
    assert "D:/xiaoda-data" in segment
    for retired in ("GPIO", "I2C", "SPI", "UART", "PWM", "摄像头", "NPU", "SBC"):
        assert retired not in segment


def test_capability_profile_has_no_edge_hardware_fields():
    fields = CapabilityProfile.__dataclass_fields__
    for retired in ("has_gpio", "has_i2c", "has_camera", "is_sbc", "npu_enabled"):
        assert retired not in fields
```

- [ ] **Step 2: 验证测试先失败**

Run: `python -m pytest tests/test_capability_detector.py -q`

Expected: `has_gpio` 等字段仍存在，测试失败。

- [ ] **Step 3: 最小化能力探测器**

删除 `CapabilityProfile` 的 `has_gpio`、`has_i2c`、`has_camera`、`is_sbc`、`npu_enabled` 字段，删除 NPU 环境变量、SBC 设备节点探测、摄像头工具和视觉模型 Prompt 段；保留 `_detect_gpu()`、CPU、内存、系统、数据目录和 `_detect_available_tools()`。日志格式改为：

```python
logger.info(
    f"capability.detected os={profile.platform_os} arch={profile.platform_arch} "
    f"gpu={profile.has_gpu} cores={profile.cpu_cores} ram={profile.total_ram_gb:.1f}GB"
)
```

- [ ] **Step 4: 删除仅服务于 SBC 的私有函数**

移除 `_detect_sbc()` 以及不再被任何生产路径使用的设备节点辅助逻辑；若 `_path_exists()` 仍有普通 PC 用途则保留，否则一并删除。

- [ ] **Step 5: 验证能力测试通过**

Run: `python -m pytest tests/test_capability_detector.py tests/test_gpu_selection.py -q`

Expected: 全部通过，PC GPU 相关测试保持绿色。

### Task 2: 退役硬件专属路由

**Files:**
- Modify: `tests/test_agent_routing.py`
- Modify: `config.py`
- Modify: `agent_dispatcher.py`
- Modify: `config/agent_routing.json`
- Modify: `config/agent_routing_v2.json`

- [ ] **Step 1: 改写路由测试形成失败基线**

删除 `test_route_hardware_to_xiaolang`，把关键词用例中的 `("GPIO 传感器读取", "hardware")` 替换为独立测试：

```python
def test_retired_edge_hardware_terms_have_no_dedicated_classification():
    dispatcher = _make_dispatcher(_ALL_AVAILABLE)
    for user_input in ["GPIO 引脚", "I2C 传感器", "SPI 通信", "UART 串口", "PWM 舵机", "Orange Pi 摄像头"]:
        assert dispatcher.classify_task(user_input) != "hardware"
        assert "hardware" not in dispatcher.classify_multi(user_input)
```

从配置加载测试中删除 `assert config["hardware"] == "xiaolang"`。

- [ ] **Step 2: 验证路由测试先失败**

Run: `python -m pytest tests/test_agent_routing.py -q`

Expected: 旧分类仍返回 `hardware`，测试失败。

- [ ] **Step 3: 删除生产路由残留**

从 `AGENT_ROUTE_KEYWORDS["xiaolang"]` 删除 Orange Pi、GPIO、I2C、SPI、传感器、LED、舵机、硬件、引脚、串口、UART、PWM、ADC、DAC、摄像头、拍照、观察、识别和检测；保留服务器、Docker、网络和普通系统管理词。

从 `classify_task()`、`classify_multi()` 删除硬件规则，并把 docstring 的任务类型列表移除 `hardware`。

- [ ] **Step 4: 删除 JSON 路由映射**

从 v1 路由 JSON 删除 `hardware` 键；从 v2 JSON 删除以 `hardware` 为单域或组合域的配置。保持 JSON 合法并沿用现有缩进。

- [ ] **Step 5: 验证路由测试通过**

Run: `python -m pytest tests/test_agent_routing.py tests/test_agent_routing.py -q`

Expected: 全部通过，硬件词不再触发专属分类。

### Task 3: 清理默认工具配置和部署残留

**Files:**
- Modify: `config/agents/xiaoke.json`
- Modify: `config/agents/xiaolian.json`
- Modify: `requirements.txt`
- Modify: `docker-compose.yml`
- Test: `tests/test_retired_edge_hardware_config.py`

- [ ] **Step 1: 编写配置扫描测试**

```python
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETIRED_TOOLS = {"gpio_control", "hardware_status", "i2c_comm", "pwm_control"}


def test_default_agent_configs_have_no_retired_hardware_tools():
    for path in (ROOT / "config" / "agents").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert RETIRED_TOOLS.isdisjoint(payload.get("excluded_tools", []))


def test_runtime_dependency_and_compose_have_no_edge_device_setup():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").lower()
    assert "smbus2" not in requirements
    for retired in ("/dev/i2c", "/dev/gpio", "/sys/class/pwm"):
        assert retired not in compose
```

- [ ] **Step 2: 验证配置测试先失败**

Run: `python -m pytest tests/test_retired_edge_hardware_config.py -q`

Expected: 默认 Agent 配置、requirements 或 Compose 至少一项命中并失败。

- [ ] **Step 3: 删除失效配置**

从所有默认 Agent JSON 的 `excluded_tools` 删除四个失效工具名；删除 `requirements.txt` 的 `smbus2` 注释块；删除 Docker Compose 的 I2C、GPIO 和 PWM 设备直通注释。

- [ ] **Step 4: 验证配置测试通过**

Run: `python -m pytest tests/test_retired_edge_hardware_config.py -q`

Expected: 2 项测试全部通过。

### Task 4: 清理当前用户文档

**Files:**
- Modify: `README.md`
- Modify: `SETUP.md`
- Modify: `USAGE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/juejin-article.md`

- [ ] **Step 1: 建立文档清理清单**

对上述五个当前文档运行：

```powershell
Select-String -Path README.md,SETUP.md,USAGE.md,docs/ARCHITECTURE.md,docs/juejin-article.md -Pattern 'Orange Pi|orangepi|RK3588|GPIO|I2C|SPI|UART|PWM|ADC|DAC|NPU|摄像头|传感器|边缘部署|hardware_tools'
```

Expected: 输出所有需要逐项判断的当前能力声明。

- [ ] **Step 2: 更新产品定位和功能表**

将“边缘部署”改为“本地与服务器部署”；工具表删除硬件控制与摄像头视觉行；保留普通系统管理、图片理解和用户上传图片等非设备摄像头能力。

- [ ] **Step 3: 更新目录树与架构**

删除不存在的 `tools/hardware_tools.py` 条目以及板卡执行链；架构保留通用 Capability Detector，并说明其只负责普通系统和 PC GPU 能力。

- [ ] **Step 4: 更新安装与使用说明**

删除 ARM 板卡、Orange Pi、设备组权限、GPIO/I2C/PWM、摄像头和 NPU 安装章节；保留 Linux 普通服务器、Docker、Windows 和 Web 使用方式。

- [ ] **Step 5: 复查当前文档**

重新执行 Step 1 的命令。

Expected: 不再有把退役项表述为当前支持能力的命中；技术历史或“不支持”说明若保留，必须语义明确。

### Task 5: 全仓边界扫描与回归

**Files:**
- Modify: implementation 中发现的当前生产配置或文档残留
- Preserve: `docs/superpowers/plans/**`、`docs/superpowers/specs/**` 中早于本次变更的历史记录、`audit/**`、`.scan_reports/**`

- [ ] **Step 1: 扫描生产代码和当前配置**

Run:

```powershell
$paths = @('*.py','core','agent_core','tools','tool_engine','config','web','docker-compose.yml','requirements.txt')
Select-String -Path $paths -Pattern 'has_gpio|has_i2c|has_camera|is_sbc|npu_enabled|gpio_control|i2c_comm|pwm_control|hardware_status|/dev/i2c|/dev/gpio|/sys/class/pwm' -Recurse
```

Expected: 无生产残留；历史测试数据命中需逐项判断。

- [ ] **Step 2: 运行专项测试**

Run:

```powershell
python -m pytest tests/test_capability_detector.py tests/test_gpu_selection.py tests/test_agent_routing.py tests/test_retired_edge_hardware_config.py -q
```

Expected: 全部通过。

- [ ] **Step 3: 运行静态检查与版本检查**

Run:

```powershell
python -m ruff check core/capability_detector.py agent_dispatcher.py config.py tests/test_capability_detector.py tests/test_agent_routing.py tests/test_retired_edge_hardware_config.py
python scripts/check_version_sync.py --check
```

Expected: Ruff 无错误，版本同步检查通过。

- [ ] **Step 4: 运行全量测试**

Run: `python -m pytest -q`

Expected: 全量测试通过；若存在与本次无关的基线失败，记录完整用例名并通过变更前对照证明非回归。

- [ ] **Step 5: 检查最终差异**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: 仅包含规格范围内文件，无空白错误，不包含密钥、运行产物或无关修改。

## 实施约束

- 不提交 Git commit，除非用户另行明确要求。
- 不修改或删除历史审计、历史计划和旧设计记录。
- 不把普通 PC GPU、用户上传图片分析或通用 Linux/Docker 能力误删为边缘硬件。
- 不新增兼容层、模拟硬件工具或未来恢复开关。

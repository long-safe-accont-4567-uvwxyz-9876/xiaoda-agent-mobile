# 边缘硬件能力完整退役设计

> 主题：从 Xiaoda Agent 中完整退役边缘硬件能力
> 日期：2026-08-09
> 状态：方案已确认，待实施

## 1. 背景

项目当前面向 Windows、Linux、Docker 和 Web 提供多智能体、长期记忆、RAG、工具调用、MCP、插件、多模态输出及多渠道交互。历史上项目曾面向 Orange Pi 等边缘设备提供 GPIO、I2C、PWM 和传感器能力，但当前仓库已不存在对应执行模块、总线协议实现及驱动依赖。

现存内容主要是能力探测、Prompt 宣称、任务路由、无效工具名、部署注释、测试断言和文档说明。这些残留会让模型和用户误以为系统仍能直接控制板卡硬件。

## 2. 目标

- 完整退役 Orange Pi、RK3588、SBC、NPU、摄像头、GPIO、I2C、SPI、UART、串口、PWM、ADC、DAC、传感器和单片机通信能力。
- 保留 Windows 桌面、Linux 普通电脑或服务器、Docker 和 Web 应用支持。
- 保留普通 PC 的 NVIDIA、Intel 和 AMD GPU 探测及本地模型加速。
- 保留多智能体、认知记忆、RAG、MCP、插件、QQ、微信、CLI、WebUI 和桌面窗口等核心功能。
- 消除运行时能力、工具清单、路由行为和当前文档之间的矛盾。

## 3. 非目标

- 不删除普通 PC 的 CPU、内存、操作系统、磁盘、GPU 或通用命令探测。
- 不删除 Docker、Linux 或本地模型能力。
- 不改造 AgentCore、记忆系统、RAG、模型路由或交互渠道。
- 不删除历史计划、历史审计报告和历史设计记录中的硬件内容。
- 不恢复或重写任何硬件控制实现。

## 4. 方案

采用完整退役方案。项目定位收敛为面向普通电脑、服务器、桌面和 Web 的多智能体 AI 应用，不再把边缘板卡作为受支持平台。

### 4.1 运行时能力

- 从 `CapabilityProfile` 移除 SBC、GPIO、I2C、NPU 和摄像头相关字段与描述。
- 删除 `/sys/class/gpio`、`/dev/gpiochip*`、`/dev/i2c-*`、RK3588、NPU 和摄像头探测。
- 保留平台、CPU、内存、PC GPU、数据目录和通用命令能力。
- Prompt 不再出现 Orange Pi、边缘设备、GPIO、I2C、SPI、UART、PWM、摄像头或 NPU 可用性声明。

### 4.2 路由和任务分类

- 从 Agent 路由关键词中移除 GPIO、I2C、SPI、UART、串口、PWM、ADC、DAC、传感器、单片机和板卡词。
- 删除 `hardware` 专属任务分类及其重复关键词表。
- 用户询问硬件知识时按普通技术问题处理，不再宣称本机可以执行硬件操作。
- 同步更新固定旧路由行为的测试。

### 4.3 工具和配置

- 清除 Agent 配置中不存在的 `gpio_control`、`hardware_status`、`i2c_comm` 和 `pwm_control` 工具名。
- 清除依赖文件中的 `smbus2` 等失效说明。
- 保证内置工具清单、权限矩阵和 WebUI 工具列表均不出现边缘硬件能力。

### 4.4 部署

- 删除 Docker Compose 中 GPIO、I2C 和 PWM 设备映射示例。
- 删除 Orange Pi、ARM 板卡、RK3588、NPU 和摄像头专属部署说明。
- 保留 Windows、Linux x86_64、Docker 和通用服务器部署配置。

### 4.5 当前文档

- 更新 README、SETUP、USAGE、架构文档、文档索引和当前对外介绍。
- 删除不存在的 `tools/hardware_tools.py` 目录树条目。
- 删除 GPIO、I2C、PWM、传感器、摄像头、RK3588 和 NPU 的当前能力宣传。
- 将“边缘部署”改为“本地与服务器部署”等符合现状的表述。
- 保留带日期的历史计划、审计证据和历史设计，避免改变项目演进记录。

## 5. 影响边界

主要修改范围：

- `core/capability_detector.py`
- `prompt_builder.py` 中硬件上下文调用点
- `config.py` 中代理路由关键词
- `agent_dispatcher.py` 中任务分类
- `config/agents/*.json` 中失效工具名
- `requirements.txt`
- `docker-compose*.yml` 和相关部署文件
- 与能力探测、Prompt、路由有关的测试
- README、SETUP、USAGE 和当前架构文档

不得因为硬件退役而整体删除能力探测器；该模块仍负责普通电脑的系统和 GPU 能力画像。

## 6. 兼容性与错误行为

- 外部调用若尝试使用旧硬件工具，将得到标准“工具不存在”结果，不增加兼容别名或静默模拟。
- 旧对话和数据库记录保持可读，不迁移或删除历史文本。
- 旧配置中多余硬件工具名应在读取时保持无害；仓库默认配置会清除这些名字。
- 普通 PC GPU 探测失败时继续优雅降级，不影响基础聊天。

## 7. 测试设计

- 验证能力画像仍包含平台、CPU、内存和 PC GPU，但不包含 SBC、GPIO、I2C、NPU 或摄像头。
- 验证系统 Prompt 不再宣称边缘硬件能力。
- 验证 GPIO、I2C、SPI、UART、PWM 和传感器词不再触发专属硬件路由。
- 验证工具注册表和默认 Agent 配置不包含硬件控制工具。
- 验证 Windows、Linux、Docker 和 Web 的启动配置仍有效。
- 运行相关单元测试、全量测试、Ruff 和版本同步检查。
- 对全仓生产代码和当前文档执行关键词扫描，历史文档命中单独列出，不作为失败。

## 8. 验收标准

- 生产代码不存在边缘硬件探测、硬件专属路由或硬件工具配置。
- 当前用户文档不再宣称可控制 GPIO、单片机、传感器、摄像头或 NPU。
- 普通 PC GPU 和本地模型加速继续保留。
- Windows 桌面、Linux 电脑或服务器、Docker 和 Web 应用仍受支持。
- 相关测试与全量回归通过。
- 不改写历史审计、历史计划和历史设计记录。

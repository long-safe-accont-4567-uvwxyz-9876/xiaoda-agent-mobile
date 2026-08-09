"""运行时能力探测 —— 替代硬编码硬件信息。

基于 AgentBoot 思路，适配 xiaoda-agent 的本地场景：
- platform.system() / platform.machine() 获取基础平台信息
- psutil 检测 CPU/内存
- nvidia-smi / rocm-smi 检测 GPU
- shutil.which() 检测可用命令行工具

设计原则：能力-上下文分离（ArXiv:2603.14332），Agent 的身份和能力在运行时动态确定。
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class CapabilityProfile:
    """Agent 运行时能力画像。"""
    schema_version: int = 1  # 画像版本，供下游判断字段可用性
    platform_os: str = ""
    platform_arch: str = ""
    hostname: str = ""
    os_release: str = ""
    processor: str = ""
    cpu_cores: int = 0
    total_ram_gb: float = 0.0
    has_gpu: bool = False
    gpu_name: str = ""
    gpu_memory_mb: int = 0
    has_cuda: bool = False
    cuda_version: str = ""
    available_tools: list[str] = field(default_factory=list)

    def to_prompt_segment(self, data_dir: str = "") -> str:
        """生成注入 system prompt 的能力描述段。"""
        lines = ["[本机硬件信息]"]
        lines.append(
            f"主机名: {self.hostname} | 架构: {self.platform_arch} | 处理器: {self.processor or '未知'}"
        )
        lines.append(
            f"系统: {self.platform_os} {self.os_release} ({self.platform_arch})"
        )

        tools = [
            "service_manage(服务管理)",
            "network_diag(网络诊断)",
            "dev_assist(开发辅助)",
        ]
        lines.append(f"可用工具: {' / '.join(tools)}")

        if data_dir:
            lines.append(f"数据存储: {data_dir}")

        # GPU 信息（如有）
        if self.has_gpu:
            gpu_line = f"GPU: {self.gpu_name}"
            if self.gpu_memory_mb:
                gpu_line += f" ({self.gpu_memory_mb}MB)"
            if self.has_cuda:
                gpu_line += f" | CUDA: {self.cuda_version}"
            lines.append(gpu_line)

        return "\n".join(lines)


# 模块级缓存：启动时探测一次，后续直接返回
_profile_cache: CapabilityProfile | None = None


def detect_capabilities() -> CapabilityProfile:
    """运行时探测 Agent 能力，结果缓存。"""
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache

    profile = CapabilityProfile()

    # 基础平台信息
    _uname = platform.uname()
    profile.platform_os = _uname.system
    profile.platform_arch = _uname.machine
    profile.os_release = _uname.release
    profile.processor = _uname.processor or ""
    try:
        profile.hostname = socket.gethostname()
    except Exception:
        profile.hostname = "unknown"

    # CPU 核心
    profile.cpu_cores = _detect_cpu_cores()

    # 内存
    profile.total_ram_gb = _detect_ram()

    # GPU 检测
    gpu_info = _detect_gpu()
    profile.has_gpu = gpu_info.get("has_gpu", False)
    profile.gpu_name = gpu_info.get("name", "")
    profile.gpu_memory_mb = gpu_info.get("memory_mb", 0)
    profile.has_cuda = gpu_info.get("has_cuda", False)
    profile.cuda_version = gpu_info.get("cuda_version", "")

    # 可用工具检测
    profile.available_tools = _detect_available_tools()

    _profile_cache = profile
    logger.info(
        f"capability.detected os={profile.platform_os} arch={profile.platform_arch} "
        f"gpu={profile.has_gpu} cores={profile.cpu_cores} ram={profile.total_ram_gb:.1f}GB"
    )
    return profile


def _detect_cpu_cores() -> int:
    try:
        import psutil
        return psutil.cpu_count(logical=True) or 1
    except ImportError:
        return os.cpu_count() or 1


def _detect_ram() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        return 0.0


def _detect_gpu() -> dict:
    result: dict = {"has_gpu": False}

    # nvidia-smi 检测
    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                timeout=5, text=True,
            ).strip()
            if output:
                parts = output.split(", ")
                result["has_gpu"] = True
                result["name"] = parts[0]
                result["memory_mb"] = int(float(parts[1])) if len(parts) > 1 else 0
        except Exception:
            logger.debug("capability_detector.gpu_detect_failed", exc_info=True)

        # CUDA 版本
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                timeout=5, text=True,
            ).strip()
            if output and output != "N/A":
                result["has_cuda"] = True
                result["cuda_version"] = output
        except Exception:
            logger.debug("capability.cuda_detect_failed", exc_info=True)

    # ROCm 检测（AMD GPU）
    if not result["has_gpu"] and shutil.which("rocm-smi"):
        try:
            output = subprocess.check_output(
                ["rocm-smi", "--showproductname"], timeout=5, text=True,
            )
            if "GPU" in output:
                result["has_gpu"] = True
                result["name"] = "AMD GPU"
                result["has_cuda"] = False
        except Exception:
            logger.debug("capability_detector.rocm_detect_failed", exc_info=True)

    return result


def _detect_available_tools() -> list[str]:
    """检测系统可用命令行工具。"""
    tools = []
    for tool in ["git", "python3", "pip", "docker", "ffmpeg", "node", "npm"]:
        if shutil.which(tool):
            tools.append(tool)
    return tools

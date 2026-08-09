"""本地部署路由：向量嵌入引擎管理（API / 本地模型切换、启动/停止、日志）。

WebUI 侧边栏"本地部署"页：选择向量嵌入引擎——远程 API（硅基流动）
或内置本地 BGE CPU 模型。使用本地模型前必须先"启动"，
页面下方展示启动/运行日志。
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from web.config_service import get_config_service
from web.routers.auth import get_current_user
from web.schemas import Envelope

router = APIRouter(tags=["local-deploy"], dependencies=[Depends(get_current_user)])

# 设备探测缓存：5 分钟有效
_DEVICE_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_DEVICE_CACHE_TTL = 300.0

# CPU 占用采样（/proc/stat 差值法，跨调用计算）
_CPU_SAMPLE: dict[str, Any] = {"ts": 0.0, "total": 0, "idle": 0}


def _cpu_stats() -> dict:
    """CPU 性能与实时占用：核数 / 频率 / 占用百分比。

    Linux 用 /proc 差值法；Windows/macOS 用 psutil（跨平台采样）。
    """
    stats: dict[str, Any] = {"cores": None, "freq_mhz": None, "usage_pct": None}
    try:
        stats["cores"] = os.cpu_count() or 0
    except Exception:  # noqa: BLE001
        pass

    if platform.system() != "Linux":
        # Windows/macOS：psutil.cpu_freq() / cpu_percent() 跨平台可用
        try:
            import psutil as _ps
        except ImportError:  # noqa: BLE001
            return stats
        try:
            freq = _ps.cpu_freq()
            if freq is not None and freq.current:
                stats["freq_mhz"] = round(freq.current)
        except Exception:  # noqa: BLE001
            pass
        try:
            # interval=None：非阻塞，首次调用返回 0.0，后续轮询（5s）取到真实值
            stats["usage_pct"] = round(_ps.cpu_percent(interval=None), 1)
        except Exception:  # noqa: BLE001
            pass
        return stats

    # 频率：/proc/cpuinfo "cpu MHz" → cpufreq sysfs（kHz）→ 未知
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("cpu MHz"):
                    stats["freq_mhz"] = round(float(line.split(":")[1].strip()))
                    break
    except (OSError, ValueError):  # noqa: BLE001
        pass
    if not stats["freq_mhz"]:
        # 额定频率：cpuinfo_max_freq（性能规格）优先，回退当前频率
        try:
            for i in range(64):
                for f in ("cpuinfo_max_freq", "cpuinfo_cur_freq"):
                    p = f"/sys/devices/system/cpu/cpu{i}/cpufreq/{f}"
                    if os.path.exists(p):
                        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                            stats["freq_mhz"] = round(int(fh.read().strip()) / 1000)
                        break
                if stats["freq_mhz"]:
                    break
        except (OSError, ValueError):  # noqa: BLE001
            pass
    # 占用百分比：两次采样间 (1 - idle/total) × 100
    try:
        with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as f:
            parts = f.readline().split()
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        total = sum(nums)
        now = time.monotonic()
        prev = _CPU_SAMPLE
        if prev["total"] and (now - prev["ts"]) > 0.2:
            dt = total - prev["total"]
            di = idle - prev["idle"]
            if dt > 0:
                stats["usage_pct"] = round((1 - di / dt) * 100, 1)
        _CPU_SAMPLE.update(ts=now, total=total, idle=idle)
    except (OSError, ValueError):  # noqa: BLE001
        pass
    return stats


def _detect_cpu_model() -> str:
    """读取 CPU 型号：Linux 依次尝试 model name / Hardware / 设备树 / Processor；
    Windows 用 PowerShell CIM 拿型号（如 "12th Gen Intel(R) Core(TM) i7-12700H"）。"""
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            for key in ("model name", "Hardware", "Processor"):
                m = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", txt, re.M)
                if m:
                    val = m.group(1).strip()
                    if val and val.lower() != "unknown":
                        return val
        except OSError:
            pass
    if platform.system() == "Windows":
        # 零开销兜底：PROCESSOR_IDENTIFIER（"Intel64 Family 6 ..."）
        pid = os.environ.get("PROCESSOR_IDENTIFIER", "")
        try:
            import subprocess
            ps = ("powershell -NoProfile -Command "
                  '"Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"')
            out = subprocess.run(ps, capture_output=True, text=True, timeout=15, check=False).stdout
            name = next((ln.strip() for ln in out.splitlines() if ln.strip()), "")
            if name:
                return name
        except (OSError, subprocess.SubprocessError):  # noqa: BLE001
            pass
        return pid or platform.processor() or "CPU"
    return platform.processor() or "CPU"


def _detect_gpu_model() -> str:
    """检测 GPU 型号：Linux 用 lspci 查 VGA/3D 控制器；Windows 用 PowerShell CIM
    枚举显卡控制器（不依赖 nvidia-smi——它默认不在 PATH）。"""
    if platform.system() == "Linux":
        import subprocess
        try:
            out = subprocess.run(
                ["lspci"], capture_output=True, text=True, timeout=5, check=False,
            ).stdout
            for line in out.splitlines():
                low = line.lower()
                if "vga" in low or "3d controller" in low or "display controller" in low:
                    # 提取设备名：lspci 行形如 "01:00.0 VGA compatible controller: NVIDIA ..."
                    seg = line.split(":", 2)[-1].strip()
                    seg = re.sub(r"^VGA compatible controller:\s*", "", seg)
                    seg = re.sub(r"^3D controller:\s*", "", seg)
                    return seg.strip() or "GPU"
            return ""
        except (OSError, subprocess.SubprocessError):
            return ""
    if platform.system() == "Windows":
        return _detect_gpu_model_windows()
    return ""


def _detect_gpu_model_windows() -> str:
    """Windows：Get-CimInstance Win32_VideoController 枚举显卡（含核显+独显）。

    优先独立显卡（NVIDIA / AMD Radeon / GeForce），其次 Intel 核显，最后任意。
    """
    import subprocess
    try:
        ps = ("powershell -NoProfile -Command "
              '"Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"')
        out = subprocess.run(ps, capture_output=True, text=True, timeout=15, check=False).stdout
        names = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not names:
            return ""
        prefer = [n for n in names
                  if any(k in n.lower() for k in ("nvidia", "radeon", "amd", "geforce", "rtx", "gtx"))]
        return (prefer or names)[0]
    except (OSError, subprocess.SubprocessError):  # noqa: BLE001
        return ""


def _detect_devices() -> dict:
    """探测本机算力设备（带 5 分钟缓存）。

    返回：
        current: 当前本地推理设备
        devices: CPU 恒可用，PC GPU 保留探测展示。
    """
    now = time.monotonic()
    if _DEVICE_CACHE["data"] is not None and (now - _DEVICE_CACHE["ts"]) < _DEVICE_CACHE_TTL:
        return _DEVICE_CACHE["data"]

    cpu_model = _detect_cpu_model()
    gpu_model = _detect_gpu_model()

    devices = [
        {
            "id": "cpu",
            "name": "CPU",
            "model": cpu_model or "CPU",
            "desc": "onnxruntime 推理，离线可用（默认）",
            "available": True,
        },
        {
            "id": "gpu",
            "name": "GPU",
            "model": gpu_model or "未检测到独立显卡",
            "desc": "此模型暂不支持 GPU 推理",
            "available": False,
        },
    ]
    data = {"current": "cpu", "devices": devices}
    _DEVICE_CACHE.update(ts=now, data=data)
    return data


def _get_vector_store(request: Request) -> Any:
    """从全局 core 获取 VectorStore 单例（可能为 None：向量库未初始化）。"""
    core = getattr(request.app.state, "core", None)
    return getattr(core, "_vec_store", None) if core is not None else None


def _fallback_status() -> dict:
    """向量库不可用时返回的环境状态（只读，页面仍可展示）。"""
    return {
        "mode": os.getenv("EMBED_MODE", "local"),
        "engine_running": False,
        "backend": "cpu",
        "api_configured": bool(
            os.getenv("SILICONFLOW_API_KEY") or os.getenv("EMBED_API_KEY")),
        "model_dir": "",
        "dimensions": 0,
        "available": False,
    }


@router.get("/local-deploy/devices", response_model=Envelope[dict])
async def local_deploy_devices(request: Request) -> Any:
    """算力设备检测：CPU 与 PC GPU 探测结果。"""
    data = _detect_devices()
    data["runtime_backend"] = "cpu"
    # 附加实时性能/占用数据（不做 5 分钟缓存，保持页面 5s 轮询下的新鲜度）
    for dev in data.get("devices", []):
        if dev["id"] == "cpu":
            dev["stats"] = _cpu_stats()
        else:
            dev["stats"] = {"status": "unavailable"}
    return Envelope(data=data)


@router.get("/local-deploy/status", response_model=Envelope[dict])
async def local_deploy_status(request: Request) -> Any:
    """当前 embedding 引擎状态：模式 / 本地引擎运行状态 / API 配置。"""
    vs = _get_vector_store(request)
    if vs is None:
        logger.info("local_deploy.status vector_store_unavailable")
        return Envelope(data=_fallback_status())
    status = vs.embed_engine_status()
    status["available"] = True
    return Envelope(data=status)


@router.post("/local-deploy/mode", response_model=Envelope[dict])
async def local_deploy_set_mode(request: Request, body: dict) -> Any:
    """切换 embedding 引擎：local=本地模型 / remote=远程 API（热生效 + 持久化）。"""
    vs = _get_vector_store(request)
    if vs is None:
        raise HTTPException(status_code=409, detail="Vector store not initialized")
    mode = str((body or {}).get("mode", "")).strip().lower()
    if mode not in ("local", "remote"):
        raise HTTPException(status_code=422, detail="mode must be 'local' or 'remote'")
    status = await asyncio.to_thread(vs.set_embed_mode, mode)
    get_config_service().set("local_deploy.mode", mode)
    logger.info("local_deploy.mode_switched mode={}", mode)
    return Envelope(data=status)


@router.post("/local-deploy/start", response_model=Envelope[dict])
async def local_deploy_start(request: Request) -> Any:
    """启动本地 embedding 引擎：预加载 CPU 模型，必须先启动再使用。"""
    vs = _get_vector_store(request)
    if vs is None:
        raise HTTPException(status_code=409, detail="Vector store not initialized")
    status = await asyncio.to_thread(vs.start_local_engine)
    get_config_service().set("local_deploy.mode", "local")
    return Envelope(data=status)


@router.post("/local-deploy/stop", response_model=Envelope[dict])
async def local_deploy_stop(request: Request) -> Any:
    """停止本地 embedding 引擎：释放 onnxruntime session。"""
    vs = _get_vector_store(request)
    if vs is None:
        raise HTTPException(status_code=409, detail="Vector store not initialized")
    status = await asyncio.to_thread(vs.stop_local_engine)
    return Envelope(data=status)


@router.get("/local-deploy/logs", response_model=Envelope[list[str]])
async def local_deploy_logs(request: Request, limit: int = 60, topic: str = "deploy") -> Any:
    """返回本地部署相关日志（agent.log 尾部，按 topic 过滤）。

    topic=deploy  向量嵌入引擎：启动/停止/模式切换/后端选择
    topic=device  算力设备探测
    """
    from config import LOG_DIR
    log_file = LOG_DIR / "agent.log"
    n = min(max(int(limit), 10), 500)
    tail: list[str] = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                tail = f.readlines()[-500:]
        except OSError:
            tail = []
    if topic == "device":
        keywords = ("local_deploy", "device")
    else:
        keywords = ("embed", "vector_store.local", "local_deploy")
    lines = [ln.rstrip("\n") for ln in tail
             if any(k in ln.lower() for k in keywords)][-n:]
    return Envelope(data=lines)

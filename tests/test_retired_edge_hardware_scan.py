import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_FILES = (
    "memory/npu_embed.py",
    "scripts/bench_local_latency.py",
    "scripts/bench_npu_retrieval.py",
    "scripts/npu/bge_npu_runner",
    "scripts/npu/bge_npu_runner.c",
    "tools/vision_tools.py",
    "utils/npu_inference.py",
)
SCANNED_PATHS = (
    "agent.py",
    "agent_core",
    "agent_dispatcher.py",
    "config",
    "config.py",
    "core",
    "deploy",
    "docker-compose.yml",
    "memory",
    "prompt_builder.py",
    "requirements.txt",
    "security",
    "slash_commands.py",
    "tools",
    "tool_engine",
    "utils",
    "web/agent_registry.py",
    "web/config_service.py",
    "web/media_tasks.py",
    "web/routers/local_deploy.py",
    "web/server.py",
    "web/frontend/src/i18n/en.ts",
    "web/frontend/src/i18n/zh.ts",
    "web/frontend/src/views/LocalDeployView.vue",
    "xiaoda-agent.spec",
    ".env.example",
)
CURRENT_DOCS = (
    "README.md",
    "SETUP.md",
    "USAGE.md",
    "docs/ARCHITECTURE.md",
    "docs/juejin-article.md",
)
RETIRED_PATTERN = re.compile(
    r"\bNPU\b|\bnpu[_-]|摄像头|camera_capture|vision_analyze|"
    r"Orange\s*Pi|orangepi|RK3588|GPIO|gpio_control|I2C|i2c_comm|"
    r"SPI|UART|PWM|pwm_control|hardware_status|/dev/video|/dev/vipcore|"
    r"/dev/gpio|/dev/i2c|/sys/class/pwm|ENABLE_NPU|NPU_NBG"
)
TEXT_SUFFIXES = {".py", ".json", ".json5", ".yaml", ".yml", ".md", ".txt", ".sh", ".ps1", ".bat", ".vue", ".ts"}
IGNORED_PARTS = {"node_modules", "dist", "__pycache__"}
PRIVACY_FILTER_FILES = {Path("security/security.py"), Path("config/security_patterns.yaml")}


def _iter_scanned_files():
    for relative in (*SCANNED_PATHS, *CURRENT_DOCS):
        path = ROOT / relative
        if path.is_file():
            yield path
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if (
                    candidate.is_file()
                    and candidate.suffix in TEXT_SUFFIXES
                    and not IGNORED_PARTS.intersection(candidate.parts)
                ):
                    yield candidate


def test_retired_edge_hardware_files_are_deleted():
    assert [relative for relative in RETIRED_FILES if (ROOT / relative).exists()] == []


def test_runtime_config_deployment_and_current_docs_have_no_retired_residue():
    matches = []
    for path in _iter_scanned_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), 1):
            if path.relative_to(ROOT) in PRIVACY_FILTER_FILES and re.search(r"orange\s|orangepi|香橙派", line):
                continue
            if RETIRED_PATTERN.search(line):
                matches.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    assert matches == []


def test_pc_gpu_capability_remains_supported():
    detector = (ROOT / "core" / "capability_detector.py").read_text(encoding="utf-8")
    local_deploy = (ROOT / "web" / "routers" / "local_deploy.py").read_text(encoding="utf-8")
    vision_service = (ROOT / "utils" / "vision_service.py").read_text(encoding="utf-8")
    assert "nvidia-smi" in detector
    assert "rocm-smi" in detector
    assert '"id": "gpu"' in local_deploy
    assert "set_vulkan_device(gpu_index)" in vision_service


def test_builtin_agents_do_not_advertise_retired_hardware_execution():
    bootstrap = (ROOT / "core" / "bootstrap.py").read_text(encoding="utf-8")
    registry = (ROOT / "web" / "agent_registry.py").read_text(encoding="utf-8")
    tool_registry = (ROOT / "tool_engine" / "tool_registry.py").read_text(encoding="utf-8")

    assert '"hardware"' not in bootstrap
    assert '"hardware"' not in registry
    assert '"hardware"' not in tool_registry

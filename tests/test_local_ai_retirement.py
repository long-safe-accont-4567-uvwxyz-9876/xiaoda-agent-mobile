import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RETIRED_FILES = (
    "memory/local_embed.py",
    "web/routers/local_deploy.py",
    "web/frontend/src/views/LocalDeployView.vue",
    "models/bge-small-zh-v1.5",
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
    "model_router.py",
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
    "web/routers",
    "web/server.py",
    "web/_provider_keys.py",
    "web/frontend/src/i18n/en.ts",
    "web/frontend/src/i18n/zh.ts",
    "web/frontend/src/router",
    "web/frontend/src/views",
    "web/frontend/src/components",
    "config/provider_metadata.json",
    "xiaoda-agent.spec",
    ".env.example",
)

CURRENT_DOCS = (
    "README.md",
    "SETUP.md",
    "USAGE.md",
    "docs/ARCHITECTURE.md",
)

RETIRED_PATTERN = re.compile(
    r"\bollama\b|OLLAMA_|local[_-]deploy|LocalDeploy|LocalEmbed|"
    r"local_embed|bge-small-zh|onnxruntime|\bnpu[_-]?embed\b|LocalEmbedProvider",
    re.IGNORECASE,
)

TEXT_SUFFIXES = {".py", ".json", ".json5", ".yaml", ".yml", ".md", ".txt", ".sh", ".ps1", ".bat", ".vue", ".ts"}
IGNORED_PARTS = {"node_modules", "dist", "__pycache__", ".git"}


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


def test_retired_local_ai_files_are_deleted():
    assert [relative for relative in RETIRED_FILES if (ROOT / relative).exists()] == []


def test_runtime_config_and_current_docs_have_no_local_ai_residue():
    matches = []
    for path in _iter_scanned_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), 1):
            if RETIRED_PATTERN.search(line):
                matches.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    assert matches == []


def test_local_ai_dependencies_removed_from_requirements():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
    assert "onnxruntime" not in requirements
    assert "tokenizers" not in requirements


def test_provider_metadata_has_no_ollama_entry():
    metadata_path = ROOT / "config" / "provider_metadata.json"
    if not metadata_path.exists():
        return
    text = metadata_path.read_text(encoding="utf-8", errors="ignore").lower()
    assert "ollama" not in text

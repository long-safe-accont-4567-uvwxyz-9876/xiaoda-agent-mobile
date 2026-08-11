import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_PATHS = (
    "memory/local_embed.py",
    "models/bge-small-zh-v1.5",
    "scripts/rebuild_vec_local.py",
    "web/frontend/src/views/LocalDeployView.vue",
    "web/routers/local_deploy.py",
)
SCANNED_PATHS = (
    ".env.example",
    ".github/workflows",
    "SETUP.md",
    "USAGE.md",
    "config",
    "core",
    "docs/ARCHITECTURE.md",
    "memory",
    "model_router.py",
    "requirements.txt",
    "requirements.lock",
    "scripts",
    "setup_wizard.py",
    "security",
    "utils",
    "web",
)
IGNORED_PARTS = {"__pycache__", "dist", "node_modules"}
TEXT_SUFFIXES = {
    ".css",
    ".example",
    ".html",
    ".js",
    ".json",
    ".json5",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}
ALLOWED_FILES = {
    Path("web/config_migrations.py"),
}
RETIRED_PATTERN = re.compile(
    r"\bollama\b|OLLAMA_|local-deploy|local_deploy|LocalDeploy|LocalEmbed|"
    r"bge-small-zh-v1\.5|onnxruntime|tokenizers",
    re.IGNORECASE,
)


def _iter_production_files():
    for relative in SCANNED_PATHS:
        path = ROOT / relative
        if path.is_file():
            yield path
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if IGNORED_PARTS.intersection(candidate.parts):
                continue
            if candidate.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if candidate.relative_to(ROOT) in ALLOWED_FILES:
                continue
            yield candidate


def test_retired_local_ai_paths_are_deleted():
    assert [relative for relative in RETIRED_PATHS if (ROOT / relative).exists()] == []


def test_production_has_no_retired_local_ai_or_ollama_references():
    matches = []
    for path in _iter_production_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), 1):
            if RETIRED_PATTERN.search(line):
                matches.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    assert matches == []

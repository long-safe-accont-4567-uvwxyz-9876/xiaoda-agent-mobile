import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED_PATHS = (
    "memory/local_embed.py",
    "models/bge-small-zh-v1.5",
    "scripts/rebuild_vec_local.py",
    "tests/test_local_embed_mode.py",
)
PRODUCTION_FILES = (
    ".env.example",
    ".github/workflows/build-release.yml",
    "SETUP.md",
    "USAGE.md",
    "core/bootstrap.py",
    "memory/vector_store.py",
    "requirements.txt",
    "scripts/bench_vec_search.py",
    "setup_wizard.py",
    "tool_engine/tool_search.py",
    "web/server.py",
    "xiaoda-agent.spec",
)
RETIRED_TERMS = (
    "EMBED_BASE_URL",
    "EMBED_MODE",
    "LOCAL_EMBED_",
    "LocalEmbeddingProvider",
    "bge-small-zh-v1.5",
    "onnxruntime",
    "tokenizers",
    "start_local_engine",
    "stop_local_engine",
    "set_embed_mode",
    "embed_engine_status",
    "text-embedding-3-small",
)


def test_local_embedding_code_assets_and_tests_are_deleted():
    assert [path for path in RETIRED_PATHS if (ROOT / path).exists()] == []


def test_production_and_release_files_do_not_reference_local_embedding():
    matches = []
    for relative in PRODUCTION_FILES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for term in RETIRED_TERMS:
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(f"{relative}: {term}")
    assert matches == []


def test_vector_store_constructor_is_remote_only():
    from inspect import signature

    from memory.vector_store import VectorStore

    parameters = signature(VectorStore).parameters
    assert "embed_base_url" not in parameters
    assert "embed_mode" not in parameters
    assert "local_model_dir" not in parameters
    assert "local_query_prefix" not in parameters


def test_vector_store_without_remote_key_disables_embedding(tmp_path):
    from memory.vector_store import VectorStore

    store = VectorStore(tmp_path / "vec.db", embed_api_key="")
    assert store._embed_client is None


def test_remote_embedding_model_environment_is_consumed_by_bootstrap():
    bootstrap = (ROOT / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert 'os.getenv("EMBED_MODEL"' in bootstrap
    assert "embed_model=embed_model" in bootstrap


def test_embedding_runtime_is_fixed_to_siliconflow():
    vector_store = (ROOT / "memory" / "vector_store.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "core" / "bootstrap.py").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'base_url="https://api.siliconflow.cn/v1"' in vector_store
    assert "EMBED_BASE_URL" not in bootstrap
    assert "EMBED_BASE_URL" not in env_example


def test_tool_vector_search_creates_only_siliconflow_client():
    tool_search = (ROOT / "tool_engine" / "tool_search.py").read_text(
        encoding="utf-8"
    )
    assert 'base_url="https://api.siliconflow.cn/v1"' in tool_search
    assert "def enable_vector_search(\n        self,\n        api_key: str," in tool_search

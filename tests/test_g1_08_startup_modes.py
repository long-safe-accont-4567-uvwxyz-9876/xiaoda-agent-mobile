from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.bootstrap import AgentCoreBootstrapper
from web.routers.insight import create_memory, semantic_search_status


def _bootstrapper(core):
    bootstrapper = AgentCoreBootstrapper.__new__(AgentCoreBootstrapper)
    bootstrapper.core = core
    return bootstrapper


def _core(tmp_path):
    db = SimpleNamespace(
        init=AsyncMock(),
        db_path=tmp_path / "agent.db",
        analytics=object(),
    )
    return SimpleNamespace(
        db=db,
        router=SimpleNamespace(set_db=MagicMock()),
        _vec_store=object(),
    )


@pytest.mark.asyncio
async def test_startup_without_embedding_key_disables_semantic_search(
    tmp_path,
    monkeypatch,
):
    core = _core(tmp_path)
    monkeypatch.delenv("EMBED_API_KEY", raising=False)

    with patch("memory.vector_store.VectorStore") as vector_store:
        await _bootstrapper(core)._init_infrastructure()

    vector_store.assert_not_called()
    assert core._vec_store is None
    assert semantic_search_status(core) == {
        "enabled": False,
        "mode": "disabled",
        "reason": "embedding_key_missing",
        "model": None,
        "dimensions": 0,
    }


@pytest.mark.asyncio
async def test_startup_with_embedding_key_enables_siliconflow_store(
    tmp_path,
    monkeypatch,
):
    core = _core(tmp_path)
    store = MagicMock()
    store.init = AsyncMock()
    store.ready = True
    store.dimensions = 1024
    store._embed_model = "BAAI/bge-m3"
    monkeypatch.setenv("EMBED_API_KEY", "test-key")
    monkeypatch.setenv("EMBED_MODEL", "BAAI/bge-m3")

    with patch("memory.vector_store.VectorStore", return_value=store) as vector_store:
        await _bootstrapper(core)._init_infrastructure()

    vector_store.assert_called_once_with(
        db_path=str(tmp_path / "agent_vec.db"),
        embed_api_key="test-key",
        embed_model="BAAI/bge-m3",
    )
    store.init.assert_awaited_once()
    assert core._vec_store is store
    assert semantic_search_status(core) == {
        "enabled": True,
        "mode": "remote",
        "reason": None,
        "model": "BAAI/bge-m3",
        "dimensions": 1024,
    }


@pytest.mark.asyncio
async def test_text_memory_creation_works_without_vector_store():
    db = SimpleNamespace(
        memory=SimpleNamespace(
            insert_episodic_memory=AsyncMock(return_value=42),
        ),
        commit=AsyncMock(),
    )
    core = SimpleNamespace(
        db=db,
        memory=SimpleNamespace(vec=None),
        _vec_store=None,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=core)),
    )

    response = await create_memory({"summary": "纯文本记忆"}, request)

    assert response.data == {"id": 42}
    db.memory.insert_episodic_memory.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("embed_key", [None, "test-key"])
async def test_embedding_mode_does_not_change_other_provider_routing(
    monkeypatch,
    embed_key,
):
    from model_router import ModelRouter

    router = ModelRouter.__new__(ModelRouter)
    router._client = MagicMock(name="mimo_client")
    router._agnes_client = None
    router._custom_clients = {
        "agnes": MagicMock(name="agnes_custom_client"),
    }
    router._credential_locks = {}
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_BASE_URL", raising=False)
    if embed_key is None:
        monkeypatch.delenv("EMBED_API_KEY", raising=False)
    else:
        monkeypatch.setenv("EMBED_API_KEY", embed_key)

    client = await router._select_client_for_provider("agnes")

    assert client is router._custom_clients["agnes"]
    assert client is not router._client

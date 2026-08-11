from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _write_config(path: Path, providers: dict, chat_model: dict | None = None) -> bytes:
    data = {
        "models": {
            "providers": providers,
            "routes": {
                "chat": {
                    "client": "ollama",
                    "model": "qwen2.5:latest",
                    "max_tokens": 4096,
                },
                "vision": {"client": "agnes", "model": "agnes-2.0-flash"},
            },
        },
        "local_deploy": {"mode": "local"},
        "ui": {"particles": "low"},
    }
    if chat_model is not None:
        data["models"]["chat_model"] = chat_model
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path.read_bytes()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_provider_replaces_retired_model_references(tmp_path):
    from web.config_migrations import migrate_retired_local_ai_config

    config_path = tmp_path / "webui_overrides.json"
    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    credential_path = credentials_dir / "provider_ollama.key"
    credential_path.write_text("ollama", encoding="utf-8")
    _write_config(
        config_path,
        {
            "ollama": {"default_model": "qwen2.5:latest", "enabled": True},
            "remote": {"default_model": "remote-chat", "enabled": True},
        },
        {"provider": "ollama", "model_id": "qwen2.5:latest"},
    )

    result = migrate_retired_local_ai_config(config_path, credentials_dir)

    migrated = _load(config_path)
    assert result.changed is True
    assert result.replacement_provider == "remote"
    assert migrated["models"]["providers"] == {
        "remote": {"default_model": "remote-chat", "enabled": True}
    }
    assert migrated["models"]["chat_model"] == {
        "provider": "remote",
        "model_id": "remote-chat",
    }
    assert migrated["models"]["routes"]["chat"]["client"] == "remote"
    assert migrated["models"]["routes"]["chat"]["model"] == "remote-chat"
    assert migrated["models"]["routes"]["vision"] == {
        "client": "agnes",
        "model": "agnes-2.0-flash",
    }
    assert "local_deploy" not in migrated
    assert "provider_setup_required" not in migrated["models"]
    assert not credential_path.exists()
    assert result.backup_path is not None
    assert result.backup_path.exists()


@pytest.mark.parametrize(
    "providers",
    [
        {
            "ollama": {"default_model": "qwen2.5:latest", "enabled": True},
            "first": {"default_model": "first-model", "enabled": True},
            "second": {"default_model": "second-model", "enabled": True},
        },
        {"ollama": {"default_model": "qwen2.5:latest", "enabled": True}},
    ],
)
def test_ambiguous_or_missing_provider_requires_configuration(tmp_path, providers):
    from web.config_migrations import migrate_retired_local_ai_config

    config_path = tmp_path / "webui_overrides.json"
    _write_config(
        config_path,
        providers,
        {"provider": "ollama", "model_id": "qwen2.5:latest"},
    )

    result = migrate_retired_local_ai_config(config_path, tmp_path / "credentials")

    migrated = _load(config_path)
    assert result.replacement_provider is None
    assert migrated["models"]["provider_setup_required"] is True
    assert "chat_model" not in migrated["models"]
    assert "client" not in migrated["models"]["routes"]["chat"]
    assert "model" not in migrated["models"]["routes"]["chat"]
    assert migrated["models"]["routes"]["chat"]["max_tokens"] == 4096


def test_atomic_write_failure_preserves_original_config_and_credential(tmp_path):
    from web.config_migrations import migrate_retired_local_ai_config

    config_path = tmp_path / "webui_overrides.json"
    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    credential_path = credentials_dir / "provider_ollama.key"
    credential_path.write_text("ollama", encoding="utf-8")
    original = _write_config(
        config_path,
        {"ollama": {"default_model": "qwen2.5:latest", "enabled": True}},
    )

    def failing_write(path, content):
        if Path(path) == config_path:
            raise OSError("disk full")
        Path(path).write_bytes(content if isinstance(content, bytes) else content.encode())

    with pytest.raises(OSError, match="disk full"):
        migrate_retired_local_ai_config(
            config_path,
            credentials_dir,
            atomic_writer=failing_write,
        )

    assert config_path.read_bytes() == original
    assert credential_path.exists()


def test_credential_delete_failure_restores_original_config(tmp_path):
    from web.config_migrations import migrate_retired_local_ai_config

    config_path = tmp_path / "webui_overrides.json"
    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    credential_path = credentials_dir / "provider_ollama.key"
    credential_path.write_text("ollama", encoding="utf-8")
    original = _write_config(
        config_path,
        {"ollama": {"default_model": "qwen2.5:latest", "enabled": True}},
    )

    def failing_unlink(path):
        raise PermissionError(str(path))

    with pytest.raises(PermissionError):
        migrate_retired_local_ai_config(
            config_path,
            credentials_dir,
            credential_remover=failing_unlink,
        )

    assert config_path.read_bytes() == original
    assert credential_path.exists()


def test_startup_provider_registration_ignores_retired_provider():
    from web.server import _register_all_providers, _register_env_providers

    cfg = MagicMock()
    cfg.get.return_value = {
        "ollama": {
            "format": "openai",
            "base_url": "http://localhost:11434/v1",
            "enabled": True,
        }
    }
    register = MagicMock()
    load_key = MagicMock(return_value="ollama")
    core = MagicMock()

    with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://localhost:11434/v1"}):
        _register_env_providers(cfg, {"OLLAMA_BASE_URL": "http://localhost:11434/v1"}, MagicMock())
        _register_all_providers(cfg, core, load_key, register)

    cfg.set.assert_not_called()
    load_key.assert_not_called()
    register.assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_initialization_migrates_before_loading_config_service():
    from web import server

    events = []
    cfg = MagicMock()
    app = MagicMock()
    app.state.core = MagicMock()
    registry = MagicMock()
    registry.load_persisted = AsyncMock()

    with patch.object(server, "_run_startup_config_migrations", side_effect=lambda: events.append("migrate")), \
         patch("web.config_service.get_config_service", side_effect=lambda: events.append("load") or cfg), \
         patch("web.agent_registry.AgentRegistry", return_value=registry):
        await server._init_lifespan_resources(app)

    assert events[:2] == ["migrate", "load"]

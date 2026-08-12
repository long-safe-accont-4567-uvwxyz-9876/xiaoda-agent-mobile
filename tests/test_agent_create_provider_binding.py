from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_create_agent_resolves_selected_provider_without_advanced_fields(monkeypatch):
    from web.agent_registry import AgentRegistry

    registered = []

    async def register(config):
        registered.append(config)
        return True

    dispatcher = SimpleNamespace(get_agent=lambda name: None, register=register)
    registry = AgentRegistry.__new__(AgentRegistry)
    registry.core = SimpleNamespace(dispatcher=dispatcher)
    registry._save_config = lambda config: None
    monkeypatch.setattr(
        registry,
        "_resolve_provider_info",
        lambda provider: ("https://local.example/v1", "PROVIDER_LOCAL_KEY"),
    )

    result = await registry.create({
        "name": "mobile_helper",
        "display_name": "????",
        "provider": "local",
        "model": "mobile-model",
        "personality_text": "?????????????",
    })

    assert result["provider"] == "local"
    assert result["base_url"] == "https://local.example/v1"
    assert result["api_key_env"] == "PROVIDER_LOCAL_KEY"
    assert registered[0].base_url == "https://local.example/v1"
    assert registered[0].api_key_env == "PROVIDER_LOCAL_KEY"


@pytest.mark.asyncio
async def test_create_agent_preserves_explicit_advanced_provider_fields(monkeypatch):
    from web.agent_registry import AgentRegistry

    registered = []

    async def register(config):
        registered.append(config)
        return True

    registry = AgentRegistry.__new__(AgentRegistry)
    registry.core = SimpleNamespace(
        dispatcher=SimpleNamespace(get_agent=lambda name: None, register=register)
    )
    registry._save_config = lambda config: None
    resolver = AsyncMock(side_effect=AssertionError("explicit advanced fields must be preserved"))
    monkeypatch.setattr(registry, "_resolve_provider_info", resolver)

    await registry.create({
        "name": "advanced_helper",
        "display_name": "????",
        "provider": "private",
        "model": "private-model",
        "base_url": "https://private.example/v1",
        "api_key_env": "PRIVATE_API_KEY",
    })

    assert registered[0].base_url == "https://private.example/v1"
    assert registered[0].api_key_env == "PRIVATE_API_KEY"
    resolver.assert_not_awaited()

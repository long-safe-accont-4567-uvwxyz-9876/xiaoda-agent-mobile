from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_persisted_custom_provider_key_counts_as_runtime_credential(monkeypatch):
    from web import _provider_keys

    config = SimpleNamespace(get=lambda path, default=None: {
        "android_local": {"enabled": True, "format": "openai"}
    } if path == "models.providers" else default)
    monkeypatch.setattr("web.config_service.get_config_service", lambda: config)
    monkeypatch.setattr(_provider_keys, "load_provider_key", lambda provider_id: "local-secret")

    assert _provider_keys.has_persisted_provider_credential() is True


def test_disabled_custom_provider_does_not_enable_runtime(monkeypatch):
    from web import _provider_keys

    config = SimpleNamespace(get=lambda path, default=None: {
        "disabled": {"enabled": False, "format": "openai"}
    } if path == "models.providers" else default)
    monkeypatch.setattr("web.config_service.get_config_service", lambda: config)
    monkeypatch.setattr(_provider_keys, "load_provider_key", lambda provider_id: "local-secret")

    assert _provider_keys.has_persisted_provider_credential() is False


@pytest.mark.asyncio
async def test_provider_change_reinitializes_degraded_core(monkeypatch):
    from web.routers import models

    core = SimpleNamespace(_initialized=False)

    async def init(*, reinit: bool = False):
        assert reinit is True
        core._initialized = True

    core.init = init
    registry = SimpleNamespace(load_persisted=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=core, agent_registry=registry)))
    start_services = AsyncMock()
    monkeypatch.setattr("web.app_ref.get_start_services", lambda: start_services)

    await models._ensure_core_initialized(request)

    start_services.assert_awaited_once_with(request.app, core)
    registry.load_persisted.assert_awaited_once()

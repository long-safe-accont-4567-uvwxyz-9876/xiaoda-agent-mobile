"""ProviderCoordinator 回归测试（G2）。

验证集中后的 provider 校验/持久化/注册协调器行为：
- 校验失败抛 ProviderValidationError 并携带 layer
- validate_only 不持久化、不注册
- create/update 正常路径持久化配置并注册客户端
- recover_startup 幂等恢复
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from web.provider_coordinator import (
    ProviderCoordinator,
    ProviderValidationError,
    get_provider_coordinator,
)


def _make_cfg(providers: dict | None = None) -> MagicMock:
    cfg = MagicMock()
    cfg.get.return_value = providers or {}
    return cfg


def _make_router() -> MagicMock:
    return MagicMock()


# ── create ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_rejects_invalid_id():
    cfg = _make_cfg()
    coord = ProviderCoordinator(cfg=cfg, router=_make_router())
    with pytest.raises(ProviderValidationError) as exc_info:
        await coord.create(
            {"id": "1bad", "format": "openai", "base_url": "https://api.example.com/v1"},
            api_key="sk-test",
            candidate_validator=lambda c, r: True,
        )
    assert exc_info.value.layer == "id"


@pytest.mark.asyncio
async def test_create_rejects_invalid_format():
    cfg = _make_cfg()
    coord = ProviderCoordinator(cfg=cfg, router=_make_router())
    with pytest.raises(ProviderValidationError) as exc_info:
        await coord.create(
            {"id": "mypv", "format": "gemini", "base_url": "https://api.example.com/v1"},
            api_key="sk-test",
            candidate_validator=lambda c, r: True,
        )
    assert exc_info.value.layer == "format"


@pytest.mark.asyncio
async def test_create_rejects_missing_api_key():
    cfg = _make_cfg()
    coord = ProviderCoordinator(cfg=cfg, router=_make_router())
    with pytest.raises(ProviderValidationError) as exc_info:
        await coord.create(
            {"id": "mypv", "format": "openai", "base_url": "https://api.example.com/v1"},
            api_key="",
            candidate_validator=lambda c, r: True,
        )
    assert exc_info.value.layer == "api_key"


@pytest.mark.asyncio
async def test_create_rejects_duplicate():
    cfg = _make_cfg(providers={"mypv": {"label": "existing"}})
    coord = ProviderCoordinator(cfg=cfg, router=_make_router())
    with pytest.raises(ProviderValidationError) as exc_info:
        await coord.create(
            {"id": "mypv", "format": "openai", "base_url": "https://api.example.com/v1"},
            api_key="sk-test",
            candidate_validator=lambda c, r: True,
        )
    assert exc_info.value.layer == "id"


@pytest.mark.asyncio
async def test_create_validate_only_does_not_persist():
    cfg = _make_cfg()
    router = _make_router()
    coord = ProviderCoordinator(cfg=cfg, router=router)
    data = await coord.create(
        {"id": "mypv", "label": "MyPV", "format": "openai",
         "base_url": "https://api.example.com/v1", "default_model": "gpt-4o"},
        api_key="sk-test",
        validate_only=True,
        candidate_validator=lambda c, r: True,
    )
    assert data["id"] == "mypv"
    assert data["label"] == "MyPV"
    cfg.set.assert_not_called()  # 未持久化


@pytest.mark.asyncio
async def test_create_persists_and_registers(monkeypatch):
    cfg = _make_cfg()
    router = _make_router()
    coord = ProviderCoordinator(cfg=cfg, router=router)

    registered = {}

    def fake_register(r, pid, fmt, base_url, key):
        registered["pid"] = pid
        registered["fmt"] = fmt
        registered["key"] = key

    monkeypatch.setattr("web.custom_providers.register_into_router", fake_register)
    monkeypatch.setattr(
        "web._provider_keys._encode_key", lambda k: f"enc:{k}")
    tmp = MagicMock()
    monkeypatch.setattr("web._provider_keys._key_file", lambda pid: tmp)
    monkeypatch.setattr("web._provider_keys._get_cred_dir", MagicMock())

    data = await coord.create(
        {"id": "mypv", "format": "openai", "base_url": "https://api.example.com/v1"},
        api_key="sk-test",
        candidate_validator=lambda c, r: True,
    )
    assert data["id"] == "mypv"
    cfg.set.assert_called_once()
    assert registered["pid"] == "mypv"
    assert registered["key"] == "sk-test"


# ── update ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_nonexistent_raises():
    cfg = MagicMock()
    cfg.get.return_value = None
    coord = ProviderCoordinator(cfg=cfg, router=_make_router())
    with pytest.raises(ProviderValidationError) as exc_info:
        await coord.update("ghost", {}, api_key=None,
                           candidate_validator=lambda c, r: True)
    assert exc_info.value.layer == "id"


@pytest.mark.asyncio
async def test_update_merges_and_persists(monkeypatch):
    existing = {"id": "mypv", "label": "old", "format": "openai",
                "base_url": "https://api.example.com/v1", "enabled": True}
    cfg = MagicMock()
    cfg.get.return_value = existing
    router = _make_router()
    coord = ProviderCoordinator(cfg=cfg, router=router)

    monkeypatch.setattr("web._provider_keys.load_provider_key", lambda pid: "sk-old")
    monkeypatch.setattr(
        "web.custom_providers.register_into_router", lambda *a, **k: None)
    monkeypatch.setattr(
        "web._provider_keys._encode_key", lambda k: f"enc:{k}")
    monkeypatch.setattr("web._provider_keys._key_file", lambda pid: MagicMock())
    monkeypatch.setattr("web._provider_keys._get_cred_dir", MagicMock())

    data = await coord.update("mypv", {"label": "new"}, api_key=None,
                              candidate_validator=lambda c, r: True)
    assert data["label"] == "new"
    assert data["base_url"] == "https://api.example.com/v1"
    cfg.set.assert_called_once()


# ── recover_startup ─────────────────────────────────────────────


def test_recover_startup_registers_configured_providers(monkeypatch):
    providers = {
        "pv1": {"format": "openai", "base_url": "https://api1.example.com/v1"},
        "pv2": {"format": "anthropic", "base_url": "https://api2.example.com"},
    }
    cfg = MagicMock()
    cfg.get.return_value = providers
    router = _make_router()

    keys = {"pv1": "sk-1", "pv2": "sk-2"}
    monkeypatch.setattr("web._provider_keys.load_provider_key",
                        lambda pid: keys.get(pid, ""))
    registered = []
    monkeypatch.setattr(
        "web.custom_providers.register_into_router",
        lambda r, pid, fmt, url, key: registered.append((pid, fmt, key)))

    coord = ProviderCoordinator(cfg=cfg, router=router)
    coord.recover_startup()
    assert len(registered) == 2
    assert {r[0] for r in registered} == {"pv1", "pv2"}


def test_recover_startup_skips_providers_without_key(monkeypatch):
    providers = {"pv1": {"format": "openai", "base_url": "https://api.example.com/v1"}}
    cfg = MagicMock()
    cfg.get.return_value = providers
    router = _make_router()

    monkeypatch.setattr("web._provider_keys.load_provider_key", lambda pid: "")
    registered = []
    monkeypatch.setattr(
        "web.custom_providers.register_into_router",
        lambda *a, **k: registered.append(1))

    coord = ProviderCoordinator(cfg=cfg, router=router)
    coord.recover_startup()
    assert registered == []


def test_recover_startup_is_best_effort(monkeypatch):
    providers = {
        "pv1": {"format": "openai", "base_url": "https://api.example.com/v1"},
        "pv2": {"format": "openai", "base_url": "https://api.example.com/v1"},
    }
    cfg = MagicMock()
    cfg.get.return_value = providers
    router = _make_router()

    keys = {"pv1": "sk-1", "pv2": "sk-2"}
    monkeypatch.setattr("web._provider_keys.load_provider_key",
                        lambda pid: keys[pid])

    calls = {"n": 0}

    def flaky_register(r, pid, fmt, url, key):
        calls["n"] += 1
        if pid == "pv1":
            raise RuntimeError("boom")

    monkeypatch.setattr("web.custom_providers.register_into_router", flaky_register)
    coord = ProviderCoordinator(cfg=cfg, router=router)
    coord.recover_startup()  # 不应抛
    assert calls["n"] == 2  # 两个都尝试


# ── singleton ───────────────────────────────────────────────────


def test_get_provider_coordinator_caches_and_refreshes():
    import web.provider_coordinator as pc
    pc._coordinator = None  # reset
    c1 = get_provider_coordinator(cfg=MagicMock(), router=MagicMock())
    c2 = get_provider_coordinator()
    assert c1 is c2
    new_router = MagicMock()
    c3 = get_provider_coordinator(router=new_router)
    assert c3 is c1
    assert c3._router is new_router
    pc._coordinator = None  # cleanup

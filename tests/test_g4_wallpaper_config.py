from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_dispatcher import SubAgentConfig
from web import agent_registry
from web.agent_registry import AgentRegistry
from web.wallpaper_config import (
    DEFAULT_WALLPAPER_FOCUS,
    DEFAULT_WALLPAPER_MOTION,
    DEFAULT_WALLPAPER_OVERLAY,
    normalize_wallpaper_fields,
)


def test_old_wallpaper_config_receives_backward_compatible_defaults():
    normalized = normalize_wallpaper_fields({"wallpaper": "/media/wallpapers/old.jpg"})

    assert normalized["wallpaper"] == "/media/wallpapers/old.jpg"
    assert normalized["wallpaper_focus"] == DEFAULT_WALLPAPER_FOCUS
    assert normalized["wallpaper_overlay"] == DEFAULT_WALLPAPER_OVERLAY
    assert normalized["wallpaper_motion"] == DEFAULT_WALLPAPER_MOTION


def test_wallpaper_fields_accept_range_boundaries_and_make_detached_focus_copy():
    original = {"x": 0.0, "y": 1.0}
    normalized = normalize_wallpaper_fields({
        "wallpaper_focus": original,
        "wallpaper_overlay": 1.0,
        "wallpaper_motion": "reduced",
    })
    original["x"] = 0.8

    assert normalized["wallpaper_focus"] == {"x": 0.0, "y": 1.0}
    assert normalized["wallpaper_overlay"] == 1.0
    assert normalized["wallpaper_motion"] == "reduced"


@pytest.mark.parametrize(
    "payload",
    [
        {"wallpaper_focus": {"x": -0.01, "y": 0.5}},
        {"wallpaper_focus": {"x": 0.5, "y": 1.01}},
        {"wallpaper_focus": {"x": "center", "y": 0.5}},
        {"wallpaper_overlay": -0.01},
        {"wallpaper_overlay": 1.01},
        {"wallpaper_motion": "parallax-forever"},
    ],
)
def test_wallpaper_fields_reject_invalid_ranges(payload):
    with pytest.raises(ValueError):
        normalize_wallpaper_fields(payload)


def test_partial_update_uses_existing_values_and_preserves_wallpaper_url():
    current = {
        "wallpaper": "/media/wallpapers/user.webp",
        "wallpaper_focus": {"x": 0.2, "y": 0.3},
        "wallpaper_overlay": 0.45,
        "wallpaper_motion": "none",
    }
    normalized = normalize_wallpaper_fields({"wallpaper_overlay": 0.7}, current=current)

    assert normalized == {
        "wallpaper": "/media/wallpapers/user.webp",
        "wallpaper_focus": {"x": 0.2, "y": 0.3},
        "wallpaper_overlay": 0.7,
        "wallpaper_motion": "none",
    }


def test_subagent_config_accepts_wallpaper_metadata_defaults():
    config = SubAgentConfig(name="custom", display_name="Custom", provider="openai", model="m")

    assert config.wallpaper_focus == DEFAULT_WALLPAPER_FOCUS
    assert config.wallpaper_overlay == DEFAULT_WALLPAPER_OVERLAY
    assert config.wallpaper_motion == DEFAULT_WALLPAPER_MOTION


@pytest.mark.asyncio
async def test_main_wallpaper_update_uses_one_atomic_batch(monkeypatch):
    updates = []
    service = SimpleNamespace(
        get=lambda _path: None,
        set_many=lambda value: updates.append(value),
    )
    monkeypatch.setattr("web.config_service.get_config_service", lambda: service)
    registry = AgentRegistry(SimpleNamespace(dispatcher=SimpleNamespace()))
    monkeypatch.setattr(registry, "get", lambda _name: dict(agent_registry.MAIN_AGENT_META))

    await registry.update("xiaoda", {
        "wallpaper": "/media/wallpapers/new.jpg",
        "wallpaper_focus": {"x": 0.2, "y": 0.7},
        "wallpaper_overlay": 0.4,
        "wallpaper_motion": "none",
    })

    assert updates == [{
        "ui.main_wallpaper": "/media/wallpapers/new.jpg",
        "ui.wallpaper_focus": {"x": 0.2, "y": 0.7},
        "ui.wallpaper_overlay": 0.4,
        "ui.wallpaper_motion": "none",
    }]


@pytest.mark.asyncio
async def test_custom_wallpaper_save_failure_restores_runtime_and_file(monkeypatch, tmp_path):
    config = SubAgentConfig(
        name="custom",
        display_name="Custom",
        provider="openai",
        model="m",
        wallpaper="/media/wallpapers/old.jpg",
    )
    agent = SimpleNamespace(config=config, reload_model_config=AsyncMock(), init=AsyncMock())
    dispatcher = SimpleNamespace(get_agent=lambda _name: agent)
    registry = AgentRegistry(SimpleNamespace(dispatcher=dispatcher))
    monkeypatch.setattr(agent_registry, "AGENTS_DIR", tmp_path)
    config_path = tmp_path / "custom.json"
    original = {"name": "custom", "wallpaper": "/media/wallpapers/old.jpg"}
    config_path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(
        agent_registry,
        "atomic_json_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        raising=False,
    )

    with pytest.raises(OSError, match="disk full"):
        await registry.update("custom", {
            "display_name": "Changed",
            "wallpaper": "/media/wallpapers/new.jpg",
        })

    assert config.display_name == "Custom"
    assert config.wallpaper == "/media/wallpapers/old.jpg"
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


@pytest.mark.asyncio
async def test_main_wallpaper_batch_failure_keeps_runtime_metadata(monkeypatch):
    original = {
        key: json.loads(json.dumps(agent_registry.MAIN_AGENT_META[key]))
        for key in ("wallpaper", "wallpaper_focus", "wallpaper_overlay", "wallpaper_motion")
    }
    service = SimpleNamespace(
        get=lambda _path: None,
        set_many=lambda _value: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr("web.config_service.get_config_service", lambda: service)
    registry = AgentRegistry(SimpleNamespace(dispatcher=SimpleNamespace()))

    with pytest.raises(OSError, match="disk full"):
        await registry.update("xiaoda", {
            "wallpaper": "/media/wallpapers/new.jpg",
            "wallpaper_focus": {"x": 0.1, "y": 0.9},
            "wallpaper_overlay": 0.6,
            "wallpaper_motion": "none",
        })

    assert {
        key: agent_registry.MAIN_AGENT_META[key]
        for key in original
    } == original

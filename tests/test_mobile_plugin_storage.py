from __future__ import annotations

from pathlib import Path

import pytest

from market.installer import MarketInstaller
from plugins.discovery import discover_plugins
from plugins.manager import PluginManager, PluginState
from tool_engine import tool_registry


PLUGIN_YAML = """id: mobile-local-plugin
name: Mobile Local Plugin
version: 1.0.0
entrypoint: mobile_local_plugin:MobileLocalPlugin
description: local test plugin
capabilities:
  tools:
    - name: mobile_local_echo
      description: local echo
"""

PLUGIN_PY = """from plugins.sdk import Plugin, register_tool

class MobileLocalPlugin(Plugin):
    @register_tool("mobile_local_echo", description="local echo")
    async def echo(self, text: str = "") -> str:
        return "mobile-local:" + text
"""


@pytest.fixture
def private_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import config

    install_dir = tmp_path / "private-plugins"
    config_dir = tmp_path / "plugin-config"
    monkeypatch.setattr(config, "PLUGINS_INSTALL_DIR", install_dir)
    monkeypatch.setattr(config, "PLUGINS_CONFIG_DIR", config_dir)
    plugin_dir = install_dir / "mobile-local-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(PLUGIN_YAML, encoding="utf-8")
    (plugin_dir / "mobile_local_plugin.py").write_text(PLUGIN_PY, encoding="utf-8")
    yield plugin_dir
    tool_registry.unregister_tool("mobile-local-plugin__mobile_local_echo")


def test_default_discovery_scans_private_install_dir(private_plugin: Path) -> None:
    discovered = discover_plugins()
    match = next(item for item in discovered if item.manifest.id == "mobile-local-plugin")
    assert match.plugin_dir == private_plugin


@pytest.mark.asyncio
async def test_private_plugin_lifecycle_tool_and_config_persist(private_plugin: Path) -> None:
    import config

    manager = PluginManager(tool_registry=tool_registry)
    assert "mobile-local-plugin" in manager.discover()
    assert await manager.load("mobile-local-plugin")
    assert await manager.enable("mobile-local-plugin")
    assert manager.get_plugin("mobile-local-plugin").state == PluginState.ENABLED

    tool = tool_registry.get_tool("mobile-local-plugin__mobile_local_echo")
    assert tool is not None
    result = await tool["func"](text="phone")
    assert result == "mobile-local:phone"

    manager.set_plugin_config("mobile-local-plugin", {"language": "zh-CN"})
    config_file = config.PLUGINS_CONFIG_DIR / "mobile-local-plugin" / "config.json"
    assert config_file.is_file()
    assert manager.get_plugin_config("mobile-local-plugin") == {"language": "zh-CN"}
    assert manager._trust_store_file == config.PLUGINS_CONFIG_DIR / "trust_store.json"
    assert manager._trust_store_file.is_file()

    assert await manager.disable("mobile-local-plugin")
    assert tool_registry.get_tool("mobile-local-plugin__mobile_local_echo") is None
    assert await manager.unload("mobile-local-plugin")


@pytest.mark.asyncio
async def test_installer_verifies_entrypoint_from_private_directory(private_plugin: Path) -> None:
    manager = PluginManager()
    manager.discover()
    installer = MarketInstaller(private_plugin.parent, private_plugin.parent / "skills", manager)
    result = await installer._verify_plugin("mobile-local-plugin", private_plugin)
    assert result["ok"] is True
    checks = {item["name"]: item["status"] for item in result["checks"]}
    assert checks["plugin.yaml"] == "ok"
    assert checks["entry_module"] == "ok"
    assert checks["registered"] == "ok"

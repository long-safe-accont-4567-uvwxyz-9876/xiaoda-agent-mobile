"""插件发现机制"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from plugins.manifest import PluginManifest, parse_manifest


@dataclass
class DiscoveredPlugin:
    manifest: PluginManifest
    plugin_dir: Path
    yaml_path: Path


def discover_plugins(search_paths: list[str | Path] | None = None) -> list[DiscoveredPlugin]:
    """扫描目录发现插件"""
    if search_paths is None:
        search_paths = [Path(__file__).parent]
        try:
            from config import PLUGINS_INSTALL_DIR
            search_paths.append(PLUGINS_INSTALL_DIR)
        except ImportError:
            logger.debug("plugin.private_install_dir_unavailable", exc_info=True)

    results: list[DiscoveredPlugin] = []
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    for search_path in search_paths:
        sp = Path(search_path).expanduser()
        try:
            resolved = sp.resolve()
        except OSError:
            resolved = sp.absolute()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        if not sp.is_dir():
            continue
        for child in sorted(sp.iterdir()):
            if not child.is_dir():
                continue
            yaml_path = child / "plugin.yaml"
            if not yaml_path.is_file():
                continue
            try:
                manifest = parse_manifest(yaml_path)
                if manifest.id in seen_ids:
                    logger.warning("plugin.duplicate_id_ignored", id=manifest.id, path=str(child))
                    continue
                seen_ids.add(manifest.id)
                results.append(DiscoveredPlugin(
                    manifest=manifest,
                    plugin_dir=child,
                    yaml_path=yaml_path,
                ))
                logger.info("plugin.discovered", id=manifest.id, path=str(child))
            except Exception as e:
                logger.warning("plugin.manifest_invalid", path=str(yaml_path), error=str(e))
    return results

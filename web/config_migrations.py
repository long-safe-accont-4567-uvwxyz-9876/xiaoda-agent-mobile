from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from utils.atomic_write import atomic_write

RETIRED_PROVIDER_ID = "ollama"


@dataclass(frozen=True)
class MigrationResult:
    changed: bool
    replacement_provider: str | None
    backup_path: Path | None


def _replacement_provider(providers: dict) -> tuple[str, str] | None:
    candidates = []
    for provider_id, record in providers.items():
        if provider_id == RETIRED_PROVIDER_ID or not isinstance(record, dict):
            continue
        model = record.get("default_model")
        if record.get("enabled", True) and isinstance(model, str) and model.strip():
            candidates.append((provider_id, model.strip()))
    return candidates[0] if len(candidates) == 1 else None


def _migrate_data(data: dict) -> tuple[dict, str | None, bool]:
    migrated = copy.deepcopy(data)
    models = migrated.setdefault("models", {})
    providers = models.setdefault("providers", {})
    retired_provider = providers.pop(RETIRED_PROVIDER_ID, None)
    replacement = _replacement_provider(providers)
    affected = retired_provider is not None

    chat_model = models.get("chat_model")
    if isinstance(chat_model, dict) and chat_model.get("provider") == RETIRED_PROVIDER_ID:
        affected = True
        if replacement:
            models["chat_model"] = {
                "provider": replacement[0],
                "model_id": replacement[1],
            }
        else:
            models.pop("chat_model", None)

    routes = models.get("routes", {})
    if isinstance(routes, dict):
        for route in routes.values():
            if not isinstance(route, dict) or route.get("client") != RETIRED_PROVIDER_ID:
                continue
            affected = True
            if replacement:
                route["client"] = replacement[0]
                route["model"] = replacement[1]
            else:
                route.pop("client", None)
                route.pop("model", None)

    if affected and replacement:
        models.pop("provider_setup_required", None)
    elif affected:
        models["provider_setup_required"] = True

    if "local_deploy" in migrated:
        migrated.pop("local_deploy")
        affected = True

    return migrated, replacement[0] if replacement else None, affected


def migrate_retired_local_ai_config(
    config_path: Path,
    credentials_dir: Path,
    atomic_writer: Callable[[str | Path, str | bytes], None] = atomic_write,
    credential_remover: Callable[[Path], None] | None = None,
) -> MigrationResult:
    config_path = Path(config_path)
    credentials_dir = Path(credentials_dir)
    credential_path = credentials_dir / f"provider_{RETIRED_PROVIDER_ID}.key"
    remover = credential_remover or Path.unlink

    if not config_path.exists():
        if credential_path.exists():
            remover(credential_path)
            return MigrationResult(True, None, None)
        return MigrationResult(False, None, None)

    original = config_path.read_bytes()
    data = json.loads(original.decode("utf-8"))
    migrated, replacement_provider, changed = _migrate_data(data)
    changed = changed or credential_path.exists()
    if not changed:
        return MigrationResult(False, replacement_provider, None)

    backup_path = config_path.with_suffix(config_path.suffix + ".pre-local-ai-retirement.bak")
    atomic_writer(backup_path, original)
    content = json.dumps(migrated, ensure_ascii=False, indent=2)
    atomic_writer(config_path, content)
    try:
        if credential_path.exists():
            remover(credential_path)
    except Exception:
        atomic_writer(config_path, original)
        raise

    return MigrationResult(True, replacement_provider, backup_path)

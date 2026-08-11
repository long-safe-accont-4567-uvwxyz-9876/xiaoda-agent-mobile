"""Collect every live and persisted reference to a custom Provider."""
from __future__ import annotations

from typing import Any


class ProviderReferenceCollector:
    def __init__(self, config_service: Any, router: Any, agent_registry: Any | None = None) -> None:
        self._config = config_service
        self._router = router
        self._agents = agent_registry

    def collect(self, provider_id: str) -> dict[str, Any]:
        references: dict[tuple[str, str], dict[str, Any]] = {}

        def add(kind: str, ref_id: str, **details: Any) -> None:
            key = (kind, ref_id)
            current = references.setdefault(key, {"type": kind, "id": ref_id})
            current.update({k: v for k, v in details.items() if v not in (None, "")})

        routes = self._config.get("models.routes", {}) or {}
        if isinstance(routes, dict):
            for task, record in routes.items():
                if isinstance(record, dict) and (record.get("client") or record.get("provider")) == provider_id:
                    add("route", str(task), model=record.get("model"), source="config")

        registry = getattr(self._router, "_registry", None)
        if registry is not None and hasattr(registry, "all_tasks") and hasattr(registry, "get_task"):
            for task in registry.all_tasks():
                record = registry.get_task(task) or {}
                if (record.get("client") or record.get("provider")) == provider_id:
                    add("route", str(task), model=record.get("model"), source="runtime")

        persisted_chat = self._config.get("models.chat_model", {}) or {}
        if isinstance(persisted_chat, dict) and persisted_chat.get("provider") == provider_id:
            add("chat_model", "chat", model=persisted_chat.get("model_id"), source="config")
        getter = getattr(self._router, "get_current_chat_model", None)
        if callable(getter):
            current_chat = getter() or {}
            if current_chat.get("provider") == provider_id:
                add("chat_model", "chat", model=current_chat.get("model_id"), source="runtime")

        if self._agents is not None:
            for agent in self._agents.list():
                if isinstance(agent, dict) and agent.get("provider") == provider_id:
                    add(
                        "agent",
                        str(agent.get("name") or "unknown"),
                        label=agent.get("display_name"),
                        model=agent.get("model"),
                    )

        providers = self._config.get("models.providers", {}) or {}
        candidates = sorted(
            pid for pid, record in providers.items()
            if pid != provider_id and isinstance(record, dict) and record.get("enabled", True)
        ) if isinstance(providers, dict) else []
        values = sorted(references.values(), key=lambda item: (item["type"], item["id"]))
        operations = [
            {
                "reference_type": item["type"],
                "reference_id": item["id"],
                "action": (
                    f"PUT /api/v1/models/routes/{item['id']}" if item["type"] == "route"
                    else "POST /api/v1/models/chat-model" if item["type"] == "chat_model"
                    else f"PUT /api/v1/agents/{item['id']}"
                ),
            }
            for item in values
        ]
        return {
            "provider_id": provider_id,
            "in_use": bool(values),
            "references": values,
            "replacement_candidates": candidates,
            "migration_operations": operations,
        }

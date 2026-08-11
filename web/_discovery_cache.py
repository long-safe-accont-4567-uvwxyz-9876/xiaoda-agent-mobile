"""Per-provider model discovery cache with separate success/failure TTLs."""
from __future__ import annotations

import asyncio
import copy
import time
from typing import Any, Callable

_CACHE_TTL = 30 * 60
_FAILURE_CACHE_TTL = 45
_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_cache_lock = asyncio.Lock()


class ProviderDiscoveryCache:
    def __init__(
        self,
        *,
        success_ttl: float = _CACHE_TTL,
        failure_ttl: float = _FAILURE_CACHE_TTL,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.success_ttl = success_ttl
        self.failure_ttl = failure_ttl
        self._clock = clock
        self._entries: dict[str, dict[str, Any]] = {}

    def get(self, provider_id: str) -> dict[str, Any] | None:
        entry = self._entries.get(provider_id)
        if entry is None or entry["expires_at"] <= self._clock():
            self._entries.pop(provider_id, None)
            return None
        value = copy.deepcopy(entry["value"])
        value["cached"] = True
        return value

    def put(self, provider_id: str, value: dict[str, Any], *, success: bool) -> None:
        ttl = self.success_ttl if success else self.failure_ttl
        stored = copy.deepcopy(value)
        stored["cached"] = False
        self._entries[provider_id] = {"value": stored, "expires_at": self._clock() + ttl}

    def invalidate(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._entries.clear()
        else:
            self._entries.pop(provider_id, None)


provider_discovery_cache = ProviderDiscoveryCache()


async def invalidate_discovery_cache(provider_id: str | None = None) -> None:
    async with _cache_lock:
        provider_discovery_cache.invalidate(provider_id)
        _cache["data"] = None
        _cache["ts"] = 0.0

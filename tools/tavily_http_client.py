"""Small Tavily Search API client used when the desktop SDK isn't available.

It intentionally implements only the stable ``TavilyClient.search`` contract used by
Xiaoda. This avoids the SDK's tiktoken native dependency on Android while retaining
search depth, answer, news topic and time-window behavior.
"""
from __future__ import annotations

from typing import Any

import httpx


class TavilyHttpClient:
    def __init__(self, api_key: str, base_url: str = "https://api.tavily.com") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"api_key": self.api_key, "query": query}
        payload.update(kwargs)
        response = self._client.post(f"{self.base_url}/search", json=payload)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("Tavily returned a non-object response")
        return value

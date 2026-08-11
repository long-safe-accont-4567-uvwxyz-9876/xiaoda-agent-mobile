"""Stage-aware Provider diagnostics using the pinned safe outbound transport."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import httpx

from core.app_exception import ProtocolError
from security.safe_outbound import build_safe_http_client, prepare_provider_target
from web.provider_urls import normalize_provider_base_url


class ProviderDiagnostics:
    def __init__(
        self,
        *,
        resolver: Callable[[str], Any] = prepare_provider_target,
        client_factory: Callable[..., Any] = build_safe_http_client,
        dns_timeout: float = 5.0,
        request_timeout: float = 12.0,
        chat_timeout: float = 20.0,
    ) -> None:
        self._resolver = resolver
        self._client_factory = client_factory
        self._dns_timeout = dns_timeout
        self._request_timeout = request_timeout
        self._chat_timeout = chat_timeout

    async def run(
        self,
        record: dict[str, Any],
        api_key: str,
        *,
        model_id: str | None = None,
        include_chat: bool = True,
    ) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []
        started_total = time.monotonic()
        target = None
        client = None
        try:
            started = time.monotonic()
            try:
                target = await asyncio.wait_for(
                    asyncio.to_thread(self._resolver, record.get("base_url", "")),
                    timeout=self._dns_timeout,
                )
                stages.append(self._ok("dns", started, resolved_ips=list(getattr(target, "resolved_ips", ()))))
            except Exception as exc:
                stages.append(self._error("dns", exc, started))
                return self._result(stages, started_total)

            client = self._client_factory(
                target,
                timeout=httpx.Timeout(self._request_timeout),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            )
            headers = self._headers(record.get("format", "openai"), api_key)
            models_url = f"{normalize_provider_base_url(target.url)}/models"
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    client.get(models_url, headers=headers),
                    timeout=self._request_timeout,
                )
                stages.append(self._ok("tls", started, status_code=response.status_code))
            except Exception as exc:
                stages.append(self._error("tls", exc, started))
                return self._result(stages, started_total)

            started = time.monotonic()
            if response.status_code in {401, 403}:
                stages.append(self._error_code("auth", "AUTH_FAILED", started, retryable=False, status_code=response.status_code))
                return self._result(stages, started_total)
            if response.status_code == 429:
                stages.append(self._error_code("auth", "RATE_LIMITED", started, retryable=True, status_code=429))
                return self._result(stages, started_total)
            if response.status_code >= 500:
                stages.append(self._error_code("auth", "UPSTREAM_UNAVAILABLE", started, retryable=True, status_code=response.status_code))
                return self._result(stages, started_total)
            stages.append(self._ok("auth", started, status_code=response.status_code))

            started = time.monotonic()
            models: list[str] = []
            if response.status_code == 404:
                stages.append(self._error_code("discover", "MODEL_DISCOVERY_UNSUPPORTED", started, retryable=False, status_code=404))
            else:
                try:
                    payload = response.json()
                    raw_models = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
                    models = [str(item.get("id") if isinstance(item, dict) else item) for item in raw_models]
                    stages.append(self._ok("discover", started, model_count=len(models)))
                except (TypeError, ValueError):
                    stages.append(self._error_code("discover", "INVALID_RESPONSE", started, retryable=True))
                    return self._result(stages, started_total)

            if include_chat:
                selected_model = model_id or record.get("default_model") or (models[0] if models else "")
                if not selected_model:
                    stages.append(self._error_code("chat", "MODEL_REQUIRED", time.monotonic(), retryable=False))
                    return self._result(stages, started_total)
                started = time.monotonic()
                chat_url, payload = self._chat_request(record, selected_model)
                try:
                    chat_response = await asyncio.wait_for(
                        client.post(chat_url, headers=headers, json=payload),
                        timeout=self._chat_timeout,
                    )
                except Exception as exc:
                    stages.append(self._error("chat", exc, started))
                    return self._result(stages, started_total)
                if chat_response.status_code in {401, 403}:
                    stages.append(self._error_code("chat", "AUTH_FAILED", started, retryable=False, status_code=chat_response.status_code))
                elif chat_response.status_code == 404:
                    stages.append(self._error_code("chat", "MODEL_NOT_FOUND", started, retryable=False, status_code=404))
                elif chat_response.status_code == 429:
                    stages.append(self._error_code("chat", "RATE_LIMITED", started, retryable=True, status_code=429))
                elif chat_response.status_code >= 400:
                    stages.append(self._error_code("chat", "CHAT_PROBE_FAILED", started, retryable=chat_response.status_code >= 500, status_code=chat_response.status_code))
                else:
                    stages.append(self._ok("chat", started, status_code=chat_response.status_code, model=selected_model))
            return self._result(stages, started_total)
        finally:
            if client is not None:
                await client.aclose()

    @staticmethod
    def _headers(fmt: str, api_key: str) -> dict[str, str]:
        if fmt == "anthropic":
            return {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        return {"authorization": f"Bearer {api_key}", "content-type": "application/json"}

    @staticmethod
    def _chat_request(record: dict[str, Any], model_id: str) -> tuple[str, dict[str, Any]]:
        base = normalize_provider_base_url(record.get("base_url", ""))
        if record.get("format") == "anthropic":
            return f"{base}/messages", {"model": model_id, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
        return f"{base}/chat/completions", {"model": model_id, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}

    @staticmethod
    def _ok(stage: str, started: float, **details: Any) -> dict[str, Any]:
        return {"stage": stage, "status": "ok", "latency_ms": round((time.monotonic() - started) * 1000), **details}

    @staticmethod
    def _error_code(stage: str, code: str, started: float, *, retryable: bool, **details: Any) -> dict[str, Any]:
        return {"stage": stage, "status": "error", "code": code, "retryable": retryable, "latency_ms": round((time.monotonic() - started) * 1000), **details}

    def _error(self, stage: str, exc: Exception, started: float) -> dict[str, Any]:
        if isinstance(exc, asyncio.TimeoutError):
            return self._error_code(stage, "UPSTREAM_TIMEOUT", started, retryable=True)
        if isinstance(exc, ProtocolError):
            return self._error_code(stage, exc.code, started, retryable=exc.retryable)
        if isinstance(exc, httpx.ConnectError):
            return self._error_code(stage, "CONNECT_FAILED", started, retryable=True)
        return self._error_code(stage, "UPSTREAM_UNAVAILABLE", started, retryable=True)

    @staticmethod
    def _result(stages: list[dict[str, Any]], started: float) -> dict[str, Any]:
        return {
            "ok": all(stage["status"] == "ok" or stage.get("code") == "MODEL_DISCOVERY_UNSUPPORTED" for stage in stages),
            "stages": stages,
            "latency_ms": round((time.monotonic() - started) * 1000),
        }

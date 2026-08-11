"""自定义模型 Provider 支持（R4/R13）。

- openai 格式：AsyncOpenAI + 自定义 base_url（复用现有依赖）
- anthropic 格式：用 httpx 直连 /v1/messages 的轻量适配器，
  对外暴露与 OpenAI SDK 相同的 client.chat.completions.create() 形状，
  这样 ModelRouter 的调用点零改动即可使用。
"""
from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from typing import Any

from loguru import logger

from core.app_exception import ProtocolError
from security.safe_outbound import build_safe_http_client, prepare_provider_target
from web.provider_urls import provider_endpoint

_runtime_registration_coordinator = threading.RLock()


class _Usage(SimpleNamespace):
    def __getattr__(self, name: Any) -> None:
        return None


def _to_openai_response(content: str, model: str, input_tokens: int, output_tokens: int) -> Any:
    message = SimpleNamespace(content=content, tool_calls=None, reasoning_content=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = _Usage(prompt_tokens=input_tokens, completion_tokens=output_tokens,
                   total_tokens=input_tokens + output_tokens,
                   prompt_cache_hit_tokens=0, prompt_cache_miss_tokens=input_tokens)
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


class AnthropicCompatClient:
    """Anthropic Messages API 适配器，形状兼容 OpenAI AsyncClient。"""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com") -> None:
        self._api_key = api_key
        target = prepare_provider_target(base_url)
        self._base_url = target.url
        self._http_client = build_safe_http_client(target)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def close(self) -> None:
        await self._http_client.aclose()

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def _create(self, model: str, messages: list[dict],
                      temperature: float = 0.7, max_tokens: int = 1024,
                      stream: bool = False, **kwargs: Any) -> Any:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_messages = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            content = m.get("content")
            if isinstance(content, list):  # 剥掉 cache_control 等结构
                content = "".join(
                    c.get("text", "") for c in content if isinstance(c, dict))
            chat_messages.append({"role": "assistant" if role == "assistant" else "user",
                                  "content": content or ""})
        if not chat_messages:
            chat_messages = [{"role": "user", "content": ""}]
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_parts:
            sys_text = system_parts[0]
            if isinstance(sys_text, list):
                sys_text = "".join(c.get("text", "") for c in sys_text if isinstance(c, dict))
            payload["system"] = sys_text
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if stream:
            payload["stream"] = True
            return self._stream_response(payload, headers, model)
        resp = await self._http_client.post(
            provider_endpoint(self._base_url, "messages"),
            json=payload,
            headers=headers,
        )
        self._raise_status(resp.status_code)
        data = resp.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
        usage = data.get("usage", {})
        return _to_openai_response(text, model,
                                   usage.get("input_tokens", 0),
                                   usage.get("output_tokens", 0))

    async def _stream_response(
        self,
        payload: dict,
        headers: dict,
        model: str,
    ) -> Any:
        async with self._http_client.stream(
            "POST",
            provider_endpoint(self._base_url, "messages"),
            json=payload,
            headers=headers,
        ) as resp:
            self._raise_status(resp.status_code)
            finished = False
            async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].lstrip(" "))
                    except json.JSONDecodeError as exc:
                        raise ProtocolError(
                            "上游流式响应格式无效",
                            code="INVALID_RESPONSE",
                            stage="probe",
                            retryable=True,
                            http_status=502,
                            cause=exc,
                        ) from exc
                    event_type = event.get("type")
                    if event_type == "error":
                        raise ProtocolError(
                            "上游流式响应失败",
                            code="INVALID_RESPONSE",
                            stage="probe",
                            retryable=True,
                            http_status=502,
                        )
                    if event_type == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            yield self._stream_chunk(model, text, None)
                    elif event_type == "message_delta":
                        stop_reason = event.get("delta", {}).get("stop_reason")
                        finish_reason = (
                            "length"
                            if stop_reason == "max_tokens"
                            else "stop" if stop_reason else None
                        )
                        usage = event.get("usage") or None
                        if finish_reason or usage:
                            yield self._stream_chunk(model, None, finish_reason, usage)
                        if finish_reason:
                            finished = True
                    elif event_type == "message_stop":
                        finished = True
            if not finished:
                raise ProtocolError(
                    "上游流式响应未正常结束",
                    code="INVALID_RESPONSE",
                    stage="probe",
                    retryable=True,
                    http_status=502,
                )

    @staticmethod
    def _stream_chunk(
        model: str,
        content: str | None,
        finish_reason: str | None,
        usage: dict | None = None,
    ) -> Any:
        delta = SimpleNamespace(content=content)
        choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
        usage_obj = SimpleNamespace(**usage) if usage else None
        return SimpleNamespace(choices=[choice], usage=usage_obj, model=model)

    @staticmethod
    def _raise_status(status_code: int) -> None:
        if status_code == 200:
            return
        if status_code in {401, 403}:
            raise ProtocolError("上游认证失败", code="AUTH_FAILED", stage="auth", retryable=False, http_status=502)
        if status_code == 429:
            raise ProtocolError("上游请求受限", code="RATE_LIMITED", stage="probe", retryable=True, http_status=429)
        if status_code == 404:
            raise ProtocolError("模型不存在", code="MODEL_NOT_FOUND", stage="probe", retryable=False, http_status=404)
        raise ProtocolError("上游请求失败", code="INVALID_RESPONSE", stage="probe", retryable=status_code >= 500, http_status=502)


def build_openai_client(
    base_url: str,
    api_key: str,
    **kwargs: Any,
) -> Any:
    from openai import AsyncOpenAI
    target = prepare_provider_target(base_url)
    return AsyncOpenAI(
        api_key=api_key,
        base_url=target.url,
        http_client=build_safe_http_client(target),
        **kwargs,
    )


def build_client(fmt: str, base_url: str, api_key: str) -> Any:
    """按 format 构建客户端实例。"""
    if fmt == "anthropic":
        return AnthropicCompatClient(api_key=api_key, base_url=base_url)
    return build_openai_client(base_url, api_key)


def _close_replaced_client(client: Any) -> None:
    if client is None:
        return
    close = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if not hasattr(result, "__await__"):
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(result)
    else:
        from core.background_tasks import _spawn
        _spawn(result)


def register_into_router(router: Any, provider_id: str, fmt: str,
                         base_url: str, api_key: str) -> None:
    """把自定义 provider 客户端注册进 ModelRouter._custom_clients。"""
    with _runtime_registration_coordinator:
        if not hasattr(router, "_custom_clients"):
            router._custom_clients = {}
        old_client = router._custom_clients.get(provider_id)
        router._custom_clients[provider_id] = build_client(fmt, base_url, api_key)
    _close_replaced_client(old_client)
    logger.info("custom_provider.registered id={} format={}", provider_id, fmt)


def unregister_from_router(router: Any, provider_id: str) -> None:
    with _runtime_registration_coordinator:
        client = router._custom_clients.pop(provider_id, None) if hasattr(router, "_custom_clients") else None
    _close_replaced_client(client)

"""模型与凭证路由（R4/R13）：provider CRUD、路由表热改、凭证池状态、用量统计。"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger

# 缓存与凭证读写抽到独立模块, 避免与 web.routers.model_discovery / model_router 互相导入
from web._discovery_cache import invalidate_discovery_cache
from web._provider_keys import (
    _mask,
    load_provider_key,
)
from web.provider_urls import validate_provider_base_url
from web.routers.auth import get_current_user
from web.schemas import Envelope

router = APIRouter(tags=["models"], dependencies=[Depends(get_current_user)])
_PROVIDER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)


def _cfg(request: Request) -> Any:
    from web.config_service import get_config_service
    return get_config_service()


def _router_of(request: Request) -> Any:
    return request.app.state.core.router


def get_provider_application_service(app: Any, config_service: Any | None = None) -> Any:
    from utils.credential_pool import get_credential_pool
    from web.config_service import get_config_service
    from web.provider_application import (
        ProviderApplicationService,
        ProviderCredentialStore,
        ProviderRepository,
        ProviderRuntimeRegistry,
    )

    existing = getattr(app.state, "provider_application_service", None)
    if existing is not None:
        return existing
    service = ProviderApplicationService(
        ProviderRepository(config_service or get_config_service()),
        ProviderCredentialStore(),
        ProviderRuntimeRegistry(app.state.core.router, get_credential_pool()),
    )
    service.recover_pending_transactions()
    app.state.provider_application_service = service
    return service


def _provider_service(request: Request) -> Any:
    return get_provider_application_service(request.app, _cfg(request))


def _provider_references(request: Request, provider_id: str) -> dict[str, Any]:
    from web.provider_references import ProviderReferenceCollector

    collector = ProviderReferenceCollector(
        _cfg(request),
        _router_of(request),
        getattr(request.app.state, "agent_registry", None),
    )
    return collector.collect(provider_id)


async def _run_provider_operation(operation: Any) -> Any:
    try:
        return await operation
    except Exception as error:
        from core.app_exception import ProtocolError

        failed_stages = getattr(error, "failed_stages", ())
        raise ProtocolError(
            "provider 操作失败",
            code="PROVIDER_OPERATION_FAILED",
            stage="persist",
            retryable=False,
            http_status=500,
            details={"compensation_failed_stages": list(failed_stages)} if failed_stages else None,
            cause=error,
        ) from error


async def _audit(request: Request, action: str, detail: str) -> None:
    core = request.app.state.core
    try:
        await core.db.insert_audit_log(f"webui.models.{action}", "webui", detail)
        await core.db.commit()
    except Exception as exc:
        logger.debug("models.audit_failed: {}", exc, exc_info=True)


async def _ensure_core_initialized(request: Request) -> None:
    """Make a newly configured provider usable without restarting the app."""
    core = getattr(request.app.state, "core", None)
    if core is None or getattr(core, "_initialized", True):
        return
    logger.info("models.reinitializing_core_after_provider_change")
    await core.init(reinit=True)
    if not getattr(core, "_initialized", False):
        from core.app_exception import ProtocolError

        raise ProtocolError(
            "provider 已保存，但本地 Agent 初始化失败",
            code="AGENT_INIT_FAILED",
            stage="initialize",
            retryable=True,
            http_status=500,
        )
    try:
        from web.app_ref import get_start_services

        start_services = get_start_services()
        if start_services is not None:
            await start_services(request.app, core)
    except (ImportError, RuntimeError, OSError, AttributeError, TypeError) as exc:
        logger.warning("models.start_services_after_reinit_failed error={}", str(exc))
    registry = getattr(request.app.state, "agent_registry", None)
    if registry is not None:
        try:
            await registry.load_persisted()
        except (OSError, KeyError, ValueError, RuntimeError, TypeError) as exc:
            logger.warning("models.registry_refresh_after_reinit_failed error={}", str(exc))
    logger.info("models.core_reinitialized_after_provider_change")


async def _broadcast_changed() -> None:
    try:
        from web.ws_hub import manager
        await manager.broadcast({"type": "config_changed", "domain": "models"})
    except Exception as exc:
        logger.debug("models.broadcast_failed: {}", exc, exc_info=True)


# ── providers ────────────────────────────────────────────────────


def _provider_text(value: Any, field: str, max_length: int, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise HTTPException(400, f"{field} must be a string")
    text = value.strip()
    if len(text) > max_length:
        raise HTTPException(400, f"{field} is too long")
    return text


def _provider_id(value: Any, *, default: str = "") -> str:
    provider_id = _provider_text(value, "id", 64, default=default)
    if not provider_id or _PROVIDER_ID_PATTERN.fullmatch(provider_id) is None:
        raise HTTPException(400, "id 必须匹配 [A-Za-z0-9_-]+")
    return provider_id


def _provider_enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise HTTPException(400, "enabled must be boolean")
    return value


def _manual_models(value: Any) -> list[dict[str, str]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise HTTPException(400, "manual_models must be an array with at most 100 entries")
    result = []
    seen = set()
    for item in value:
        model_id = str(item.get("id") if isinstance(item, dict) else item).strip()
        if not model_id or len(model_id) > 200 or model_id in seen:
            continue
        category = str(item.get("category", "chat")) if isinstance(item, dict) else "chat"
        if category not in {"chat", "embedding", "image", "video", "tts"}:
            raise HTTPException(400, "invalid manual model category")
        result.append({"id": model_id, "category": category})
        seen.add(model_id)
    return result


async def _diagnose_provider(record: dict[str, Any], api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    from web.provider_diagnostics import ProviderDiagnostics

    return await ProviderDiagnostics().run(
        record, api_key,
        model_id=body.get("model_id") or record.get("default_model"),
        include_chat=body.get("include_chat", True),
    )


def list_providers_data(cfg: Any) -> list[dict]:
    out = []
    custom = cfg.get("models.providers", {}) or {}
    # 按 order 字段升序排列；未设置 order 的排在已设置之后，按字典插入顺序
    keys_order = list(custom.keys())
    sorted_custom = sorted(
        custom.items(),
        key=lambda kv: (kv[1].get("order", 9999), keys_order.index(kv[0]))
    )
    for pid, p in sorted_custom:
        key = load_provider_key(pid)
        out.append({
            "id": pid,
            "label": p.get("label", pid),
            "format": p.get("format", "openai"),
            "base_url": p.get("base_url", ""),
            "builtin": p.get("builtin", False),
            "key_masked": _mask(key) if key else "",
            "has_key": bool(key),
            "enabled": p.get("enabled", True),
            "default_model": p.get("default_model", ""),
            "manual_models": p.get("manual_models", []),
            "order": p.get("order", 9999),
        })
    return out


@router.get("/models/providers", response_model=Envelope[list[dict]])
async def list_providers(request: Request) -> Any:
    return Envelope(data=list_providers_data(_cfg(request)))


@router.post("/models/providers/diagnose", response_model=Envelope[dict])
async def diagnose_provider_candidate(body: dict, request: Request) -> Any:
    pid = _provider_id(body.get("id"), default="candidate")
    fmt = body.get("format", "openai")
    if fmt not in ("openai", "anthropic"):
        raise HTTPException(400, "format must be openai or anthropic")
    record = {
        "label": _provider_text(body.get("label"), "label", 128, default=pid) or pid,
        "format": fmt,
        "base_url": validate_provider_base_url(body.get("base_url") or ""),
        "default_model": _provider_text(body.get("default_model"), "default_model", 256),
        "manual_models": _manual_models(body.get("manual_models", [])),
        "enabled": _provider_enabled(body.get("enabled", True)),
    }
    api_key = _provider_text(body.get("api_key"), "api_key", 8192)
    if not api_key:
        raise HTTPException(400, "api_key is required for diagnostics")
    diagnostics = await _diagnose_provider(record, api_key, body)
    return Envelope(data={"normalized": dict(record, id=pid), "diagnostics": diagnostics})


@router.post("/models/providers", response_model=Envelope[dict])
async def create_provider(body: dict, request: Request) -> Any:
    pid = _provider_id(body.get("id"))
    fmt = body.get("format", "openai")
    base_url = validate_provider_base_url(body.get("base_url") or "")
    if pid in ("mimo",):
        raise HTTPException(400, "不能覆盖内置 provider")
    if fmt not in ("openai", "anthropic"):
        raise HTTPException(400, "format 必须是 openai 或 anthropic")
    # SSRF 防护：校验 URL 不指向内网/元数据服务。
    # 本地/容器内受信服务显式配置时放行。
    cfg = _cfg(request)
    if pid in (cfg.get("models.providers", {}) or {}):
        raise HTTPException(400, f"provider {pid} 已存在")
    record = {
        "label": _provider_text(body.get("label"), "label", 128, default=pid) or pid,
        "format": fmt,
        "base_url": base_url,
        "default_model": _provider_text(body.get("default_model"), "default_model", 256),
        "manual_models": _manual_models(body.get("manual_models", [])),
        "enabled": _provider_enabled(body.get("enabled", True)),
    }
    api_key = _provider_text(body.get("api_key"), "api_key", 8192)
    if not api_key:
        raise HTTPException(400, "api_key cannot be empty")
    if body.get("validate_only"):
        validated = await _provider_service(request).validate_candidate(pid, record, api_key)
        return Envelope(data={
            "validated": True, "probe_performed": False,
            "normalized": dict(validated, id=pid),
        })
    try:
        record = await _run_provider_operation(_provider_service(request).create(pid, record, api_key))
    except Exception as e:
        logger.error("provider.register_failed id={} error={}", pid, str(e))
        raise
    await _ensure_core_initialized(request)
    await _audit(request, "provider.create", pid)
    await invalidate_discovery_cache()
    await _broadcast_changed()
    return Envelope(data=dict(record, id=pid, key_masked=_mask(api_key), builtin=False))


@router.put("/models/providers/{pid}", response_model=Envelope[dict])
async def update_provider(pid: str, body: dict, request: Request) -> Any:
    cfg = _cfg(request)
    existing = cfg.get(f"models.providers.{pid}")
    if pid in ("mimo",) or not existing:
        raise HTTPException(404 if not existing else 400,
                            "内置 provider 不可修改" if existing else f"provider {pid} 不存在")
    changes = {}
    normalized_base_url = None
    if "base_url" in body and body["base_url"] is not None:
        normalized_base_url = validate_provider_base_url(str(body["base_url"]))
    if "format" in body and body["format"] not in ("openai", "anthropic"):
        raise HTTPException(400, "format 必须是 openai 或 anthropic")
    if "label" in body:
        changes["label"] = _provider_text(body.get("label"), "label", 128)
    if "format" in body and body["format"] is not None:
        changes["format"] = body["format"]
    if "default_model" in body:
        changes["default_model"] = _provider_text(body.get("default_model"), "default_model", 256)
    if "enabled" in body:
        changes["enabled"] = _provider_enabled(body.get("enabled"))
    if "manual_models" in body:
        changes["manual_models"] = _manual_models(body.get("manual_models"))
    if normalized_base_url is not None:
        changes["base_url"] = normalized_base_url
    existing_key = load_provider_key(pid)
    replacement_key = _provider_text(body.get("api_key"), "api_key", 8192) or None
    effective_key = replacement_key or existing_key
    if body.get("validate_only"):
        record = dict(existing)
        record.update(changes)
        validated = await _provider_service(request).validate_candidate(pid, record, effective_key)
        return Envelope(data={"validated": True, "probe_performed": False, "normalized": dict(validated, id=pid)})
    record = await _run_provider_operation(_provider_service(request).update(pid, changes, api_key=replacement_key))
    key = replacement_key or existing_key
    await _audit(request, "provider.update", pid)
    await invalidate_discovery_cache()
    await _broadcast_changed()
    return Envelope(data=dict(
        record, id=pid, key_masked=_mask(key), builtin=False,
        references=_provider_references(request, pid)["references"],
    ))


@router.get("/models/providers/{pid}/references", response_model=Envelope[dict])
async def provider_references(pid: str, request: Request) -> Any:
    if not _cfg(request).get(f"models.providers.{pid}"):
        raise HTTPException(404, f"provider {pid} does not exist")
    return Envelope(data=_provider_references(request, pid))


@router.delete("/models/providers/{pid}", response_model=Envelope[dict])
async def delete_provider(pid: str, request: Request) -> Any:
    if request.headers.get("X-Confirm") != "yes":
        raise HTTPException(400, "缺少 X-Confirm: yes 确认头")
    cfg = _cfg(request)
    if not cfg.get(f"models.providers.{pid}"):
        raise HTTPException(404, f"provider {pid} 不存在")
    references = _provider_references(request, pid)
    if references["in_use"]:
        from core.app_exception import ProtocolError

        raise ProtocolError(
            "provider is still referenced",
            code="PROVIDER_IN_USE",
            stage="references",
            retryable=False,
            http_status=409,
            details=references,
        )
    await _run_provider_operation(_provider_service(request).delete(pid))
    await _audit(request, "provider.delete", pid)
    await invalidate_discovery_cache()
    await _broadcast_changed()
    return Envelope(data={"deleted": pid})


@router.post("/models/providers/{pid}/test", response_model=Envelope[dict])
async def test_provider_connection(pid: str, body: dict, request: Request) -> Any:
    record = _cfg(request).get(f"models.providers.{pid}")
    if not record:
        raise HTTPException(404, f"provider {pid} does not exist")
    api_key = str(body.get("api_key") or "").strip() or load_provider_key(pid)
    if not api_key:
        raise HTTPException(400, "provider key is not configured")
    return Envelope(data=await _diagnose_provider(record, api_key, body))


@router.post("/models/providers/{pid}/discover", response_model=Envelope[dict])
async def discover_provider_models(pid: str, request: Request) -> Any:
    from web.routers.model_discovery import _discover_provider, _get_all_providers

    provider = next((item for item in _get_all_providers() if item["id"] == pid), None)
    if provider is None:
        raise HTTPException(404, f"provider {pid} does not exist")
    await invalidate_discovery_cache(pid)
    return Envelope(data=await _discover_provider(provider))


@router.post("/models/providers/{pid}/key", response_model=Envelope[dict])
async def set_provider_key(pid: str, body: dict, request: Request) -> Any:
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(400, "api_key 不能为空")
    cfg = _cfg(request)
    record = cfg.get(f"models.providers.{pid}")
    if not record:
        raise HTTPException(404, f"provider {pid} 不存在（内置 provider 的 key 走 .env）")
    await _run_provider_operation(_provider_service(request).set_key(pid, api_key))
    await _ensure_core_initialized(request)
    await _audit(request, "provider.key", pid)
    await invalidate_discovery_cache()
    await _broadcast_changed()
    return Envelope(data={"id": pid, "key_masked": _mask(api_key)})


@router.post("/models/providers/reorder", response_model=Envelope[dict])
async def reorder_providers(body: dict, request: Request) -> Any:
    order_list = body.get("order")
    if not isinstance(order_list, list):
        raise HTTPException(400, "order 必须是字符串数组")
    # 忽略 mimo（内置 provider 不可重排序）
    filtered = [pid for pid in order_list if pid != "mimo"]
    await _run_provider_operation(_provider_service(request).reorder(filtered))
    await _audit(request, "provider.reorder", json.dumps(filtered, ensure_ascii=False))
    await invalidate_discovery_cache()
    await _broadcast_changed()
    logger.info("providers.reordered count={}", len(filtered))
    return Envelope(data={"ok": True})


# ── routes（任务路由表）──────────────────────────────────────────


@router.get("/models/routes", response_model=Envelope[dict])
async def list_routes(request: Request) -> Any:
    from model_router import FALLBACK_ROUTE, ROUTE_TABLE
    routes = {}
    for task, c in ROUTE_TABLE.items():
        routes[task] = {
            "model": c.get("model", ""),
            "provider": c.get("client", "mimo"),
            "max_tokens": c.get("max_tokens", 1500),
            "thinking": bool(c.get("thinking") and c["thinking"].get("type") == "enabled"),
            "timeout": _router_of(request).TASK_TIMEOUTS.get(task),
        }
    return Envelope(data={"routes": routes, "fallback": dict(FALLBACK_ROUTE)})


@router.put("/models/routes/{task}", response_model=Envelope[dict])
async def update_route(task: str, body: dict, request: Request) -> Any:
    from model_router import ROUTE_TABLE, ModelRouter
    if task not in ROUTE_TABLE:
        raise HTTPException(404, f"未知路由任务 {task}")
    cfg = _cfg(request)
    provider = body.get("provider")
    if provider and provider not in ("mimo",) \
            and not cfg.get(f"models.providers.{provider}"):
        raise HTTPException(400, f"provider {provider} 不存在")

    router_obj = _router_of(request)
    registry = router_obj._registry  # ModelRouter.__init__ 保证 _registry 已初始化

    # CodeRabbit#5 + m8 修复：走 registry.get_task_ref 而非直接读 ROUTE_TABLE[task]，
    # 保证 replace_table 后语义一致（虽然 replace_table 已保持对象身份，仍统一入口）。
    current_entry = registry.get_task_ref(task) or {}
    model_id = str(body["model"]) if body.get("model") else current_entry.get("model", "")
    final_provider = provider or current_entry.get("client", "mimo")

    # CodeRabbit Nit: int 转换加 try/except 返回 400 而非让 ValueError 变成 500
    try:
        max_tokens = int(body["max_tokens"]) if body.get("max_tokens") else None
        timeout = int(body["timeout"]) if body.get("timeout") else None
    except (TypeError, ValueError):
        raise HTTPException(400, "max_tokens/timeout 必须为整数") from None

    # CodeRabbit#14 + C3 修复：max_tokens clamp 用 PROVIDER_MAX_TOKENS_CAP 动态裁剪，
    # 不再硬编码 32768。旧实现把 chat 路由的 131072 压到 32768，严重退化为默认值。
    # _cap_max_tokens(provider) 返回该 provider 的上限（无 cap 时返回原值），下限保留 64。
    if max_tokens is not None:
        max_tokens = max(64, ModelRouter._cap_max_tokens(max_tokens, final_provider))

    thinking = None
    if "thinking" in body:
        # CR-Major-3 修复：budget_tokens 保留原 entry 的值，不硬编码 2048。
        # 旧实现恢复时硬编码 2048，导致重启后 thinking budget 减半。
        _orig_thinking = current_entry.get("thinking") or {}
        _orig_budget = (_orig_thinking.get("budget_tokens", 4096)
                        if isinstance(_orig_thinking, dict) else 4096)
        if body["thinking"]:
            thinking = {"type": "enabled", "budget_tokens": _orig_budget}
        else:
            thinking = {"type": "disabled"}
        import structlog
        structlog.get_logger().info("route.thinking_updated", task=task, thinking=thinking)
    # Qodo#4 修复：timeout 先 clamp 再传 registry，保证运行时与持久化用同一个验证值
    if timeout is not None:
        timeout = max(5, min(timeout, 600))

    # 通过 Registry 原子化更新（内存 + 持久化，失败回滚）
    try:
        registry.update_route(
            task, model_id=model_id, provider=final_provider,
            max_tokens=max_tokens, thinking=thinking, timeout=timeout,
        )
    except KeyError as e:
        raise HTTPException(404, f"未知路由任务 {task}: {e}") from None
    except Exception as e:
        raise HTTPException(500, f"路由更新失败: {e}") from None

    # Qodo#5 修复：TASK_TIMEOUTS 在 registry 持久化成功后才修改，
    # 失败时（上面抛 HTTPException）不修改运行时 timeout，保持原值
    if timeout is not None:
        router_obj.TASK_TIMEOUTS[task] = timeout

    # 同步更新 models.chat_model，使 GET /models/chat-model 返回最新值
    if task == "chat":
        final_entry = registry.get_task_ref(task) or {}
        cfg.set("models.chat_model", {"provider": final_entry.get("client", "mimo"),
                                       "model_id": final_entry["model"]})
    await _audit(request, "route.update", json.dumps({task: body}, ensure_ascii=False))
    await _broadcast_changed()
    final_entry = registry.get_task_ref(task) or {}
    return Envelope(data={"task": task, "model": final_entry["model"],
                          "provider": final_entry.get("client", "mimo")})


@router.get("/models/chat-model", response_model=Envelope[dict])
async def get_chat_model(request: Request) -> Any:
    cfg = _cfg(request)
    # 优先从 config_service 的 models.chat_model 读取（如果存在）
    chat_model = cfg.get("models.chat_model")
    if isinstance(chat_model, dict) and chat_model.get("provider") \
            and chat_model.get("model_id"):
        return Envelope(data={"provider": chat_model["provider"],
                              "model_id": chat_model["model_id"]})
    # 否则从 model_router.ROUTE_TABLE["chat"] 读取
    from model_router import ROUTE_TABLE
    chat_route = ROUTE_TABLE.get("chat", {})
    return Envelope(data={
        "provider": chat_route.get("client", "mimo"),
        "model_id": chat_route.get("model", ""),
    })


# ── 凭证池状态 ───────────────────────────────────────────────────


@router.get("/models/credentials/status", response_model=Envelope[list[dict]])
async def credentials_status() -> Any:
    from utils.credential_pool import get_credential_pool
    pool = get_credential_pool()
    out = []
    for provider, creds in getattr(pool, "_pool", {}).items():
        for i, c in enumerate(creds):
            out.append({
                "provider": provider,
                "index": i,
                "key_masked": _mask(c.api_key),
                "state": c.state.value,
                "last_error": c.last_error,
                "use_count": c.use_count,
                "error_count": c.error_count,
                "last_used_at": c.last_used_at,
            })
    # 也包含自定义 provider 的 key 状态
    from web.config_service import get_config_service as _get_cfg
    try:
        cfg = _get_cfg()
        custom_providers = cfg.get("models.providers", {}) or {}
        for pid in custom_providers:
            try:
                key = load_provider_key(pid)
                if not key:
                    continue
                # 避免和 credential_pool 中已有的重复
                if any(o["provider"] == pid for o in out):
                    continue
                out.append({
                    "provider": pid,
                    "index": 0,
                    "key_masked": _mask(key),
                    "state": "ok",
                    "last_error": None,
                    "use_count": 0,
                    "error_count": 0,
                    "last_used_at": None,
                })
            except Exception as e:
                logger.error(f"[credentials_status] pid={pid} error: {e}")
    except Exception as e:
        logger.error(f"[credentials_status] custom providers block error: {e}")
    return Envelope(data=out)


# ── Temperature 配置 ─────────────────────────────────────────────


@router.get("/models/temperature", response_model=Envelope[dict])
async def get_temperature(request: Request) -> Any:
    """获取当前 temperature 设置（优先 webui_overrides，回退 agent.json5）。"""
    cfg = _cfg(request)
    override = cfg.get("models.temperature")
    from config import AGENT_CONFIG
    default = AGENT_CONFIG.get("model", {}).get("temperature", 0.7)
    value = override if override is not None else default
    return Envelope(data={"temperature": value, "source": "override" if override is not None else "config"})


@router.put("/models/temperature", response_model=Envelope[dict])
async def set_temperature(request: Request) -> Any:
    """设置 temperature（0.0-2.0），写入 webui_overrides.json 热生效。"""
    body = await request.json()
    value = body.get("temperature")
    if value is None or not isinstance(value, (int, float)):
        raise HTTPException(400, "temperature must be a number")
    value = round(float(value), 2)
    if not (0.0 <= value <= 2.0):
        raise HTTPException(400, "temperature must be between 0.0 and 2.0")
    cfg = _cfg(request)
    cfg.set("models.temperature", value)
    await _audit(request, "temperature.set", f"temperature={value}")
    await _broadcast_changed()
    return Envelope(data={"temperature": value})


@router.get("/models/frequency_penalty", response_model=Envelope[dict])
async def get_frequency_penalty(request: Request) -> Any:
    """获取当前 frequency_penalty 设置（优先 webui_overrides，回退默认 1.0）。"""
    cfg = _cfg(request)
    override = cfg.get("models.frequency_penalty")
    default = 1.0
    value = override if override is not None else default
    return Envelope(data={"frequency_penalty": value, "source": "override" if override is not None else "default"})


@router.put("/models/frequency_penalty", response_model=Envelope[dict])
async def set_frequency_penalty(request: Request) -> Any:
    """设置 frequency_penalty（0.0-2.0），写入 webui_overrides.json 热生效。"""
    body = await request.json()
    value = body.get("frequency_penalty")
    if value is None or not isinstance(value, (int, float)):
        raise HTTPException(400, "frequency_penalty must be a number")
    value = round(float(value), 2)
    if not (0.0 <= value <= 2.0):
        raise HTTPException(400, "frequency_penalty must be between 0.0 and 2.0")
    cfg = _cfg(request)
    cfg.set("models.frequency_penalty", value)
    await _audit(request, "frequency_penalty.set", f"frequency_penalty={value}")
    await _broadcast_changed()
    return Envelope(data={"frequency_penalty": value})


@router.get("/models/presence_penalty", response_model=Envelope[dict])
async def get_presence_penalty_api(request: Request) -> Any:
    """获取当前 presence_penalty 设置（优先 webui_overrides，回退默认 1.0）。"""
    cfg = _cfg(request)
    override = cfg.get("models.presence_penalty")
    default = 1.0
    value = override if override is not None else default
    return Envelope(data={"presence_penalty": value, "source": "override" if override is not None else "default"})


@router.put("/models/presence_penalty", response_model=Envelope[dict])
async def set_presence_penalty_api(request: Request) -> Any:
    """设置 presence_penalty（0.0-2.0），写入 webui_overrides.json 热生效。"""
    body = await request.json()
    value = body.get("presence_penalty")
    if value is None or not isinstance(value, (int, float)):
        raise HTTPException(400, "presence_penalty must be a number")
    value = round(float(value), 2)
    if not (0.0 <= value <= 2.0):
        raise HTTPException(400, "presence_penalty must be between 0.0 and 2.0")
    cfg = _cfg(request)
    cfg.set("models.presence_penalty", value)
    await _audit(request, "presence_penalty.set", f"presence_penalty={value}")
    await _broadcast_changed()
    return Envelope(data={"presence_penalty": value})


# ── 用量统计 ─────────────────────────────────────────────────────


@router.get("/models/usage", response_model=Envelope[dict])
async def usage(request: Request, days: int = Query(default=7, ge=1, le=90)) -> Any:
    core = request.app.state.core
    since = time.time() - days * 86400
    rows = await core.db.fetch_all(
        "SELECT date(created_at, 'unixepoch', 'localtime') AS day, model, "
        "SUM(prompt_tokens) AS prompt_tokens, SUM(completion_tokens) AS completion_tokens, "
        "SUM(cost_usd) AS cost_usd, COUNT(*) AS calls "
        "FROM api_usage WHERE created_at > ? GROUP BY day, model ORDER BY day",
        (since,))
    total = await core.db.fetch_one(
        "SELECT SUM(cost_usd) AS cost, SUM(prompt_tokens + completion_tokens) AS tokens, "
        "COUNT(*) AS calls FROM api_usage WHERE created_at > ?", (since,))
    return Envelope(data={"days": days, "series": rows, "total": total or {}})

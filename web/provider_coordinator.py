"""自定义 Provider 协调器（G2 重构）。

集中 provider 创建/更新的校验、连接测试、凭证持久化、路由注册，以及
启动恢复，供 web.routers.models / model_router / model_discovery / web.server
统一调用，避免校验逻辑在多处复制。

设计约束：
- 校验失败抛 ProviderValidationError(layer=..., message=...)，路由层映射为 400。
- validate_only=True 时只做校验与连接测试，不持久化、不注册、不改配置。
- 凭证写入与注册与原 _save_key_and_register 行为一致（加密存储 + 注册进 router）。
"""
from __future__ import annotations

from typing import Any, Callable

from loguru import logger


class ProviderValidationError(Exception):
    """Provider 校验失败，携带失败层信息供路由层映射 HTTP 状态码。"""

    def __init__(self, layer: str, message: str) -> None:
        super().__init__(message)
        self.layer = layer


_VALID_FORMATS = ("openai", "anthropic")


class ProviderCoordinator:
    """协调自定义 provider 的校验、持久化与注册。"""

    def __init__(self, cfg: Any = None, router: Any = None) -> None:
        self._cfg = cfg
        self._router = router

    # ── 校验 ────────────────────────────────────────────────────

    @staticmethod
    def _validate_id(pid: str) -> None:
        if not pid or not pid.replace("-", "_").isidentifier():
            raise ProviderValidationError("id", "id 必须是合法标识符（字母/数字/-/_）")

    @staticmethod
    def _validate_fields(fmt: str, base_url: str) -> None:
        if fmt not in _VALID_FORMATS:
            raise ProviderValidationError("format", "format 必须是 openai 或 anthropic")
        if not base_url.startswith(("http://", "https://")):
            raise ProviderValidationError("base_url", "base_url 必须是 http(s) URL")

    # ── 凭证与注册 ──────────────────────────────────────────────

    def _persist_and_register(self, pid: str, fmt: str,
                              base_url: str, api_key: str) -> None:
        """先注册客户端，成功后再持久化凭证（避免部分失败状态）。"""
        import contextlib
        import os
        from web._provider_keys import _get_cred_dir, _key_file, _encode_key
        from web.custom_providers import register_into_router

        _get_cred_dir().mkdir(parents=True, exist_ok=True)
        fp = _key_file(pid)
        fp.write_text(_encode_key(api_key) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(fp, 0o600)
        register_into_router(self._router, pid, fmt, base_url, api_key)

    # ── 创建 ────────────────────────────────────────────────────

    async def create(self, record: dict, api_key: str, *,
                     validate_only: bool = False,
                     candidate_validator: Callable[..., bool] | None = None) -> dict:
        pid = record.get("id", "").strip()
        fmt = record.get("format", "openai")
        base_url = (record.get("base_url") or "").strip()
        self._validate_id(pid)
        if pid in ("mimo",):
            raise ProviderValidationError("id", "不能覆盖内置 provider")
        self._validate_fields(fmt, base_url)
        if not api_key:
            raise ProviderValidationError("api_key", "api_key 不能为空")
        if pid in ((self._cfg.get("models.providers", {}) or {})):
            raise ProviderValidationError("id", f"provider {pid} 已存在")
        # SSRF / 候选校验（candidate_validator 在 models.py 中实现，会校验非本地 URL）
        if candidate_validator is not None:
            try:
                candidate_validator(True, record)
            except ValueError as reason:
                raise ProviderValidationError("ssrf", str(reason)) from None
        data = {
            "id": pid,
            "label": record.get("label", pid),
            "format": fmt,
            "base_url": base_url,
            "default_model": record.get("default_model", ""),
            "enabled": record.get("enabled", True),
        }
        if validate_only:
            return data
        try:
            self._persist_and_register(pid, fmt, base_url, api_key)
        except ProviderValidationError:
            raise
        except Exception as exc:
            logger.error("provider.register_failed id={} error={}", pid, exc)
            raise ProviderValidationError("register", f"provider 注册失败: {exc}") from None
        self._cfg.set(f"models.providers.{pid}", data)
        return data

    # ── 更新 ────────────────────────────────────────────────────

    async def update(self, pid: str, changes: dict, *, api_key: str | None = None,
                     validate_only: bool = False,
                     candidate_validator: Callable[..., bool] | None = None) -> dict:
        record = self._cfg.get(f"models.providers.{pid}")
        if not record:
            raise ProviderValidationError("id", f"provider {pid} 不存在")
        merged = dict(record)
        merged.update(changes)
        fmt = merged.get("format", "openai")
        base_url = (merged.get("base_url") or "").strip()
        self._validate_fields(fmt, base_url)
        if candidate_validator is not None:
            try:
                candidate_validator(True, merged)
            except ValueError as reason:
                raise ProviderValidationError("ssrf", str(reason)) from None
        data = {
            "id": pid,
            "label": merged.get("label", pid),
            "format": fmt,
            "base_url": base_url,
            "default_model": merged.get("default_model", ""),
            "enabled": merged.get("enabled", True),
        }
        if validate_only:
            return data
        # 持久化配置
        self._cfg.set(f"models.providers.{pid}", data)
        # 若提供新 key 则更新凭证并重注册；否则用既有 key 重注册
        from web._provider_keys import load_provider_key
        key = api_key or load_provider_key(pid)
        if key:
            try:
                self._persist_and_register(pid, fmt, base_url, key)
            except ProviderValidationError:
                raise
            except Exception as exc:
                logger.error("provider.update_register_failed id={} error={}", pid, exc)
                raise ProviderValidationError("register", f"provider 更新注册失败: {exc}") from None
        return data

    # ── 启动恢复 ────────────────────────────────────────────────

    def recover_startup(self) -> None:
        """启动时从配置恢复所有自定义 provider 到路由（幂等、best-effort）。"""
        from web._provider_keys import load_provider_key
        from web.custom_providers import register_into_router

        providers = self._cfg.get("models.providers", {}) or {}
        for pid, record in providers.items():
            try:
                api_key = load_provider_key(pid)
                if not api_key:
                    continue
                register_into_router(
                    self._router, pid,
                    record.get("format", "openai"),
                    record.get("base_url", ""),
                    api_key,
                )
            except Exception as exc:
                logger.warning("provider.recover_startup_failed id={} error={}", pid, exc)


_coordinator: ProviderCoordinator | None = None


def get_provider_coordinator(cfg: Any = None, router: Any = None) -> ProviderCoordinator:
    """获取（并缓存）ProviderCoordinator 单例。

    首次调用时绑定 cfg 与 router；后续调用传入新的 cfg/router 会刷新绑定，
    保证懒注册路径（model_router._lazy_register_provider）拿到最新上下文。
    """
    global _coordinator
    if _coordinator is None:
        _coordinator = ProviderCoordinator(cfg=cfg, router=router)
    else:
        if cfg is not None:
            _coordinator._cfg = cfg
        if router is not None:
            _coordinator._router = router
    return _coordinator

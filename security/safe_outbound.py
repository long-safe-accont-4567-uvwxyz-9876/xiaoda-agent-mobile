from __future__ import annotations

import asyncio
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from core.app_exception import ProtocolError
from security.ssrf_guard import check_ip


@dataclass(frozen=True)
class ResolvedTarget:
    url: str
    hostname: str
    port: int
    resolved_ips: tuple[str, ...]
    pinned_ip: str | None
    allowlisted: bool


def _blocked(reason: str, *, stage: str = "validate") -> ProtocolError:
    return ProtocolError(
        "安全出站策略拒绝目标",
        code="SSRF_BLOCKED",
        stage=stage,
        retryable=False,
        http_status=400,
        details={"reason": reason},
    )


def _load_hosts() -> set[str]:
    return {
        value.strip().lower().rstrip(".")
        for value in os.getenv("PROVIDER_ALLOW_HOSTS", "").split(",")
        if value.strip()
    }


def _load_ports(name: str, defaults: set[int]) -> set[int]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return defaults
    ports: set[int] = set()
    for value in raw.split(","):
        try:
            port = int(value.strip())
        except ValueError as exc:
            raise _blocked(f"{name} 配置无效") from exc
        if not 1 <= port <= 65535:
            raise _blocked(f"{name} 配置无效")
        ports.add(port)
    return ports


def _resolve_ips(hostname: str, port: int) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(
            hostname,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except (socket.gaierror, OSError) as exc:
        raise ProtocolError(
            "DNS 解析失败",
            code="DNS_FAILED",
            stage="dns",
            retryable=True,
            http_status=502,
            cause=exc,
        ) from exc
    ips: list[str] = []
    for info in infos:
        ip = info[4][0].split("%", 1)[0]
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise ProtocolError(
            "DNS 解析失败",
            code="DNS_FAILED",
            stage="dns",
            retryable=True,
            http_status=502,
        )
    return tuple(ips)


def resolve_provider_target(value: str) -> ResolvedTarget:
    target = prepare_provider_target(value)
    ips = _resolve_ips(target.hostname, target.port)
    return _validate_resolved_ips(target, ips)


def prepare_provider_target(value: str) -> ResolvedTarget:
    from web.provider_urls import normalize_provider_base_url

    normalized = normalize_provider_base_url(value)
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    scheme = parsed.scheme.lower()
    port = parsed.port or (443 if scheme == "https" else 80)
    allowlisted = hostname in _load_hosts()
    if scheme == "https":
        allowed_ports = _load_ports("PROVIDER_ALLOWED_HTTPS_PORTS", {443})
    elif allowlisted:
        allowed_ports = _load_ports("PROVIDER_ALLOWED_HTTP_PORTS", {80})
    else:
        raise _blocked("公网 Provider 仅允许 HTTPS")
    if port not in allowed_ports:
        raise _blocked("Provider 端口不在 allowlist")
    return ResolvedTarget(
        url=normalized,
        hostname=hostname,
        port=port,
        resolved_ips=(),
        pinned_ip=None,
        allowlisted=allowlisted,
    )


def _validate_resolved_ips(
    target: ResolvedTarget,
    ips: tuple[str, ...],
) -> ResolvedTarget:
    safety = [check_ip(ip) for ip in ips]
    if urlsplit(target.url).scheme == "http" and any(safe for safe, _ in safety):
        raise _blocked("明文 HTTP 仅允许显式授权的私网或回环目标")
    if not target.allowlisted:
        for safe, reason in safety:
            if not safe:
                raise _blocked(f"目标解析到危险地址: {reason}")
    return ResolvedTarget(
        url=target.url,
        hostname=target.hostname,
        port=target.port,
        resolved_ips=ips,
        pinned_ip=ips[0],
        allowlisted=target.allowlisted,
    )


class PinnedNetworkStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream: httpcore.AsyncNetworkStream, hostname: str) -> None:
        self._stream = stream
        self._hostname = hostname

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        stream = await self._stream.start_tls(
            ssl_context,
            server_hostname=self._hostname,
            timeout=timeout,
        )
        return PinnedNetworkStream(stream, self._hostname)

    def get_extra_info(self, info: str):
        return self._stream.get_extra_info(info)


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        target: ResolvedTarget,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        from httpcore._backends.auto import AutoBackend

        self._target = target
        self._backend = backend or AutoBackend()
        self._pinned_ip = target.pinned_ip

    async def _resolve_pinned_ip(self) -> str:
        if self._pinned_ip is not None:
            return self._pinned_ip
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                self._target.hostname,
                self._target.port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except (socket.gaierror, OSError) as exc:
            raise ProtocolError(
                "DNS 解析失败",
                code="DNS_FAILED",
                stage="dns",
                retryable=True,
                http_status=502,
                cause=exc,
            ) from exc
        ips = tuple(dict.fromkeys(info[4][0].split("%", 1)[0] for info in infos))
        resolved = _validate_resolved_ips(self._target, ips)
        self._pinned_ip = resolved.pinned_ip
        return self._pinned_ip

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        normalized_host = host.lower().rstrip(".")
        if normalized_host != self._target.hostname or port != self._target.port:
            raise _blocked("连接目标与已解析目标不一致", stage="connect")
        stream = await self._backend.connect_tcp(
            await self._resolve_pinned_ip(),
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        return PinnedNetworkStream(stream, self._target.hostname)

    async def connect_unix_socket(self, path: str, timeout=None, socket_options=None):
        raise _blocked("禁止 Unix socket 出站", stage="connect")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(
        self,
        target: ResolvedTarget,
        *,
        limits: httpx.Limits = httpx.Limits(),
    ) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=True, trust_env=False),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=0,
            network_backend=PinnedNetworkBackend(target),
        )


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower().rstrip("."),
        parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
    )


def build_safe_http_client(
    base_url: str | ResolvedTarget,
    *,
    timeout=None,
    limits: httpx.Limits | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    target = (
        base_url
        if isinstance(base_url, ResolvedTarget)
        else prepare_provider_target(base_url)
    )
    expected_origin = _origin(target.url)

    async def validate_request(request: httpx.Request) -> None:
        if _origin(str(request.url)) != expected_origin:
            raise _blocked("请求目标与 Provider 源不一致")
        request.headers["Host"] = request.url.netloc.decode("ascii")

    async def validate_response(response: httpx.Response) -> None:
        if not response.is_redirect:
            return
        location = response.headers.get("location")
        if location and _origin(urljoin(str(response.request.url), location)) != expected_origin:
            await response.aclose()
            raise _blocked("禁止跨主机重定向")

    selected_limits = limits or httpx.Limits()
    selected_transport = transport or PinnedAsyncHTTPTransport(
        target,
        limits=selected_limits,
    )
    return httpx.AsyncClient(
        timeout=timeout or httpx.Timeout(120.0),
        limits=selected_limits,
        transport=selected_transport,
        trust_env=False,
        follow_redirects=True,
        event_hooks={
            "request": [validate_request],
            "response": [validate_response],
        },
    )

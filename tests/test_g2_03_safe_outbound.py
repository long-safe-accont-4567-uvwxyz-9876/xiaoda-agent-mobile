import asyncio
import socket
from unittest.mock import patch

import httpx
import pytest

from core.app_exception import ProtocolError


def _addrinfo(*ips):
    def resolve(host, port, *args, **kwargs):
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                0,
                "",
                (ip, port, 0, 0) if ":" in ip else (ip, port),
            )
            for ip in ips
        ]

    return resolve


def test_public_https_target_resolves_to_immutable_pinned_ip(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        target = resolve_provider_target("https://api.example.com/v1")

    assert target.hostname == "api.example.com"
    assert target.port == 443
    assert target.pinned_ip == "93.184.216.34"
    assert target.resolved_ips == ("93.184.216.34",)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://api.example.com:22/v1",
        "https://api.example.com:8080/v1",
    ],
)
def test_public_target_rejects_disallowed_scheme_or_port(monkeypatch, url):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        with pytest.raises(ProtocolError) as caught:
            resolve_provider_target(url)

    assert caught.value.code == "SSRF_BLOCKED"
    assert caught.value.stage == "validate"


def test_private_target_requires_explicit_admin_allowlist(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("127.0.0.1")):
        with pytest.raises(ProtocolError) as caught:
            resolve_provider_target("http://localhost:8080/v1")

    assert caught.value.code == "SSRF_BLOCKED"


def test_allowlisted_private_target_is_resolved_and_pinned(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.setenv("PROVIDER_ALLOW_HOSTS", "localhost")
    monkeypatch.setenv("PROVIDER_ALLOWED_HTTP_PORTS", "8080")
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("127.0.0.1")):
        target = resolve_provider_target("http://localhost:8080/v1")

    assert target.pinned_ip == "127.0.0.1"
    assert target.allowlisted is True


def test_general_ssrf_allowlist_does_not_authorize_provider(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.setenv("SSRF_ALLOW_HOSTS", "localhost")
    monkeypatch.delenv("PROVIDER_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("127.0.0.1")):
        with pytest.raises(ProtocolError):
            resolve_provider_target("http://localhost/v1")


def test_allowlisted_public_target_cannot_use_plain_http(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.setenv("PROVIDER_ALLOW_HOSTS", "api.example.com")
    monkeypatch.setenv("PROVIDER_ALLOWED_HTTP_PORTS", "8080")
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        with pytest.raises(ProtocolError):
            resolve_provider_target("http://api.example.com:8080/v1")


def test_any_unsafe_dns_answer_blocks_public_hostname(monkeypatch):
    from security.safe_outbound import resolve_provider_target

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch(
        "security.safe_outbound.socket.getaddrinfo",
        _addrinfo("93.184.216.34", "127.0.0.1"),
    ):
        with pytest.raises(ProtocolError):
            resolve_provider_target("https://api.example.com/v1")


def test_pinned_backend_dials_ip_and_preserves_tls_hostname(monkeypatch):
    from security.safe_outbound import PinnedNetworkBackend, ResolvedTarget

    calls = []

    class Stream:
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            calls.append(("tls", server_hostname))
            return self

    class Backend:
        async def connect_tcp(self, host, port, **kwargs):
            calls.append(("tcp", host, port))
            return Stream()

        async def connect_unix_socket(self, path, **kwargs):
            raise AssertionError("unix socket must not be used")

        async def sleep(self, seconds):
            return None

    target = ResolvedTarget(
        url="https://api.example.com/v1",
        hostname="api.example.com",
        port=443,
        resolved_ips=("93.184.216.34",),
        pinned_ip="93.184.216.34",
        allowlisted=False,
    )
    backend = PinnedNetworkBackend(target, Backend())
    stream = asyncio.run(backend.connect_tcp("api.example.com", 443))
    asyncio.run(stream.start_tls(object(), server_hostname="api.example.com"))

    assert calls == [
        ("tcp", "93.184.216.34", 443),
        ("tls", "api.example.com"),
    ]


def test_safe_client_preserves_original_host_header(monkeypatch):
    from security.safe_outbound import build_safe_http_client

    seen = []

    async def handler(request):
        seen.append(request.headers["host"])
        return httpx.Response(200, json={})

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        client = build_safe_http_client(
            "https://api.example.com/v1",
            transport=httpx.MockTransport(handler),
        )

    async def request():
        async with client:
            await client.get("https://api.example.com/v1/models")

    asyncio.run(request())
    assert seen == ["api.example.com"]


def test_safe_client_rejects_cross_host_redirect(monkeypatch):
    from security.safe_outbound import build_safe_http_client

    async def handler(request):
        return httpx.Response(302, headers={"Location": "https://evil.example/v1"})

    monkeypatch.delenv("SSRF_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        client = build_safe_http_client(
            "https://api.example.com/v1",
            transport=httpx.MockTransport(handler),
        )

    async def request():
        async with client:
            await client.get("https://api.example.com/v1/models")

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(request())
    assert caught.value.code == "SSRF_BLOCKED"


def test_cross_host_redirect_closes_response_before_rejection(monkeypatch):
    from security.safe_outbound import build_safe_http_client

    closed = []

    class Response(httpx.Response):
        async def aclose(self):
            closed.append(True)
            await super().aclose()

    async def handler(request):
        return Response(302, headers={"Location": "https://evil.example/v1"})

    monkeypatch.delenv("PROVIDER_ALLOW_HOSTS", raising=False)
    with patch("security.safe_outbound.socket.getaddrinfo", _addrinfo("93.184.216.34")):
        client = build_safe_http_client(
            "https://api.example.com/v1",
            transport=httpx.MockTransport(handler),
        )

    async def request():
        async with client:
            await client.get("https://api.example.com/v1/models")

    with pytest.raises(ProtocolError):
        asyncio.run(request())
    assert closed


def test_real_tcp_request_dials_pinned_ip_without_resolving_hostname_again(monkeypatch):
    from security.safe_outbound import build_safe_http_client

    observed = {}

    async def scenario():
        async def handle(reader, writer):
            data = await reader.readuntil(b"\r\n\r\n")
            observed["request"] = data.decode("ascii")
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setenv("PROVIDER_ALLOW_HOSTS", "provider.test")
        monkeypatch.setenv("PROVIDER_ALLOWED_HTTP_PORTS", str(port))
        calls = []
        real_getaddrinfo = socket.getaddrinfo

        def resolve(host, requested_port, *args, **kwargs):
            calls.append(host)
            if host == "provider.test":
                return _addrinfo("127.0.0.1")(host, requested_port, *args, **kwargs)
            return real_getaddrinfo(host, requested_port, *args, **kwargs)

        monkeypatch.setattr("security.safe_outbound.socket.getaddrinfo", resolve)
        client = build_safe_http_client(f"http://provider.test:{port}/v1")
        async with server, client:
            response = await client.get(f"http://provider.test:{port}/v1/models")
            assert response.status_code == 200
        observed["dns_calls"] = calls

    asyncio.run(scenario())
    assert observed["dns_calls"] == ["provider.test"]
    assert "Host: provider.test:" in observed["request"]


def test_openai_client_receives_safe_http_client(monkeypatch):
    import openai

    from web.custom_providers import build_client

    built = {}

    class OpenAIClient:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", OpenAIClient)
    monkeypatch.setattr(
        "web.custom_providers.prepare_provider_target",
        lambda url: __import__(
            "security.safe_outbound", fromlist=["ResolvedTarget"]
        ).ResolvedTarget(url, "api.example.com", 443, ("93.184.216.34",), "93.184.216.34", False),
    )
    build_client("openai", "https://api.example.com/v1", "test-key")

    assert isinstance(built["http_client"], httpx.AsyncClient)
    assert built["base_url"] == "https://api.example.com/v1"


def test_provider_replacement_and_removal_close_owned_clients(monkeypatch):
    from web import custom_providers

    closed = []

    class Client:
        def __init__(self, name):
            self.name = name

        async def aclose(self):
            closed.append(self.name)

    clients = iter([Client("old"), Client("new")])
    monkeypatch.setattr(custom_providers, "build_client", lambda *args: next(clients))
    router = type("Router", (), {"_custom_clients": {}})()

    async def scenario():
        custom_providers.register_into_router(router, "custom", "openai", "https://a.test", "key")
        custom_providers.register_into_router(router, "custom", "openai", "https://a.test", "key")
        await asyncio.sleep(0)
        custom_providers.unregister_from_router(router, "custom")
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert closed == ["old", "new"]

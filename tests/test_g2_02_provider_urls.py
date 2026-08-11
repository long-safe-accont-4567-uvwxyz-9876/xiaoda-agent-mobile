import asyncio

import httpx
import pytest

from core.app_exception import ProtocolError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.example.com", "https://api.example.com/v1"),
        ("https://api.example.com/", "https://api.example.com/v1"),
        ("https://api.example.com/v1", "https://api.example.com/v1"),
        ("https://api.example.com/v1/", "https://api.example.com/v1"),
        ("https://api.example.com/gateway", "https://api.example.com/gateway/v1"),
        ("https://api.example.com/gateway/v1/", "https://api.example.com/gateway/v1"),
        ("https://[2001:db8::1]", "https://[2001:db8::1]/v1"),
        ("https://[2001:db8::1]:8443/proxy", "https://[2001:db8::1]:8443/proxy/v1"),
        ("HTTP://API.EXAMPLE.COM:8080/prefix/", "http://api.example.com:8080/prefix/v1"),
        ("https://api.example.com/a%20b", "https://api.example.com/a%20b/v1"),
    ],
)
def test_normalize_provider_base_url_table(raw, expected):
    from web.provider_urls import normalize_provider_base_url

    assert normalize_provider_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:pass@api.example.com/v1",
        "https://user%3Apass%40api.example.com/v1",
        "https://api.example.com:99999/v1",
        "https://api.example.com:0/v1",
        "https://api.example.com:-1/v1",
        "https://api.example.com:notaport/v1",
        "ftp://api.example.com/v1",
        "https://api.example.com/v1?token=secret",
        "https://api.example.com/v1#fragment",
        "https://api.example.com/%2fadmin",
        "https://api.example.com/%252fadmin",
        "https://api.example.com/%5cadmin",
        "https://api.example.com/%2e%2e/admin",
        "https://api.example.com/%252e%252e/admin",
        "https://api.example.com/v1%0d%0aX-Test:yes",
        "https://api.example.com%09.evil/v1",
        "https://api.example.com%0b.evil/v1",
        "https://api.example.com%0c.evil/v1",
        "https://api.example.com%1f.evil/v1",
        "https://api.example.com%7f.evil/v1",
        "https://api.example.com//v1",
        "https://api.example.com/../v1",
        "https://api.example.com/./v1",
    ],
)
def test_normalize_provider_base_url_rejects_ambiguous_or_dangerous_input(raw):
    from web.provider_urls import normalize_provider_base_url

    with pytest.raises(ProtocolError) as caught:
        normalize_provider_base_url(raw)

    assert caught.value.code == "INVALID_REQUEST"
    assert caught.value.stage == "validate"
    assert caught.value.retryable is False
    assert "secret" not in str(caught.value)


def test_provider_endpoint_joins_only_known_relative_paths():
    from web.provider_urls import provider_endpoint

    base = "https://api.example.com/proxy/v1/"
    assert provider_endpoint(base, "models") == "https://api.example.com/proxy/v1/models"
    assert provider_endpoint(base, "/messages") == "https://api.example.com/proxy/v1/messages"

    with pytest.raises(ProtocolError):
        provider_endpoint(base, "../admin")


def test_discover_and_openai_chat_share_normalized_api_root(monkeypatch):
    import openai

    from web import custom_providers
    from web.routers import model_discovery

    requested = []
    monkeypatch.setattr("security.ssrf_guard.validate_url", lambda url: (True, ""))
    monkeypatch.setattr(
        "security.safe_outbound.socket.getaddrinfo",
        lambda host, port, *args: [
            (2, 1, 0, "", ("93.184.216.34", port)),
        ],
    )

    async def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "security.safe_outbound.PinnedAsyncHTTPTransport",
        lambda target, limits: transport,
    )

    asyncio.run(model_discovery._fetch_openai_compatible_models(
        "custom",
        "https://api.example.com/proxy/",
        "test-key",
    ))

    built = {}

    class OpenAIClient:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(openai, "AsyncOpenAI", OpenAIClient)
    custom_providers.build_client(
        "openai",
        "https://api.example.com/proxy/",
        "test-key",
    )

    assert requested == ["https://api.example.com/proxy/v1/models"]
    assert built["base_url"] == "https://api.example.com/proxy/v1"


def test_anthropic_chat_uses_same_normalized_api_root(monkeypatch):
    from web.custom_providers import AnthropicCompatClient

    requested = []
    monkeypatch.setattr("security.ssrf_guard.validate_url", lambda url: (True, ""))
    monkeypatch.setattr(
        "security.safe_outbound.socket.getaddrinfo",
        lambda host, port, *args: [
            (2, 1, 0, "", ("93.184.216.34", port)),
        ],
    )

    async def handler(request):
        requested.append(str(request.url))
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}], "usage": {}},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    client = AnthropicCompatClient(
        "test-key",
        "https://api.example.com/proxy/",
    )
    client._http_client = real_client(transport=transport)

    asyncio.run(client._create(
        model="claude-test",
        messages=[{"role": "user", "content": "hello"}],
    ))

    assert requested == ["https://api.example.com/proxy/v1/messages"]


@pytest.mark.parametrize("provider_id", ["openrouter", "siliconflow"])
def test_special_provider_discovery_uses_configured_base_url(monkeypatch, provider_id):
    from web.routers import model_discovery

    requested = []
    monkeypatch.setattr(
        "security.safe_outbound.socket.getaddrinfo",
        lambda host, port, *args: [
            (2, 1, 0, "", ("93.184.216.34", port)),
        ],
    )

    async def handler(request):
        requested.append(str(request.url).split("?", 1)[0])
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "security.safe_outbound.PinnedAsyncHTTPTransport",
        lambda target, limits: transport,
    )
    if provider_id == "siliconflow":
        async def no_pricing():
            return None
        monkeypatch.setattr(model_discovery, "_get_siliconflow_pricing", no_pricing)

    fetch = (
        model_discovery._fetch_openrouter_models
        if provider_id == "openrouter"
        else model_discovery._fetch_siliconflow_models
    )
    asyncio.run(fetch("test-key", "https://gateway.example/prefix"))

    assert requested == ["https://gateway.example/prefix/v1/models"]


def test_runtime_registration_rejects_unsafe_legacy_config(monkeypatch):
    from security.safe_outbound import PinnedNetworkBackend, prepare_provider_target

    async def getaddrinfo(self, host, port, *args, **kwargs):
        return [
            (2, 1, 0, "", ("10.0.0.1", port)),
        ]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", getaddrinfo)
    target = prepare_provider_target("https://legacy.example/v1")
    backend = PinnedNetworkBackend(target)

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(backend.connect_tcp("legacy.example", 443))

    assert caught.value.code == "SSRF_BLOCKED"


def test_startup_restore_isolates_unsafe_legacy_provider(monkeypatch):
    from web.server import _register_all_providers

    class Config:
        def get(self, key, default=None):
            return {
                "unsafe": {
                    "format": "openai",
                    "base_url": "https://unsafe.example/v1",
                    "enabled": True,
                },
                "safe": {
                    "format": "openai",
                    "base_url": "https://safe.example/v1",
                    "enabled": True,
                },
            }

    registered = []

    def register(router, pid, fmt, base_url, key):
        if pid == "unsafe":
            raise ProtocolError(
                "base_url 安全检查失败",
                code="SSRF_BLOCKED",
                stage="validate",
                retryable=False,
                http_status=400,
            )
        registered.append(pid)

    core = type("Core", (), {"router": object()})()
    _register_all_providers(Config(), core, lambda pid: "key", register)

    assert registered == ["safe"]


def test_sub_agent_normalizes_provider_url_before_client_creation(monkeypatch):
    from agent_dispatcher import SubAgent, SubAgentConfig

    built = {}

    monkeypatch.setattr("agent_dispatcher._read_env_key", lambda name: "key")
    monkeypatch.setattr(
        "web.custom_providers.build_openai_client",
        lambda base_url, api_key: built.update(
            base_url=base_url,
            api_key=api_key,
        ),
    )
    monkeypatch.setattr(
        "web.provider_urls.validate_provider_base_url",
        lambda value: "https://gateway.example/prefix/v1",
    )
    config = SubAgentConfig(
        name="test",
        display_name="Test",
        provider="custom",
        model="model-test",
        api_key_env="CUSTOM_KEY",
        base_url="https://gateway.example/prefix",
    )
    agent = SubAgent(config, object())

    asyncio.run(agent.init())

    assert built["base_url"] == "https://gateway.example/prefix/v1"


def test_sub_agent_recovery_keeps_unsafe_url_degraded(monkeypatch):
    import agent_dispatcher
    from agent_dispatcher import SubAgent, SubAgentConfig

    monkeypatch.setattr(agent_dispatcher, "_read_env_key", lambda name: "key")
    monkeypatch.setattr(
        "web.provider_urls.validate_provider_base_url",
        lambda value: (_ for _ in ()).throw(ProtocolError(
            "base_url 安全检查失败",
            code="SSRF_BLOCKED",
            stage="validate",
            retryable=False,
            http_status=400,
        )),
    )
    config = SubAgentConfig(
        name="test",
        display_name="Test",
        provider="custom",
        model="model-test",
        api_key_env="CUSTOM_KEY",
        base_url="https://unsafe.example/v1",
    )
    agent = SubAgent(config, object())
    agent._degraded = True

    result = asyncio.run(agent.chat("hello"))

    assert agent._degraded is True
    assert agent._client is None
    assert "累了" in result


def test_refresh_all_clients_skips_unsafe_url(monkeypatch):
    import agent_dispatcher
    from agent_dispatcher import AgentDispatcher, SubAgent, SubAgentConfig

    monkeypatch.setattr(agent_dispatcher, "_read_env_key", lambda name: "key")
    monkeypatch.setattr(
        "web.provider_urls.validate_provider_base_url",
        lambda value: (_ for _ in ()).throw(ProtocolError(
            "base_url 安全检查失败",
            code="SSRF_BLOCKED",
            stage="validate",
            retryable=False,
            http_status=400,
        )),
    )
    config = SubAgentConfig(
        name="test",
        display_name="Test",
        provider="custom",
        model="model-test",
        api_key_env="CUSTOM_KEY",
        base_url="https://unsafe.example/v1",
    )
    agent = SubAgent(config, object())
    agent._degraded = True
    dispatcher = object.__new__(AgentDispatcher)
    dispatcher._agents = {"test": agent}

    assert dispatcher.refresh_all_clients() == 0
    assert agent._degraded is True
    assert agent._client is None


def test_sub_agent_reload_rejects_unsafe_url_without_mutation(monkeypatch):
    import agent_dispatcher
    from agent_dispatcher import SubAgent, SubAgentConfig

    monkeypatch.setattr(agent_dispatcher, "_read_env_key", lambda name: "key")
    monkeypatch.setattr(
        "web.provider_urls.validate_provider_base_url",
        lambda value: (_ for _ in ()).throw(ProtocolError(
            "base_url 安全检查失败",
            code="SSRF_BLOCKED",
            stage="validate",
            retryable=False,
            http_status=400,
        )),
    )
    config = SubAgentConfig(
        name="test",
        display_name="Test",
        provider="old",
        model="old-model",
        api_key_env="OLD_KEY",
        base_url="https://old.example/v1",
    )
    agent = SubAgent(config, object())

    changed = asyncio.run(agent.reload_model_config(
        "new",
        "new-model",
        "https://unsafe.example/v1",
        "NEW_KEY",
    ))

    assert changed is False
    assert agent.config.provider == "old"
    assert agent.config.model == "old-model"
    assert agent.config.base_url == "https://old.example/v1"

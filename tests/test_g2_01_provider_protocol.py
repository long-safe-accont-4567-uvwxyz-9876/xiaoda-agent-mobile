import asyncio
import socket
import ssl
from types import SimpleNamespace

import httpx
import pytest

from core.app_exception import ProtocolError
from web.routers import model_discovery


def _caused(wrapper: Exception, cause: Exception) -> Exception:
    try:
        raise wrapper from cause
    except Exception as exc:
        return exc


def test_provider_network_errors_are_classified_from_nested_causes():
    request = httpx.Request("GET", "https://provider.example/v1/models")
    cases = [
        (
            _caused(
                httpx.ConnectError("connect failed", request=request),
                socket.gaierror(socket.EAI_NONAME, "name resolution failed"),
            ),
            ("DNS_FAILED", "dns", True),
        ),
        (
            _caused(
                httpx.ConnectError("connect failed", request=request),
                ssl.SSLCertVerificationError("certificate verify failed"),
            ),
            ("TLS_FAILED", "tls", False),
        ),
        (OSError("network unreachable"), ("CONNECTION_FAILED", "connect", True)),
    ]

    for exc, expected in cases:
        error = model_discovery._protocol_error_from_exception(exc)
        assert (error.code, error.stage, error.retryable) == expected


def test_provider_tls_error_is_classified_from_httpx_wrapped_message():
    request = httpx.Request("GET", "https://provider.example/v1/models")
    exc = httpx.ConnectError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        request=request,
    )

    error = model_discovery._protocol_error_from_exception(exc)

    assert (error.code, error.stage, error.retryable) == (
        "TLS_FAILED",
        "tls",
        False,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ("AUTH_FAILED", "auth", False)),
        (403, ("AUTH_FAILED", "auth", False)),
        (404, ("MODEL_NOT_FOUND", "discover", False)),
        (429, ("RATE_LIMITED", "discover", True)),
    ],
)
def test_provider_http_statuses_have_stable_protocol(status, expected):
    request = httpx.Request("GET", "https://provider.example/v1/models")
    response = httpx.Response(status, request=request)
    exc = httpx.HTTPStatusError("upstream body secret", request=request, response=response)

    error = model_discovery._protocol_error_from_exception(exc)

    assert (error.code, error.stage, error.retryable) == expected
    assert "secret" not in error.message


def test_anthropic_discovery_uses_configured_model_without_openai_models(monkeypatch):
    providers = [{
        "id": "anthropic-custom",
        "label": "Anthropic Custom",
        "format": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "test",
        "default_model": "claude-sonnet-test",
    }]

    async def forbidden(*args, **kwargs):
        raise AssertionError("OpenAI /models must not be called")

    monkeypatch.setattr(model_discovery, "_get_all_providers", lambda: providers)
    monkeypatch.setattr(model_discovery, "_fetch_openai_compatible_models", forbidden)
    monkeypatch.setitem(model_discovery._cache, "data", None)
    monkeypatch.setitem(model_discovery._cache, "ts", 0.0)

    result = asyncio.run(model_discovery.discover_models()).data

    assert result[0]["provider"] == "anthropic-custom"
    assert [item["id"] for item in result[0]["models"]] == ["claude-sonnet-test"]


def test_anthropic_discovery_requires_a_configured_model(monkeypatch):
    providers = [{
        "id": "anthropic-custom",
        "label": "Anthropic Custom",
        "format": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key": "test",
        "default_model": "",
    }]
    monkeypatch.setattr(model_discovery, "_get_all_providers", lambda: providers)
    monkeypatch.setitem(model_discovery._cache, "data", None)
    monkeypatch.setitem(model_discovery._cache, "ts", 0.0)

    result = asyncio.run(model_discovery.discover_models()).data

    assert result[0]["models"] == []
    assert result[0]["error"] == {
        "code": "MODEL_NOT_FOUND",
        "stage": "discover",
        "retryable": False,
        "message": "Anthropic provider 未配置默认模型",
    }


def test_provider_probe_returns_structured_redacted_diagnostic(monkeypatch):
    from web import custom_providers, probes

    class Completions:
        async def create(self, **kwargs):
            raise ProtocolError(
                "上游认证失败",
                code="AUTH_FAILED",
                stage="auth",
                retryable=False,
                http_status=502,
                cause=RuntimeError("secret upstream body"),
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions()),
    )
    monkeypatch.setattr(custom_providers, "build_client", lambda *args: client)

    result = asyncio.run(probes._perform_provider_probe(
        {"format": "anthropic", "base_url": "https://provider.example"},
        "secret-key",
        "claude-test",
        0,
    ))

    assert result["ok"] is False
    assert result["code"] == "AUTH_FAILED"
    assert result["stage"] == "auth"
    assert result["retryable"] is False
    assert result["message"] == "上游认证失败"
    assert "secret" not in str(result)


def test_anthropic_adapter_redacts_non_success_response(monkeypatch):
    from web.custom_providers import AnthropicCompatClient

    class Response:
        status_code = 401
        text = "secret upstream body"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    client = AnthropicCompatClient("secret-key")

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(client._create(
            model="claude-test",
            messages=[{"role": "user", "content": "hello"}],
        ))

    assert caught.value.code == "AUTH_FAILED"
    assert "secret upstream body" not in str(caught.value)


def test_openai_discovery_executes_http_and_redacts_status_body(monkeypatch):
    async def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(401, text="secret upstream body")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "security.safe_outbound.socket.getaddrinfo",
        lambda host, port, *args: [(2, 1, 0, "", ("93.184.216.34", port))],
    )
    monkeypatch.setattr(
        "security.safe_outbound.PinnedAsyncHTTPTransport",
        lambda target, limits: transport,
    )

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(model_discovery._fetch_openai_compatible_models(
            "custom",
            "https://provider.example/v1",
            "test-key",
        ))

    assert caught.value.code == "AUTH_FAILED"
    assert "secret upstream body" not in str(caught.value)


def test_openai_discovery_classifies_malformed_json(monkeypatch):
    async def handler(request):
        return httpx.Response(200, content=b"not-json")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "security.safe_outbound.socket.getaddrinfo",
        lambda host, port, *args: [(2, 1, 0, "", ("93.184.216.34", port))],
    )
    monkeypatch.setattr(
        "security.safe_outbound.PinnedAsyncHTTPTransport",
        lambda target, limits: transport,
    )

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(model_discovery._fetch_openai_compatible_models(
            "custom",
            "https://provider.example/v1",
            "test-key",
        ))

    assert (caught.value.code, caught.value.stage) == (
        "INVALID_RESPONSE",
        "discover",
    )


def test_probe_wait_timeout_is_retryable_timeout(monkeypatch):
    from web import custom_providers, probes

    class Completions:
        async def create(self, **kwargs):
            raise TimeoutError("secret timeout body")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions()),
    )
    monkeypatch.setattr(custom_providers, "build_client", lambda *args: client)

    result = asyncio.run(probes._perform_provider_probe(
        {"format": "openai", "base_url": "https://provider.example"},
        "secret-key",
        "model-test",
        0,
    ))

    assert (result["code"], result["stage"], result["retryable"]) == (
        "TIMEOUT",
        "connect",
        True,
    )
    assert "secret" not in str(result)


def test_standard_llm_probe_redacts_router_exception(monkeypatch):
    from model_router import ROUTE_TABLE
    from web import probes

    class Router:
        async def route(self, *args, **kwargs):
            raise RuntimeError("secret upstream body")

    monkeypatch.setitem(
        ROUTE_TABLE,
        "g201-test",
        {"model": "model-test"},
    )
    core = SimpleNamespace(router=Router())

    result = asyncio.run(probes.probe_llm(core, "g201-test"))

    assert result["code"] == "INVALID_RESPONSE"
    assert result["stage"] == "probe"
    assert "secret" not in str(result)


def test_run_all_redacts_unhandled_probe_exception(monkeypatch):
    from web import probes

    async def fail(*args, **kwargs):
        raise RuntimeError("secret upstream body")

    class Database:
        def __init__(self):
            self.saved = None

        async def execute(self, query, params):
            self.saved = params

    database = Database()
    core = SimpleNamespace(db=database)
    monkeypatch.setattr(
        probes,
        "list_probe_ids",
        lambda core: [{"id": "broken", "label": "Broken"}],
    )
    monkeypatch.setattr(probes, "run_probe", fail)

    report = asyncio.run(probes.run_all(core))

    assert report["detail"][0]["code"] == "INVALID_RESPONSE"
    assert "secret" not in str(report)
    assert "secret" not in str(database.saved)


def test_anthropic_adapter_streams_openai_compatible_chunks(monkeypatch):
    from web.custom_providers import AnthropicCompatClient

    lines = [
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"草元"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"素就绪"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}',
        'data: {"type":"message_stop"}',
    ]

    class StreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return StreamResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    client = AnthropicCompatClient("secret-key")

    async def collect():
        stream = await client._create(
            model="claude-test",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        return [chunk async for chunk in stream]

    chunks = asyncio.run(collect())

    assert "".join(
        chunk.choices[0].delta.content or ""
        for chunk in chunks
    ) == "草元素就绪"
    assert chunks[-1].choices[0].finish_reason == "stop"


def test_anthropic_adapter_maps_max_tokens_to_length(monkeypatch):
    from web.custom_providers import AnthropicCompatClient

    lines = [
        'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"}}',
    ]

    class StreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return StreamResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    client = AnthropicCompatClient("secret-key")

    async def collect():
        stream = await client._create(
            model="claude-test",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        return [chunk async for chunk in stream]

    chunks = asyncio.run(collect())

    assert chunks[-1].choices[0].finish_reason == "length"


def test_model_router_catches_protocol_errors_in_retry_paths():
    from pathlib import Path

    text = Path("model_router.py").read_text(encoding="utf-8")

    assert "from core.app_exception import LLMError, ProtocolError" in text
    assert text.count("ProtocolError, httpx.TransportError) as e:") >= 2


def test_provider_probe_closes_temporary_client(monkeypatch):
    from web import custom_providers, probes

    class Completions:
        async def create(self, **kwargs):
            message = SimpleNamespace(content="草元素已就绪")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message)],
            )

    class Client:
        def __init__(self):
            self.closed = False
            self.chat = SimpleNamespace(completions=Completions())

        async def aclose(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(custom_providers, "build_client", lambda *args: client)

    result = asyncio.run(probes._perform_provider_probe(
        {"format": "openai", "base_url": "https://provider.example"},
        "secret-key",
        "model-test",
        0,
    ))

    assert result["ok"] is True
    assert client.closed is True


def test_error_classifier_respects_protocol_error_machine_fields():
    from utils.error_classifier import ErrorClassifier, FailoverReason

    cases = [
        (
            ProtocolError("认证失败", code="AUTH_FAILED", stage="auth", retryable=False, http_status=502),
            FailoverReason.AUTH_ERROR,
            False,
        ),
        (
            ProtocolError("请求受限", code="RATE_LIMITED", stage="probe", retryable=True, http_status=429),
            FailoverReason.RATE_LIMIT,
            True,
        ),
    ]

    for error, reason, retryable in cases:
        classified = ErrorClassifier().classify(error)
        assert classified.reason == reason
        assert classified.is_retryable is retryable


def test_anthropic_sse_accepts_data_without_space_and_rejects_error_event(monkeypatch):
    from web.custom_providers import AnthropicCompatClient

    streams = [
        ['data:{"type":"content_block_delta","delta":{"type":"text_delta","text":"草元素"}}',
         'data:{"type":"message_delta","delta":{"stop_reason":"end_turn"}}'],
        ['data:{"type":"error","error":{"message":"secret upstream body"}}'],
    ]

    class StreamResponse:
        status_code = 200

        def __init__(self, lines):
            self.lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            for line in self.lines:
                yield line

    class Client:
        def __init__(self, lines):
            self.lines = lines

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, *args, **kwargs):
            return StreamResponse(self.lines)

    client = AnthropicCompatClient("secret-key")

    async def collect(lines):
        client._http_client = Client(lines)
        stream = await client._create(
            model="claude-test",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
        )
        return [chunk async for chunk in stream]

    chunks = asyncio.run(collect(streams[0]))
    assert chunks[0].choices[0].delta.content == "草元素"

    with pytest.raises(ProtocolError) as caught:
        asyncio.run(collect(streams[1]))
    assert caught.value.code == "INVALID_RESPONSE"
    assert "secret" not in str(caught.value)


def test_anthropic_client_supports_router_close_contract():
    from web.custom_providers import AnthropicCompatClient

    client = AnthropicCompatClient("secret-key")

    asyncio.run(client.close())
    asyncio.run(client.aclose())

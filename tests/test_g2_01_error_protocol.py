from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from core.app_exception import AuthError, LLMError, NetworkError, ProtocolError
from core.error_codes import ErrorCodeEnum
from web.error_handler import _ERROR_PROTOCOL, register_error_handlers


class Payload(BaseModel):
    name: str


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/http/{kind}")
    async def raise_http(kind: str):
        cases = {
            "auth": HTTPException(401, "认证失败"),
            "ssrf": HTTPException(403, "SSRF 安全检查失败"),
            "model": HTTPException(404, "模型不存在"),
            "tls": HTTPException(502, "TLS 证书校验失败"),
        }
        raise cases[kind]

    @app.get("/app/{kind}")
    async def raise_app(kind: str):
        cases = {
            "auth": AuthError("认证失败"),
            "timeout": LLMError("上游超时", error_code=ErrorCodeEnum.E_LLM004),
            "dns": NetworkError("DNS 解析失败", error_code=ErrorCodeEnum.E_NET003),
            "rate": LLMError("请求过多", error_code=ErrorCodeEnum.E_LLM007),
        }
        raise cases[kind]

    @app.post("/validation")
    async def validate(payload: Payload):
        return payload

    @app.get("/generic")
    async def raise_generic():
        raise RuntimeError("secret upstream body")

    @app.get("/protocol")
    async def raise_protocol():
        raise ProtocolError(
            "操作失败",
            code="INVALID_RESPONSE",
            stage="discover",
            retryable=True,
            http_status=502,
        )

    return TestClient(app, raise_server_exceptions=False)


def _assert_contract(body: dict) -> None:
    assert body["ok"] is False
    assert body["data"] is None
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert body["detail"] is not None
    assert body["stage"] in {"validate", "dns", "connect", "tls", "auth", "discover", "probe"}
    assert isinstance(body["retryable"], bool)
    assert isinstance(body["trace_id"], str) and body["trace_id"]
    assert body["error"] == {"code": body["code"], "message": body["message"]}


def test_http_exception_uses_stable_compatible_contract():
    client = _client()
    expected = {
        "auth": ("AUTH_FAILED", "auth", False),
        "ssrf": ("SSRF_BLOCKED", "validate", False),
        "model": ("MODEL_NOT_FOUND", "discover", False),
        "tls": ("TLS_FAILED", "tls", False),
    }
    for kind, result in expected.items():
        response = client.get(f"/http/{kind}")
        body = response.json()
        _assert_contract(body)
        assert (body["code"], body["stage"], body["retryable"]) == result
        assert body["detail"] == body["message"]


def test_app_exception_maps_provider_failures_to_stable_contract():
    client = _client()
    expected = {
        "auth": ("AUTH_FAILED", "auth", False),
        "timeout": ("TIMEOUT", "probe", True),
        "dns": ("DNS_FAILED", "dns", True),
        "rate": ("RATE_LIMITED", "probe", True),
    }
    for kind, result in expected.items():
        body = client.get(f"/app/{kind}").json()
        _assert_contract(body)
        assert (body["code"], body["stage"], body["retryable"]) == result
        assert body["error_code"].startswith("E_")


def test_validation_error_preserves_detail_and_adds_top_level_message():
    response = _client().post("/validation", json={})
    body = response.json()
    assert response.status_code == 422
    _assert_contract(body)
    assert body["code"] == "INVALID_REQUEST"
    assert body["stage"] == "validate"
    assert isinstance(body["detail"], list)


def test_unhandled_error_is_redacted_and_correlated():
    body = _client().get("/generic").json()
    _assert_contract(body)
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message"] == "内部错误"
    assert "secret upstream body" not in str(body)


def test_protocol_error_preserves_explicit_machine_contract():
    response = _client().get("/protocol")
    body = response.json()
    assert response.status_code == 502
    assert (body["code"], body["stage"], body["retryable"]) == (
        "INVALID_RESPONSE",
        "discover",
        True,
    )


def test_http_status_precedes_ambiguous_human_message():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ambiguous")
    async def ambiguous():
        raise HTTPException(401, "model credential expired")

    body = TestClient(app).get("/ambiguous").json()
    assert (body["code"], body["stage"]) == ("AUTH_FAILED", "auth")


def test_every_internal_error_code_has_public_protocol_mapping():
    assert set(_ERROR_PROTOCOL) == set(ErrorCodeEnum)


def test_routes_do_not_return_failed_envelopes():
    from pathlib import Path

    routers = Path("web/routers")
    offenders = []
    for path in routers.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "Envelope(ok=False" in text or "ok=False," in text:
            offenders.append(path.name)
    assert offenders == []


def test_provider_discovery_returns_per_provider_structured_failures(monkeypatch):
    import asyncio

    from web.routers import model_discovery

    providers = [{
        "id": "broken",
        "label": "Broken",
        "base_url": "https://broken.example/v1",
        "api_key": "test",
    }]

    async def fail(*args, **kwargs):
        raise ProtocolError(
            "DNS 解析失败",
            code="DNS_FAILED",
            stage="dns",
            retryable=True,
            http_status=502,
        )

    monkeypatch.setattr(model_discovery, "_get_all_providers", lambda: providers)
    monkeypatch.setattr(model_discovery, "_fetch_openai_compatible_models", fail)
    monkeypatch.setitem(model_discovery._cache, "data", None)
    monkeypatch.setitem(model_discovery._cache, "ts", 0.0)

    envelope = asyncio.run(model_discovery.discover_models())
    assert len(envelope.data) == 1
    item = envelope.data[0]
    assert item["provider"] == "broken"
    assert item["label"] == "Broken"
    assert item["models"] == []
    assert item["status"] == "error"
    assert item["stage"] == "dns"
    assert item["error"]["code"] == "DNS_FAILED"
    assert item["error"]["stage"] == "dns"
    assert item["error"]["retryable"] is True
    assert item["error"]["message"]


def test_trace_id_matches_response_header_in_real_middleware_path(monkeypatch, tmp_path):
    from web.server import create_app

    monkeypatch.setenv("XIAODA_DATA_DIR", str(tmp_path))
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/sessions")

    assert response.status_code == 401
    assert response.json()["trace_id"] == response.headers["X-Trace-Id"]

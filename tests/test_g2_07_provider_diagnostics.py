from __future__ import annotations

import asyncio

import httpx

from web.provider_diagnostics import ProviderDiagnostics


class FakeTarget:
    url = 'https://api.example.com/v1'
    hostname = 'api.example.com'
    resolved_ips = ('203.0.113.10',)


class FakeClient:
    opened = 0
    closed = 0

    def __init__(self, status=200):
        self.status = status
        FakeClient.opened += 1

    async def get(self, url, headers=None):
        request = httpx.Request('GET', url)
        return httpx.Response(self.status, request=request, json={'data': [{'id': 'chat-1'}]})

    async def post(self, url, headers=None, json=None):
        request = httpx.Request('POST', url)
        return httpx.Response(self.status, request=request, json={'choices': [{'message': {'content': 'ok'}}]})

    async def aclose(self):
        FakeClient.closed += 1


def test_diagnostics_reports_all_stages_and_closes_temporary_client():
    FakeClient.opened = FakeClient.closed = 0
    diagnostics = ProviderDiagnostics(
        resolver=lambda _url: FakeTarget(),
        client_factory=lambda _target, **_kwargs: FakeClient(),
    )

    result = asyncio.run(diagnostics.run(
        {'base_url': FakeTarget.url, 'format': 'openai', 'default_model': 'chat-1'},
        'secret-key',
    ))

    assert result['ok'] is True
    assert [stage['stage'] for stage in result['stages']] == ['dns', 'tls', 'auth', 'discover', 'chat']
    assert FakeClient.opened == FakeClient.closed == 1
    assert 'secret-key' not in str(result)


def test_auth_failure_does_not_include_upstream_body():
    diagnostics = ProviderDiagnostics(
        resolver=lambda _url: FakeTarget(),
        client_factory=lambda _target, **_kwargs: FakeClient(status=401),
    )

    result = asyncio.run(diagnostics.run({'base_url': FakeTarget.url, 'format': 'openai'}, 'secret'))

    assert result['ok'] is False
    failed = next(stage for stage in result['stages'] if stage['status'] == 'error')
    assert failed['stage'] == 'auth'
    assert failed['code'] == 'AUTH_FAILED'
    assert 'body' not in failed


def test_one_hundred_probes_release_every_client():
    FakeClient.opened = FakeClient.closed = 0
    diagnostics = ProviderDiagnostics(
        resolver=lambda _url: FakeTarget(),
        client_factory=lambda _target, **_kwargs: FakeClient(),
    )

    async def run_many():
        for _ in range(100):
            result = await diagnostics.run({'base_url': FakeTarget.url, 'format': 'openai'}, 'secret', include_chat=False)
            assert result['ok']

    asyncio.run(run_many())
    assert FakeClient.opened == FakeClient.closed == 100

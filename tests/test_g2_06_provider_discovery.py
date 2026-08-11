from __future__ import annotations

from web._discovery_cache import ProviderDiscoveryCache
from web.routers import models as models_router
from web.routers.model_discovery import _enrich_models, _merge_manual_models


def test_provider_cache_uses_different_success_and_failure_ttl():
    now = [100.0]
    cache = ProviderDiscoveryCache(success_ttl=1800, failure_ttl=45, clock=lambda: now[0])
    cache.put('ok', {'status': 'ok'}, success=True)
    cache.put('bad', {'status': 'error'}, success=False)

    now[0] += 46
    assert cache.get('ok') == {'status': 'ok', 'cached': True}
    assert cache.get('bad') is None


def test_manual_models_survive_missing_models_endpoint_and_are_user_sourced():
    models = _merge_manual_models([], ['chat-manual', 'embed-manual'])
    enriched = _enrich_models(models)

    assert [model['id'] for model in enriched] == ['chat-manual', 'embed-manual']
    assert enriched[0]['category'] == 'chat'
    assert enriched[1]['category'] == 'embedding'
    assert all(model['capability_source'] == 'user' for model in enriched)


def test_discovered_non_chat_models_are_classified_with_evidence_source():
    models = _enrich_models([
        {'id': 'text-embedding-3-small'},
        {'id': 'image-gen-v2', 'capabilities': ['image']},
        {'id': 'voice-tts-1'},
        {'id': 'video-pro-1'},
    ])

    assert [model['category'] for model in models] == ['embedding', 'image', 'tts', 'video']
    assert models[0]['capability_source'] == 'inferred'
    assert models[1]['capability_source'] == 'declared'

def test_provider_list_keeps_disabled_or_keyless_manual_provider(monkeypatch):
    class Config:
        def get(self, path, default=None):
            if path == 'models.providers':
                return {
                    'manual-only': {
                        'label': 'Manual only',
                        'format': 'openai',
                        'base_url': 'https://provider.example/v1',
                        'enabled': False,
                        'manual_models': ['chat-manual'],
                    }
                }
            return default

    monkeypatch.setattr(models_router, 'load_provider_key', lambda provider_id: None)

    providers = models_router.list_providers_data(Config())

    assert providers == [
        {
            'id': 'manual-only',
            'label': 'Manual only',
            'format': 'openai',
            'base_url': 'https://provider.example/v1',
            'builtin': False,
            'key_masked': '',
            'has_key': False,
            'enabled': False,
            'default_model': '',
            'manual_models': ['chat-manual'],
            'order': 9999,
        }
    ]

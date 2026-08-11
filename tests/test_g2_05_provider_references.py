from __future__ import annotations

from types import SimpleNamespace

from web.provider_references import ProviderReferenceCollector


class ConfigStub:
    def __init__(self, data):
        self.data = data

    def get(self, path, default=None):
        node = self.data
        for part in path.split('.'):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


class RouteRegistryStub:
    def __init__(self, routes):
        self.routes = routes

    def all_tasks(self):
        return list(self.routes)

    def get_task(self, task):
        return self.routes.get(task)


class RouterStub:
    def __init__(self):
        self._registry = RouteRegistryStub({
            'chat': {'client': 'acme', 'model': 'chat-1'},
            'memory': {'client': 'other', 'model': 'embed-1'},
        })

    def get_current_chat_model(self):
        return {'provider': 'acme', 'model_id': 'chat-1'}


class AgentRegistryStub:
    def list(self):
        return [
            {'name': 'xiaoda', 'display_name': 'Xiaoda', 'provider': 'acme', 'model': 'chat-1'},
            {'name': 'research', 'display_name': 'Research', 'provider': 'other', 'model': 'r1'},
        ]


def test_collects_route_chat_model_and_agent_references_without_duplicates():
    config = ConfigStub({
        'models': {
            'routes': {
                'chat': {'client': 'acme', 'model': 'chat-1'},
                'vision': {'provider': 'acme', 'model': 'vision-1'},
            },
            'chat_model': {'provider': 'acme', 'model_id': 'chat-1'},
            'providers': {'acme': {}, 'other': {}},
        }
    })
    collector = ProviderReferenceCollector(config, RouterStub(), AgentRegistryStub())

    result = collector.collect('acme')

    assert result['in_use'] is True
    assert {(item['type'], item['id']) for item in result['references']} == {
        ('route', 'chat'), ('route', 'vision'), ('chat_model', 'chat'), ('agent', 'xiaoda'),
    }
    assert result['replacement_candidates'] == ['other']
    assert {item['action'] for item in result['migration_operations']} == {
        'PUT /api/v1/models/routes/chat', 'PUT /api/v1/models/routes/vision',
        'POST /api/v1/models/chat-model', 'PUT /api/v1/agents/xiaoda',
    }


def test_empty_provider_has_no_references():
    collector = ProviderReferenceCollector(
        ConfigStub({'models': {'providers': {'acme': {}, 'other': {}}}}),
        SimpleNamespace(),
        AgentRegistryStub(),
    )

    result = collector.collect('missing')

    assert result['in_use'] is False
    assert result['references'] == []

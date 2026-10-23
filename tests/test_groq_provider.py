"""Offline tests of API adapter, no tokens or key required."""
import json
from types import SimpleNamespace
from src.agents.planner import plan_document, _resolve_provider_model

PAYLOAD = {'metadata': {'title': 'Тест'}, 'sections': [{'id': '1', 'title': 'Раздел', 'level': 1, 'blocks': []}]}

class StubGroq:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(self.replies)))])


def test_groq_model_ids():
    for model in ['groq/openai/gpt-oss-120b','groq/openai/gpt-oss-20b','groq/qwen/qwen3.8-27b']:
        assert _resolve_provider_model('groq', model) == ('groq', model[5:])


def test_groq_compiles_ast_and_requests_json():
    client = StubGroq([json.dumps(PAYLOAD)])
    ast = plan_document('Сделай тест', provider='groq', model='groq/openai/gpt-oss-120b', client=client)
    assert ast.metadata.title == 'Тест'
    assert client.requests[0]['model'] == 'openai/gpt-oss-120b'
    assert client.requests[0]['response_format'] == {'type': 'json_object'}


def test_groq_repair_retry():
    client = StubGroq(['{}', json.dumps(PAYLOAD)])
    result = plan_document('Тест', provider='groq', model='openai/gpt-oss-20b', client=client)
    assert result.metadata.title == 'Тест'
    assert len(client.requests) == 2
    assert 'Исправь JSON' in client.requests[1]['messages'][-1]['content']

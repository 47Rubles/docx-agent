"""Устойчивость planner'а к вариантам ответа модели.

Модель (особенно reasoning-модели Groq) отвечает на один и тот же промпт
неодинаково: то корректным объектом, то массивом с одним объектом, то с
мелкими нарушениями схемы. Планировщик обязан это переживать, а не падать.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.planner import (
    _create_with_retry,
    _describe_errors,
    _json_generation_failure,
    _strip_fences,
    _unwrap_document,
)
from src.models.ast_schema import DocumentAST

VALID_DOCUMENT = {
    'metadata': {'title': 'Отчёт', 'author': 'AI Assistant'},
    'sections': [
        {
            'id': 'sec1',
            'title': '1. Введение',
            'level': 1,
            'blocks': [{'type': 'paragraph', 'text': 'Текст раздела'}],
        }
    ],
}


def test_unwrap_accepts_plain_object():
    assert _unwrap_document(VALID_DOCUMENT) is VALID_DOCUMENT


def test_unwrap_accepts_single_element_array():
    assert _unwrap_document([VALID_DOCUMENT]) == VALID_DOCUMENT


def test_unwrap_picks_document_out_of_mixed_list():
    assert _unwrap_document([{'note': 'лишнее'}, VALID_DOCUMENT]) == VALID_DOCUMENT


def test_unwrap_rejects_shapes_that_are_not_documents():
    with pytest.raises(ValueError):
        _unwrap_document(['просто строка'])
    with pytest.raises(ValueError):
        _unwrap_document(42)


def test_unwrap_result_validates():
    document = DocumentAST.model_validate(_unwrap_document([VALID_DOCUMENT]))
    assert document.metadata.title == 'Отчёт'
    assert len(document.sections) == 1


def test_describe_errors_has_no_input_dump():
    broken = {'metadata': {'title': 'Отчёт'}, 'sections': [{'title': 'без id'}]}
    with pytest.raises(ValidationError) as excinfo:
        DocumentAST.model_validate(broken)
    description = _describe_errors(excinfo.value)
    # Модель не должна получать обрезанный дамп входных данных: она начинает
    # его цитировать вместо починки структуры.
    assert 'input_value' not in description
    assert 'sections' in description


def test_strip_fences_removes_markdown_wrapper():
    assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


class FakeHttpError(Exception):
    """Имитация ошибки OpenAI SDK: несёт HTTP-статус."""

    def __init__(self, status_code: int):
        super().__init__(f'HTTP {status_code}')
        self.status_code = status_code


def test_retry_on_rate_limit():
    """429 — инфраструктурная ошибка: повторяем тот же запрос."""
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise FakeHttpError(429)
        return 'ok'

    assert _create_with_retry(flaky, attempts=4, base_delay=0.01) == 'ok'
    assert len(calls) == 3


def test_retry_on_server_error():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise FakeHttpError(503)
        return 'ok'

    assert _create_with_retry(flaky, attempts=3, base_delay=0.01) == 'ok'
    assert len(calls) == 2


def test_no_retry_on_client_error():
    calls = []

    def bad():
        calls.append(1)
        raise FakeHttpError(400)

    with pytest.raises(FakeHttpError):
        _create_with_retry(bad, attempts=3, base_delay=0.01)
    assert len(calls) == 1


def test_retry_gives_up_after_last_attempt():
    calls = []

    def always_rate_limited():
        calls.append(1)
        raise FakeHttpError(429)

    with pytest.raises(FakeHttpError):
        _create_with_retry(always_rate_limited, attempts=2, base_delay=0.01)
    assert len(calls) == 2


def test_daily_quota_is_not_retried():
    """Суточная квота не лечится повтором — нужен понятный отказ."""
    calls = []

    class DailyQuotaError(Exception):
        status_code = 429
        body = {'error': {'message': 'Rate limit reached ... on tokens per day (TPD)'}}

    def exhausted():
        calls.append(1)
        raise DailyQuotaError()

    with pytest.raises(ValueError) as excinfo:
        _create_with_retry(exhausted, attempts=3, base_delay=0.01)
    assert 'квота' in str(excinfo.value)
    assert len(calls) == 1


class FakeBadRequest(Exception):
    """Имитация 400 от провайдера: тело ошибки приходит в .body."""

    def __init__(self, body, code=None):
        super().__init__('bad request')
        self.body = body
        self.code = code


def test_json_generation_failure_extracts_partial_output():
    """Тело ошибки может быть плоским (как в openai SDK 2.x) или вложенным."""
    flat = FakeBadRequest(
        {'message': 'Failed to generate JSON', 'code': 'json_validate_failed',
         'failed_generation': '{"metadata":{"title":"x"'},
        code='json_validate_failed',
    )
    assert _json_generation_failure(flat) == '{"metadata":{"title":"x"'

    nested = FakeBadRequest({
        'error': {
            'code': 'json_validate_failed',
            'failed_generation': '{"metadata":{"title":"y"',
        }
    })
    assert _json_generation_failure(nested) == '{"metadata":{"title":"y"'


def test_json_generation_failure_ignores_other_errors():
    exc = FakeBadRequest({'error': {'code': 'rate_limit_exceeded'}})
    assert _json_generation_failure(exc) is None
    assert _json_generation_failure(ValueError('обычная ошибка')) is None

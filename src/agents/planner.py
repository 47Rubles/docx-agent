"""LLM-to-validated-AST adapter for Anthropic and Groq."""
import json
import time
from typing import Any

from pydantic import ValidationError
from src.config import (
    DEFAULT_MODELS,
    GROQ_BASE_URL,
    MAX_AST_REPAIR_ATTEMPTS,
    MAX_OUTPUT_TOKENS,
    MAX_TOKENS,
    MODEL,
    PROVIDER,
    resolve_api_key,
)
from src.core.ast_normalizer import normalize_document
from src.models.ast_schema import DocumentAST

SYSTEM = '''Ты — архитектор технической документации. Верни ТОЛЬКО JSON DocumentAST без markdown.
Верни РОВНО ОДИН JSON-объект верхнего уровня (не массив, не список объектов, не два документа).
Корень: {"metadata":{"title":"...","author":"...","enable_toc":true,"enable_track_changes":false},"sections":[...]}
Секции: {"id":"unique","title":"1. ...","level":1..3,"blocks":[...]}
Блоки: {"type":"paragraph","text":"...","runs":[{"text":"...","bold":false,"italic":false,"code":false}]}, {"type":"formula","latex":"E=mc^2","display_mode":"block"}, {"type":"table","headers":["..."],"rows":[[{"text":"...","align":"left","col_span":1,"row_span":1}]],"col_widths":[100]}, {"type":"callout","callout_type":"info","title":"...","text":"..."}.
Для таблиц процентные ширины в сумме 100. Не придумывай неподтвержденные факты. Разделы не глубже Heading 3.
ОБЪЁМ: не более 5 разделов, в каждом не более 3 блоков, абзац — до 3 предложений, максимум одна таблица или формула на раздел. Ответ должен уместиться в один JSON: не обрывай его на середине.'''

GROQ_MODELS = ('openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3.8-27b')


def _resolve_provider_model(provider, model):
    provider = (provider or PROVIDER).lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f'Unknown LLM provider: {provider}. Use anthropic or groq.')
    selected = model or (MODEL if provider == PROVIDER else DEFAULT_MODELS[provider])
    if provider == 'groq' and selected.startswith('groq/'):
        selected = selected[len('groq/'):]
    return provider, selected


def _strip_fences(raw):
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return raw


def _unwrap_document(payload):
    """Принимает ответ модели в виде объекта либо массива с одним объектом.

    Reasoning-модели периодически заворачивают документ в массив — это не
    ошибка модели, а форма ответа, которую нужно корректно разобрать.
    """
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        documents = [item for item in payload if isinstance(item, dict)]
        for candidate in documents:
            if 'metadata' in candidate or 'sections' in candidate:
                return candidate
        if len(documents) == 1:
            return documents[0]
    raise ValueError(
        'Ожидался JSON-объект DocumentAST, получен тип '
        f'{type(payload).__name__}. Верни один объект, не массив.'
    )


def _describe_errors(exc: ValidationError) -> str:
    """Краткое описание ошибок схемы без дампа входных данных.

    Полный текст Pydantic содержит обрезанный JSON («input_value=…»), и модель
    начинает его цитировать вместо того, чтобы починить структуру. Поэтому
    отдаём только места и описания проблем.
    """
    problems = []
    for error in exc.errors():
        location = '.'.join(str(part) for part in error.get('loc', ())) or 'корень'
        problems.append(f'- {location}: {error.get("msg", "невалидное значение")}')
    return '\n'.join(problems[:20])


def _has_structure(payload: Any) -> bool:
    """Есть ли в ответе модели разделы.

    Раздел без блоков — допустимый минимум (модель так решила), но ответ
    вовсе без разделов означает, что модель не справилась.
    """
    if not isinstance(payload, dict):
        return False
    sections = payload.get('sections')
    return isinstance(sections, list) and len(sections) > 0


def _truncation_hint(finish_reason) -> str:
    """Подсказка модели, если ответ оборвался по лимиту токенов.

    Reasoning-модель может не уложиться в лимит: токены размышления идут в
    тот же счёт, что и ответ. В этом случае чинить структуру бессмысленно —
    нужно попросить более короткий документ.
    """
    if finish_reason in ('length', 'max_tokens'):
        return (
            'Ответ обрезан по лимиту токенов. Сократи документ: '
            'не более 4 разделов, в каждом не более 4 блоков, '
            'формулы и таблицы — только самые важные.'
        )
    return 'Ответ не является корректным JSON.'


def _repair_instruction(problems: str) -> str:
    """Запрос на починку JSON: короткий, без дампа данных, с явной формой ответа."""
    return (
        'Исправь JSON DocumentAST. Верни ПОЛНЫЙ валидный JSON-ОБЪЕКТ '
        '(не массив, не список объектов, не markdown) и ничего кроме него.\n'
        'Корень: {"metadata":{"title":"...","author":"...","enable_toc":true,'
        '"enable_track_changes":false},"sections":[...]}\n'
        'Секция: {"id":"unique","title":"1. ...","level":1..3,"blocks":[...]}\n'
        'Блок: {"type":"paragraph","text":"..."} | {"type":"formula","latex":"...","display_mode":"block"} '
        '| {"type":"table","headers":[...],"rows":[[{"text":"...","align":"left","col_span":1,"row_span":1}]],"col_widths":[100]} '
        '| {"type":"callout","callout_type":"info","title":"...","text":"..."}\n'
        f'Проблемы:\n{problems}'
    )


def _json_generation_failure(exc: Exception) -> str | None:
    """Достаёт частичный ответ модели, если провайдер отклонил JSON.

    Groq в json-режиме отвечает 400 ``json_validate_failed``, когда модель
    не дописала JSON (например, её обрезал лимит токенов). Тело ошибки
    приходит в разных видах: вложенным (``body['error']``) или плоским —
    поэтому проверяются все формы. Это не поломка ключа и не поломка схемы:
    документ нужно попросить сделать короче.
    """
    body = getattr(exc, 'body', None)
    if not isinstance(body, dict):
        body = {}
    nested = body.get('error') if isinstance(body.get('error'), dict) else {}

    code = getattr(exc, 'code', None) or body.get('code') or nested.get('code')
    if code != 'json_validate_failed':
        return None
    return body.get('failed_generation') or nested.get('failed_generation') or ''


def _daily_quota_exceeded(exc: Exception) -> bool:
    """Исчерпана суточная квота провайдера (а не минутная).

    Минутный лимит лечится повтором, суточный — только ожиданием до
    следующего дня. Различать их важно: иначе агент будет бессмысленно
    повторять запрос и висеть.
    """
    body = getattr(exc, 'body', None)
    text = ''
    if isinstance(body, dict):
        error = body.get('error') if isinstance(body.get('error'), dict) else body
        text = str(error.get('message', ''))
    if not text:
        text = str(exc)
    return 'tokens per day' in text or 'TPD' in text


def _create_with_retry(create, attempts: int = 4, base_delay: float = 5.0):
    """Повторяет запрос при 429 и временных ошибках сервера.

    Groq на бесплатном тарифе ограничивает токены в минуту (8 000 на
    организацию), поэтому одинаковый запрос может быть отклонён из-за
    нагрузки. Это инфраструктурная ошибка, а не дефект ответа модели:
    повторяем тот же запрос с задержкой, а не просим модель что-то менять.
    """
    delay = base_delay
    for attempt in range(attempts):
        try:
            return create()
        except Exception as exc:
            status = getattr(exc, 'status_code', None)
            if _daily_quota_exceeded(exc):
                raise ValueError(
                    'Исчерпана суточная квота токенов у провайдера (Groq: tokens per day). '
                    'Повтор не поможет — нужен следующий день, другой тариф или другая модель.'
                ) from exc
            retryable = status == 429 or (isinstance(status, int) and status >= 500)
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError('Unexpected retry termination')


def plan_document(prompt: str, model: str | None = None, client=None,
                  provider: str | None = None) -> DocumentAST:
    provider, model = _resolve_provider_model(provider, model)
    if client is None:
        if provider == 'anthropic':
            from anthropic import Anthropic
            client = Anthropic()
        else:
            from openai import OpenAI
            key = resolve_api_key('groq')
            if not key:
                raise ValueError(
                    'GROQ_API_KEY is not set (fallback: LLM_API_KEY). '
                    'Задай ключ через scripts/set-api-key.ps1 или переменную окружения.'
                )
            client = OpenAI(api_key=key, base_url=GROQ_BASE_URL)

    messages = [{'role': 'user', 'content': prompt}]
    last_problems = 'неизвестная ошибка'
    for attempt in range(MAX_AST_REPAIR_ATTEMPTS + 1):
        finish_reason = None
        if provider == 'anthropic':
            response = _create_with_retry(lambda: client.messages.create(
                model=model, max_tokens=MAX_TOKENS, temperature=0,
                system=SYSTEM, messages=messages))
            raw = ''.join(b.text for b in response.content if b.type == 'text').strip()
            finish_reason = getattr(response, 'stop_reason', None)
        else:
            try:
                response = _create_with_retry(lambda: client.chat.completions.create(
                    model=model, max_completion_tokens=MAX_OUTPUT_TOKENS,
                    messages=[{'role': 'system', 'content': SYSTEM}, *messages],
                    response_format={'type': 'json_object'},
                ))
            except Exception as exc:
                partial = _json_generation_failure(exc)
                if partial is None:
                    raise
                # Модель не дописала JSON — провайдер вернул 400. Лечится
                # просьбой сократить документ, а не аварийным выходом.
                last_problems = 'Ответ модели оборвался на середине JSON.'
                if attempt == MAX_AST_REPAIR_ATTEMPTS:
                    raise ValueError(
                        f'Модель вернула обрезанный JSON после {MAX_AST_REPAIR_ATTEMPTS} попыток правки'
                    ) from exc
                messages.extend([
                    {'role': 'assistant', 'content': partial or '(ответ оборвался)'},
                    {'role': 'user', 'content': _repair_instruction(_truncation_hint('length'))},
                ])
                continue
            raw = response.choices[0].message.content or ''
            finish_reason = getattr(response.choices[0], 'finish_reason', None)
            if not raw.strip():
                raise ValueError('Groq returned empty content; check model token limits and reasoning settings')
        raw = _strip_fences(raw)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_problems = f'Ответ не является корректным JSON: {exc}'
            if attempt == MAX_AST_REPAIR_ATTEMPTS:
                raise ValueError(
                    f'Модель вернула невалидный JSON после {MAX_AST_REPAIR_ATTEMPTS} попыток правки: {last_problems}'
                ) from exc
            messages.extend([
                {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': _repair_instruction(_truncation_hint(finish_reason))},
            ])
            continue

        try:
            document = DocumentAST.model_validate(normalize_document(_unwrap_document(payload)))
            if not _has_structure(payload):
                # Модель не вернула ни одного раздела — это провал, а не
                # результат: пустая заготовка не должна проходить как документ.
                raise ValueError('Модель не вернула структуру документа (нет разделов).')
            return document
        except ValidationError as exc:
            last_problems = _describe_errors(exc)
            if attempt == MAX_AST_REPAIR_ATTEMPTS:
                raise ValueError(
                    f'Unable to produce valid DocumentAST after {MAX_AST_REPAIR_ATTEMPTS} repairs:\n{last_problems}'
                ) from exc
            messages.extend([
                {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': _repair_instruction(last_problems)},
            ])
        except ValueError as exc:
            last_problems = str(exc)
            if attempt == MAX_AST_REPAIR_ATTEMPTS:
                raise ValueError(
                    f'Unable to produce valid DocumentAST after {MAX_AST_REPAIR_ATTEMPTS} repairs:\n{last_problems}'
                ) from exc
            messages.extend([
                {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': _repair_instruction(last_problems)},
            ])
    raise RuntimeError('Unexpected planner termination')

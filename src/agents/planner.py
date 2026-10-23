"""LLM-to-validated-AST adapter for Anthropic and Groq."""
import json
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
from src.models.ast_schema import DocumentAST

SYSTEM = '''Ты — архитектор технической документации. Верни ТОЛЬКО JSON DocumentAST без markdown.
Корень: {"metadata":{"title":"...","author":"...","enable_toc":true,"enable_track_changes":false},"sections":[...]}
Секции: {"id":"unique","title":"1. ...","level":1..3,"blocks":[...]}
Блоки: {"type":"paragraph","text":"...","runs":[{"text":"...","bold":false,"italic":false,"code":false}]}, {"type":"formula","latex":"E=mc^2","display_mode":"block"}, {"type":"table","headers":["..."],"rows":[[{"text":"...","align":"left","col_span":1,"row_span":1}]],"col_widths":[100]}, {"type":"callout","callout_type":"info","title":"...","text":"..."}.
Для таблиц процентные ширины в сумме 100. Не придумывай неподтвержденные факты. Разделы не глубже Heading 3.'''

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
    for attempt in range(MAX_AST_REPAIR_ATTEMPTS + 1):
        if provider == 'anthropic':
            response = client.messages.create(
                model=model, max_tokens=MAX_TOKENS, temperature=0,
                system=SYSTEM, messages=messages)
            raw = ''.join(b.text for b in response.content if b.type == 'text').strip()
        else:
            response = client.chat.completions.create(
                model=model, max_completion_tokens=MAX_OUTPUT_TOKENS,
                messages=[{'role': 'system', 'content': SYSTEM}, *messages],
                response_format={'type': 'json_object'},
            )
            raw = response.choices[0].message.content or ''
            if not raw.strip():
                raise ValueError('Groq returned empty content; check model token limits and reasoning settings')
        raw = _strip_fences(raw)
        try:
            return DocumentAST.model_validate(json.loads(raw))
        except (ValidationError, ValueError) as exc:
            if attempt == MAX_AST_REPAIR_ATTEMPTS:
                raise ValueError(
                    f'Unable to produce valid DocumentAST after {MAX_AST_REPAIR_ATTEMPTS} repairs'
                ) from exc
            messages.extend([
                {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': f'Исправь JSON по ошибке: {str(exc)[:3500]}. Верни только валидный JSON.'},
            ])
    raise RuntimeError('Unexpected planner termination')

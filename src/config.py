"""Провайдер и параметры генерации.

Приоритет источников (от высшего к низшему):

1. переменная окружения — ``DOCX_LLM_PROVIDER``, ``DOCX_LLM_MODEL``;
2. файл ``config/settings.yaml`` (секции ``llm`` и ``generation``);
3. значения по умолчанию этого модуля.

Ключи API сюда не попадают: они читаются из окружения функцией
:func:`resolve_api_key`. Файл ``.env`` подгружается автоматически, поэтому
в репозитории ключа нет ни в каком виде.
"""
from __future__ import annotations

import os

from src.core.settings import load_env_file, read_settings_raw

# Файл .env в окружение: реальное окружение важнее файла (override=False).
load_env_file()

_settings = read_settings_raw()
_llm = _settings.get('llm') or {}
_generation = _settings.get('generation') or {}

DEFAULT_MODELS = {
    'anthropic': 'claude-sonnet-4-5',
    'groq': 'openai/gpt-oss-120b',
}

#: Имена переменных окружения с ключом: сначала специфичные для провайдера,
#: затем общая LLM_API_KEY. Проверка идёт по порядку.
KEY_ENV_NAMES = {
    'groq': ('GROQ_API_KEY', 'LLM_API_KEY'),
    'anthropic': ('ANTHROPIC_API_KEY', 'LLM_API_KEY'),
}

PROVIDER = (os.getenv('DOCX_LLM_PROVIDER') or _llm.get('provider') or 'anthropic').strip().lower()

_yaml_model = _llm.get('model') if _llm.get('provider') == PROVIDER else None

MODEL = (
    os.getenv('DOCX_LLM_MODEL')
    or (os.getenv('ANTHROPIC_MODEL') if PROVIDER == 'anthropic' else os.getenv('GROQ_MODEL'))
    or _yaml_model
    or DEFAULT_MODELS.get(PROVIDER, DEFAULT_MODELS['anthropic'])
)

GROQ_BASE_URL = (
    os.getenv('GROQ_BASE_URL')
    or _llm.get('base_url')
    or 'https://api.groq.com/openai/v1'
)

#: Лимит токенов ответа для провайдеров с max_tokens.
MAX_TOKENS = int(_generation.get('max_tokens', 6000))

#: Лимит токенов ответа для OpenAI-совместимых API (max_completion_tokens).
MAX_OUTPUT_TOKENS = int(_llm.get('max_output_tokens', 8192))

#: Сколько раз агент пытается починить невалидный JSON от модели.
MAX_AST_REPAIR_ATTEMPTS = int(_generation.get('max_ast_repair_attempts', 2))

#: Таймаут запроса к провайдеру, секунды.
REQUEST_TIMEOUT = float(_llm.get('timeout_seconds', 120))


def resolve_api_key(provider: str | None = None) -> str | None:
    """Возвращает ключ провайдера из окружения или ``None``.

    Сначала проверяется специфичная переменная (``GROQ_API_KEY``,
    ``ANTHROPIC_API_KEY``), затем общая ``LLM_API_KEY`` — так один и тот же
    секрет работает и для MCP-сервера в opencode, и для локального запуска.
    """
    selected = (provider or PROVIDER).strip().lower()
    for name in KEY_ENV_NAMES.get(selected, ('LLM_API_KEY',)):
        value = (os.getenv(name) or '').strip()
        if value:
            return value
    return None

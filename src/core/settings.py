"""Загрузка конфигурации и безопасное разрешение ссылок на секреты.

Правило хранения ключей в этом проекте:

* в репозитории лежит только плейсхолдер ``${LLM_API_KEY}``;
* значение живёт в переменной окружения — локально в переменной уровня User
  (её ставит ``scripts/set-api-key.ps1``), в CI — в GitHub Actions Secret;
* подстановка происходит в памяти при загрузке конфигурации, поэтому ни один
  скомпилированный или сгенерированный файл не содержит ключ.

Если переменная не задана, бросается :class:`SecretNotConfigured` с именами
переменных — без значений, чтобы ошибку можно было безопасно печатать в лог.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

try:  # .env — необязательная удобная обёртка, ключ всё равно в окружении
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - зависимость ставится в requirements
    load_dotenv = None  # type: ignore[assignment]

__all__ = [
    "SecretNotConfigured",
    "load_settings",
    "resolve_placeholders",
    "mask_secrets",
    "referenced_env_names",
    "DEFAULT_SETTINGS_PATH",
]

#: Плейсхолдер вида ``${ИМЯ_ПЕРЕМЕННОЙ}``.
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Корень репозитория: src/core/settings.py -> src/core -> src -> <root>
DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

#: Поле, для которого применяется цепочка резервных переменных.
_SECRET_FIELD = "api_key"

#: Поле со списком резервных имён переменных.
_FALLBACKS_FIELD = "api_key_fallbacks"


class SecretNotConfigured(RuntimeError):
    """Секрет не найден в окружении.

    В тексте исключения перечислены только имена переменных, никогда значения.
    """


def _lookup_env(name: str, fallbacks: Sequence[str]) -> str | None:
    """Возвращает значение переменной или её резервной копии."""
    for candidate in (name, *fallbacks):
        value = os.environ.get(candidate, "").strip()
        if value:
            return value
    return None


def _resolve_str(value: str, fallbacks: Sequence[str]) -> str:
    """Подставляет значения переменных окружения вместо плейсхолдеров."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = _lookup_env(name, fallbacks)
        if resolved is None:
            hint = f" (проверены также: {', '.join(fallbacks)})" if fallbacks else ""
            raise SecretNotConfigured(
                f"Переменная окружения {name} не задана{hint}. "
                "Задай её через scripts/set-api-key.ps1 или как GitHub Actions Secret."
            )
        return resolved

    return PLACEHOLDER_RE.sub(substitute, value)


def _resolve_node(node: Any, fallbacks: Sequence[str], in_secret_field: bool = False) -> Any:
    """Обход структуры с сохранением контекста «мы внутри поля api_key»."""
    if isinstance(node, Mapping):
        result: dict[str, Any] = {}
        for key, item in node.items():
            if key == _FALLBACKS_FIELD:
                continue  # служебное поле, в итоговую конфигурацию не попадает
            result[key] = _resolve_node(item, fallbacks, key == _SECRET_FIELD)
        return result
    if isinstance(node, list):
        return [_resolve_node(item, fallbacks, in_secret_field) for item in node]
    if isinstance(node, str):
        # Резервные имена применяются только внутри поля api_key:
        # для остальных плейсхолдеров важен их собственный переменная.
        return _resolve_str(node, fallbacks if in_secret_field else ())
    return node


def resolve_placeholders(value: Any, fallback_env: Sequence[str] = ()) -> Any:
    """Рекурсивно заменяет ``${ПЕРЕМЕННУЮ}`` в структуре на значения окружения.

    Резервные имена ``fallback_env`` действуют только для поля ``api_key`` —
    им именно там нужен «ключ из любого места».
    """
    return _resolve_node(value, tuple(fallback_env))


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    """Читает YAML-конфигурацию и подставляет секреты из окружения.

    Значения окружения имеют приоритет над файлом ``.env``: файл лишь
    подставляет то, чего ещё нет в процессе.

    :raises FileNotFoundError: файл конфигурации не найден.
    :raises SecretNotConfigured: обязательная переменная окружения не задана.
    """
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.is_file():
        raise FileNotFoundError(f"Файл конфигурации не найден: {settings_path}")

    if load_dotenv is not None:
        # override=False — реальное окружение важнее файла
        load_dotenv(dotenv_path=settings_path.parent.parent / ".env", override=False)

    raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Ожидался словарь на верхнем уровне в {settings_path}")

    # Резервные источники ключа можно объявить на верхнем уровне или внутри
    # секции llm. Второй вариант удобнее: у каждого профиля провайдера свой
    # список, и при переключении с Gemini на Groq старый ключ не подставится
    # случайно.
    fallbacks = tuple(raw.get(_FALLBACKS_FIELD) or ())
    llm_section = raw.get("llm")
    if isinstance(llm_section, Mapping):
        fallbacks = tuple(llm_section.get(_FALLBACKS_FIELD) or fallbacks)

    resolved = resolve_placeholders(raw, fallbacks)
    return resolved


def referenced_env_names(raw: Any) -> list[str]:
    """Возвращает имена переменных, упомянутых плейсхолдерами в конфиге."""
    names: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            for match in PLACEHOLDER_RE.finditer(node):
                if match.group(1) not in names:
                    names.append(match.group(1))

    walk(raw)
    return names


def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Заменяет вхождения секретов в тексте на ``***``.

    Нужен, чтобы в лог уходило сообщение об ошибке запроса к провайдеру,
    а не сам ключ.
    """
    result = text
    for secret in secrets:
        if secret and len(secret) >= 8:
            result = result.replace(secret, "***")
    return result

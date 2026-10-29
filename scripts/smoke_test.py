#!/usr/bin/env python3
"""Минимальная проверка связи с LLM-провайдером.

Локально ключ берётся из переменной окружения ``LLM_API_KEY`` (или из ``.env``),
в CI — из ``secrets.LLM_API_KEY``.

Если ключа нет, скрипт не падает: печатает «пропущено» и выходит с кодом 0.
В CI секрет может быть не настроен, и это не повод ронять сборку.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Windows-консоль по умолчанию отдаёт кириллицу в однобайтовой кодировке,
# и PowerShell читает байты как UTF-8 — текст превращается в мусор.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.settings import SecretNotConfigured, load_settings, mask_secrets  # noqa: E402

PROMPT = "Ответь одним словом: OK"


def build_request(llm: dict) -> tuple[str, dict[str, str], dict]:
    """Собирает URL, заголовки и тело запроса под провайдера."""
    base = llm["base_url"].rstrip("/")
    key = llm["api_key"]
    model = llm["model"]

    if llm.get("auth_style") == "header":
        # Google: ключ идёт заголовком x-goog-api-key.
        # Передача в Authorization: Bearer с ключами формата AQ.* даёт 401.
        headers = {llm.get("auth_header", "x-goog-api-key"): key}
        url = f"{base}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 16},
        }
    else:
        headers = {"Authorization": f"Bearer {key}"}
        url = f"{base}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            # У reasoning-моделей (gpt-oss) токены ответа включают размышления,
            # поэтому лимит берём с запасом.
            "max_completion_tokens": 256,
        }

    headers["Content-Type"] = "application/json"
    return url, headers, body


def main() -> int:
    try:
        settings = load_settings(ROOT / "config" / "settings.yaml")
    except SecretNotConfigured as exc:
        print(f"Пропущено: {exc}")
        return 0
    except (FileNotFoundError, KeyError) as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    llm = settings["llm"]
    key = llm["api_key"]
    url, headers, body = build_request(llm)

    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=llm.get("timeout_seconds", 120)) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code == 429:
            # Квота провайдера исчерпана: ключ при этом рабочий, ключ не при чём.
            print(f"Пропущено: провайдер вернул 429 (лимит запросов): {mask_secrets(detail, [key])}")
            return 0
        print(f"Ошибка HTTP {exc.code}: {mask_secrets(detail, [key])}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - в лог уходит текст без ключа
        print(f"Ошибка запроса: {mask_secrets(str(exc), [key])}", file=sys.stderr)
        return 1

    print(f"OK: провайдер {llm['provider']}, модель {llm['model']} отвечает.")
    print(f"  размер ответа: {len(payload)} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

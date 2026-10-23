#!/usr/bin/env python3
"""Проверка, что в репозитории не завелись ключи.

Скрипт гоняется и локально (перед пушем), и в CI (шаг workflow).
Ищет характерные префиксы ключей в отслеживаемых git-файлах и заодно
проверяет, что файл .env не попал в индекс.

Ничего не печатает кроме номеров строк и масок — сами совпадения
показаны только как «<префикс>…», чтобы скрипт нельзя было использовать
как источник ключа.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Windows-консоль по умолчанию отдаёт кириллицу в однобайтовой кодировке,
# и PowerShell читает байты как UTF-8 — текст превращается в мусор.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

#: (имя правила, регулярное выражение)
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_pat_legacy", re.compile(r"\bghp_[A-Za-z0-9]{20,}")),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("google_standard", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("google_authorization", re.compile(r"\bAQ\.Ab[A-Za-z0-9_-]{20,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

#: Файлы, где префиксы встречаются как текст описания, а не как живой ключ.
ALLOWLIST = {
    "scripts/check_secrets.py",
    "docs/SECRETS.md",
}

#: Файлы, которые вообще не должны быть в индексе.
FORBIDDEN_TRACKED = {".env", ".env.local", "config/local.yaml", "settings.local.yaml"}


def git_tracked_files() -> list[str]:
    """Отслеживаемые git-файлы плюс ещё не добавленные в индекс.

    Локально незакоммиченный файл тоже нужно проверять: именно он чаще всего
    содержит ключ по недосмотру. ``--exclude-standard`` убирает игнорируемые
    файлы (``.env`` и прочее), поэтому в проверку они не попадают.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        print("Не удалось получить список файлов из git.", file=sys.stderr)
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def mask(match_text: str) -> str:
    """Показывает только тип и первые символы, но не сам секрет."""
    return f"<{match_text[:6]}…>"


def main() -> int:
    tracked = git_tracked_files()
    if not tracked:
        print("Список отслеживаемых файлов пуст — нечего проверять.")
        return 0

    problems: list[str] = []

    for path in FORBIDDEN_TRACKED:
        if path in tracked:
            problems.append(f"Файл {path} отслеживается git и не должен быть в репозитории.")

    for rel in tracked:
        if rel in ALLOWLIST:
            continue
        file_path = Path(rel)
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # бинарные файлы (шаблоны .dotx) пропускаем

        for line_no, line in enumerate(content.splitlines(), start=1):
            for rule_name, pattern in PATTERNS:
                match = pattern.search(line)
                if match:
                    problems.append(
                        f"{rel}:{line_no}: возможный секрет [{rule_name}] {mask(match.group(0))}"
                    )

    if problems:
        print("Найдены потенциальные утечки секретов:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nЕсли это ложное срабатывание (например, пример в документации), "
            "добавь файл в ALLOWLIST в scripts/check_secrets.py.",
            file=sys.stderr,
        )
        return 1

    print(f"Проверено файлов: {len(tracked)}. Утечек не найдено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Каждый сторонний импорт проекта должен быть заявлен в requirements.txt.

Тест ловит именно ту ошибку, из-за которой CI падал: модуль импортируется в
коде, но его пакета нет в зависимостях — локально всё работает (пакет стоит
из другого проекта), а на чистом раннере падает ``ModuleNotFoundError``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Имя модуля в импорте -> имя пакета в pip.
MODULE_TO_PACKAGE = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "docx": "python-docx",
    "latex2mathml": "latex2mathml",
    "lxml": "lxml",
    "mcp": "mcp",
    "openai": "openai",
    "anthropic": "anthropic",
    "pydantic": "pydantic",
    "typer": "typer",
    "pytest": "pytest",
}

#: Модули самого проекта — импорты вида ``from src.config import ...``.
LOCAL_MODULES = {"src"}


def _python_files() -> list[Path]:
    return [
        path
        for folder in ("src", "scripts", "tests")
        for path in (ROOT / folder).rglob("*.py")
    ]


def _third_party_imports() -> set[str]:
    found: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return {
        name
        for name in found
        if name not in sys.stdlib_module_names and name not in LOCAL_MODULES
    }


def test_requirements_cover_all_third_party_imports():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    missing = []
    for module in sorted(_third_party_imports()):
        package = MODULE_TO_PACKAGE.get(module, module)
        if not re.search(rf"(?m)^{re.escape(package)}\b", requirements):
            missing.append(f"{module} (пакет {package})")
    assert not missing, "Не указаны в requirements.txt: " + ", ".join(missing)


def test_requirements_is_not_empty():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert text.strip(), "requirements.txt пуст"

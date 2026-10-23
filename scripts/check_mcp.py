#!/usr/bin/env python3
"""Проверка, что MCP-сервер поднимается и отдаёт инструменты.

Поднимает ``python -m src.interfaces.mcp_server`` как дочерний процесс,
договаривается по MCP over stdio и запрашивает список инструментов.

Нужен для локальной проверки перед пушем и для шага CI: если сервер не
стартует или не отвечает, сборка падает на первой же минуте, а не в
середине работы агента.

    python scripts\\check_mcp.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Windows-консоль по умолчанию отдаёт кириллицу в однобайтовой кодировке,
# и PowerShell читает байты как UTF-8 — текст превращается в мусор.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parents[1]

#: Инструменты, которые сервер обязан отдавать.
EXPECTED_TOOLS = {
    "docx_validate_ast",
    "docx_compile",
    "docx_interview",
    "docx_generate",
}


async def probe() -> list[str]:
    params = StdioServerParameters(
        command="python",
        args=["-m", "src.interfaces.mcp_server"],
        cwd=ROOT,
        env=None,  # наследуем окружение: так ключ доходит до сервера
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [tool.name for tool in result.tools]


async def main() -> int:
    try:
        names = await probe()
    except Exception as exc:  # noqa: BLE001 - в вывод уходит текст ошибки
        print(f"MCP-сервер не ответил: {exc}", file=sys.stderr)
        return 1

    print(f"Инструментов: {len(names)}")
    for name in names:
        print(f"  {name}")

    missing = EXPECTED_TOOLS - set(names)
    if missing:
        print(f"Отсутствуют ожидаемые инструменты: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1

    print("MCP-сервер работает, все инструменты на месте.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

# DOCX Agent — Document AST prototype

Python 3.11+ prototype: structured Pydantic AST → styled Word DOCX, with an LLM-powered planner (Groq or Anthropic) exposed as an MCP server for OpenCode.

## Setup

```bash
python -m pip install -r requirements.txt
pytest -q
```

## Offline workflow (no API required)

```bash
python -m src.cli from-json example_ast.json --output report.docx
```

A sample document is built by the tests as `output_sample.docx`.

## LLM workflow (Groq или Anthropic)

```bash
python -m src.cli generate 'Подготовь отчёт для руководителей о результатах проекта за 2026 год...' --output report.docx --skip-questions
```

Ключ берётся из переменной окружения: сначала `GROQ_API_KEY` / `ANTHROPIC_API_KEY`, а если они не заданы — общая `LLM_API_KEY` (её ставит `scripts\set-api-key.ps1` или файл `.env`). Провайдер по умолчанию берётся из `config/settings.yaml` (сейчас `groq`) и переопределяется через `DOCX_LLM_PROVIDER`. Модель — через `--model`, `DOCX_LLM_MODEL` или `GROQ_MODEL`/`ANTHROPIC_MODEL`. Планировщик валидирует JSON через Pydantic и бросает исключение на невалидный ответ: provider-native строгий structured output не используется.

## Architecture

- `src/models/ast_schema.py`: discriminated, strictly validated document AST.
- `src/core/ast_normalizer.py`: приводит ответ модели к схеме — лишние поля, ширины таблиц, уровни заголовков, неизвестные типы блоков.
- `src/core/`: OMML conversion, tables, callouts and DOCX compilation.
- `src/agents/interviewer.py`: heuristic requirement questions.
- `src/agents/planner.py`: LLM → нормализованный и валидный AST, до двух попыток починки.
- `src/cli.py`: `generate` and `from-json` commands.

## Документация

| Документ | О чём |
|---|---|
| [`docs/TOOLS.md`](docs/TOOLS.md) | Сводный перечень используемых инструментов: библиотеки, форматы, внешние сервисы, инструменты продукта, контроль качества |
| [`docs/SECRETS.md`](docs/SECRETS.md) | Как хранить API-ключи локально и в CI, и что делать, если ключ утёк |
| [`PROJECT_SPEC.md`](PROJECT_SPEC.md) | Техническая спецификация: архитектура, схема AST, компилятор OpenXML |
| [`AGENTS.md`](AGENTS.md) | Регламенты агентов, стейт-машина оркестрации, протоколы валидации и отката |
| [`REVIEW_REPORT.md`](REVIEW_REPORT.md) | Аудит прототипа: что исправлено и что ещё не реализовано |

## Known limits

- Bundled MathML→OMML XSLT supports common basic constructs (tokens, fractions, powers, subscripts, roots). For production-grade advanced mathematics replace `assets/xslt/MML2OMML.XSL` with the official Microsoft stylesheet; unsupported constructs may lose semantics.
- Word/LibreOffice must update TOC and page-count fields upon opening; preview applications may not do so.
- Interviewer is a lightweight heuristic, not a full requirement analysis agent.
- LLM mode needs a valid API key (Groq or Anthropic) and network access; offline compilation and tests do not.
- Word table borders and layout may vary across renderers.

## Ревизия по PROJECT_SPEC.md / AGENTS.md (22.10.2026)

- AST v2: `metadata`, `runs`, `display_mode`, тип `critical`, объединение ячеек, проверка границ и сумм ширин. Старый плоский AST автоматически преобразуется при загрузке для обратной совместимости.
- Компилятор использует стили шаблона без переписывания шрифта/полей документа; обработка некорректной формулы безопасна (текстовый маркер + WARNING).
- Агентный планировщик запрашивает AST v2 и имеет до двух попыток исправления невалидного JSON.
- `enable_track_changes` включает режим записи последующих правок в Word. Это **не** реализует автоматический diff между версиями AST.
- Сложные объединения таблиц поддерживаются через объединение ячеек `python-docx` и проверку пересечений.

### Пока НЕ реализовано (отдельные этапы)

- Поиск RAG, разделение Planner/Synthesizers, параллельная генерация разделов и полноценная state machine.
- Дифференциальные правки AST с генерацией `w:ins` и `w:del`; подключение интерфейса бота.
- Загрузка и конвертация `.dotx` (поддерживаются `.docx` шаблоны через параметр `template` Python API).
- Полный официальный XSLT MathML→OMML. В комплекте ограниченный преобразователь; сложные формулы требуют отдельной проверки.
- Нагрузочное подтверждение лимита 3,5 секунды/50 страниц и полная проверка ECMA-376 XML Schema; тесты проверяют ZIP/XML и чтение python-docx.

Режим `from-json` позволяет компилировать документ **без ключа Anthropic**, полностью локально.

## Groq (добавлено 22.10.2026)

Также поддерживаются модели Groq через OpenAI-compatible Chat Completions API:

- `groq/openai/gpt-oss-120b` → API model `openai/gpt-oss-120b`
- `groq/openai/gpt-oss-20b` → API model `openai/gpt-oss-20b`
- `groq/qwen/qwen3.8-27b` → API model `qwen/qwen3.8-27b`

PowerShell:

```powershell
$env:GROQ_API_KEY = 'your-groq-key'
python -m src.cli generate 'Составь технический отчёт для руководителей' --provider groq --model groq/openai/gpt-oss-120b --output report.docx --skip-questions
```

Можно выбрать провайдера по умолчанию:

```powershell
$env:DOCX_LLM_PROVIDER = 'groq'
$env:DOCX_LLM_MODEL = 'qwen/qwen3.8-27b'
python -m src.cli generate 'Технический отчёт для руководителей' --skip-questions
```

Без `--provider` используется провайдер из `config/settings.yaml` (по умолчанию `groq`; `DOCX_LLM_PROVIDER` переопределяет). Ключ для Groq берётся из `GROQ_API_KEY` или общей `LLM_API_KEY`, для Anthropic — из `ANTHROPIC_API_KEY` или общей `LLM_API_KEY`. Используется JSON mode с Pydantic-проверкой и максимум двумя попытками исправления невалидного AST. Доступность моделей и квоты зависят от аккаунта провайдера. API-запросы в тестах замоканы, реальных запросов без ключа не выполняется.

## MCP-сервер (добавлено 23.10.2026)

Функционал агента доступен как MCP-инструменты через stdio-сервер `src/interfaces/mcp_server.py` (SDK `mcp` 2.x). Запуск вручную:

```powershell
python -m src.interfaces.mcp_server
```

Инструменты:

| Инструмент | Назначение | Ключ LLM |
|---|---|---|
| `docx_validate_ast(ast_json)` | Валидация Document AST по схеме Pydantic, отчёт об ошибках | нет |
| `docx_compile(ast_json, output_path)` | Сборка `.docx` из AST | нет |
| `docx_interview(prompt)` | Предполётный анализ ТЗ: список уточняющих вопросов | нет |
| `docx_generate(prompt, output_path, provider, model)` | Полный цикл LLM → AST → `.docx` | Groq/Anthropic |

Безопасность: выходные пути инструментов ограничены рабочей директорией сервера и должны иметь расширение `.docx`.

Подключение к OpenCode — в `opencode.json` (корень проекта):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "groq/llama-3.3-70b-versatile",
  "provider": {
    "groq": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Groq",
      "options": {
        "baseURL": "https://api.groq.com/openai/v1",
        "apiKey": "{env:GROQ_API_KEY}"
      },
      "models": {
        "llama-3.3-70b-versatile": { "name": "Llama 3.3 70B Versatile" },
        "openai/gpt-oss-120b": { "name": "GPT OSS 120B" }
      }
    }
  },
  "mcp": {
    "servers": {
      "docx-agent": {
        "type": "local",
        "command": ["python", "-m", "src.interfaces.mcp_server"],
        "cwd": ".",
        "environment": {
          "GROQ_API_KEY": "{env:GROQ_API_KEY}",
          "LLM_API_KEY": "{env:LLM_API_KEY}",
          "ANTHROPIC_API_KEY": "{env:ANTHROPIC_API_KEY}",
          "DOCX_LLM_PROVIDER": "{env:DOCX_LLM_PROVIDER}",
          "DOCX_LLM_MODEL": "{env:DOCX_LLM_MODEL}",
          "GROQ_BASE_URL": "{env:GROQ_BASE_URL}"
        }
      }
    }
  }
}
```

Ключи LLM передаются только через переменные окружения (подстановка `{env:...}`), в конфиг они не записываются. `docx_generate` без ключа возвращает ошибку — офлайн-инструменты работают всегда.

## Секреты и конфигурация

Ключ API **не хранится в репозитории**. В `config/settings.yaml` лежит только плейсхолдер, который подставляется из переменной окружения в памяти:

```yaml
llm:
  api_key: "${LLM_API_KEY}"
```

| Среда | Где живёт ключ | Кто ставит |
|-------|----------------|------------|
| Локально | переменная уровня User `LLM_API_KEY` | `scripts\set-api-key.ps1` |
| Локально (альтернатива) | `.env` (в `.gitignore`) | вручную по `.env.example` |
| CI | GitHub Actions Secret `LLM_API_KEY` | Settings репозитория → Secrets |

Один и тот же секрет работает в обоих местах — код к нему обращается одинаково.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1   # задать ключ
python scripts\smoke_test.py                                       # проверить связь
python scripts\check_secrets.py                                    # проверить репозиторий
```

Подробности, включая разбор «ключ утёк» и особенность заголовка `x-goog-api-key` у Google, — в [`docs/SECRETS.md`](docs/SECRETS.md).

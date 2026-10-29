# Инструменты и технологии проекта

Сводный перечень того, из чего собран DocxGen Agent: библиотеки, форматы,
внешние сервисы, инструменты самого продукта и средства контроля качества.
Документ описывает **текущее состояние репозитория** — то, что реально
подключено и проверяется тестами.

Источники: `requirements.txt`, `config/settings.yaml`, `opencode.json`,
`.github/workflows/ci.yml`, `PROJECT_SPEC.md`, `AGENTS.md`.

---

## 1. Язык и среда выполнения

| Компонент | Значение |
|---|---|
| Язык | Python 3.11+ (разрабатывается и тестируется на 3.12) |
| Транспорт агента | MCP over stdio (`json-rpc` через stdin/stdout) |
| Хостинг агента | opencode Desktop 2.1.3 / opencode CLI |
| Формат результата | `.docx` (OpenXML, ECMA-376) |

Из стандартной библиотеки используются `json`, `zipfile`, `xml.etree`,
`pathlib`, `dataclasses`, `asyncio`, `subprocess`, `enum`, `re`.

---

## 2. Библиотеки (`requirements.txt`)

| Пакет | Версия | Назначение |
|---|---|---|
| `python-docx` | ≥1.1 | Сборка `.docx`: абзацы, стили, таблицы, колонтитулы, разделы |
| `lxml` | ≥5 | Прямой инжект XML в OpenXML: поля TOC, `w:ins`/`w:del`, `w:tblGrid` |
| `latex2mathml` | ≥3.77 | Преобразование формул LaTeX → MathML |
| `pydantic` | ≥2, <3 | Схема и строгая валидация Document AST (`extra='forbid'`) |
| `pyyaml` | ≥6.0.1 | Чтение конфигурации `config/settings.yaml` |
| `typer` | ≥0.12 | CLI-интерфейс: команды `generate` и `from-json` |
| `rich` | ≥13.7 | Форматированный вывод CLI (подтягивается `typer`, объявлен явно) |
| `openai` | ≥1.50, <3 | OpenAI-совместимый клиент для **Groq** |
| `anthropic` | ≥0.40 | Альтернативный LLM-провайдер (Anthropic Messages API) |
| `mcp` | ≥2.3 | MCP SDK 2.x: `MCPServer`, stdio-транспорт, клиент для самопроверки |
| `python-dotenv` | ≥1.0.1 | Чтение `.env` как альтернативы переменной окружения |
| `pytest` | ≥8 | Тесты (в том числе как dev-зависимость) |

---

## 3. Форматы и стандарты

| Формат | Где используется |
|---|---|
| OpenXML / OOXML (ECMA-376) | Итоговый `.docx`, шаблон `assets/templates/default.docx` |
| Document AST (JSON) | Промежуточный контракт между агентом и компилятором |
| LaTeX → MathML → OMML | Формулы: `latex2mathml` + `assets/xslt/MML2OMML.XSL` (XSLT 1.0) |
| Markdown | Документация проекта |
| YAML | Конфигурация `config/settings.yaml` |

---

## 4. Внешние сервисы

| Сервис | Роль | Детали |
|---|---|---|
| **Groq** | LLM-провайдер (основной) | OpenAI-совместимый API, `api.groq.com/openai/v1`; модель по умолчанию `openai/gpt-oss-120b`. Бесплатный тариф: 8 000 токенов/мин на организацию — планировщик повторяет запрос при 429 и держит лимит ответа в этих рамках |
| **Anthropic** | LLM-провайдер (альтернативный) | Messages API, модель `claude-sonnet-4-5` |
| **opencode** | Среда агента и MCP-клиент | Desktop 2.1.3; читает `opencode.json` из корня проекта |
| **GitHub** | Хостинг репозитория | `47Rubles/docx-agent` (публичный) |
| **GitHub Actions** | CI | `ci.yml`: тесты, сканер утечек, проверка MCP, smoke-тест |
| **GitHub Secrets** | Хранение ключа для CI | Секрет `LLM_API_KEY` |
| **Прокси** | Доступ к Groq с этой машины | `http://127.0.0.1:7890` (без прокси Groq отдаёт 403 — гео-блок) |

---

## 5. Инструменты продукта

### 5.1 MCP-инструменты (`src/interfaces/mcp_server.py`)

| Инструмент | Что делает | Нужен ли LLM-ключ |
|---|---|---|
| `docx_validate_ast(ast_json)` | Проверяет AST по схеме Pydantic, отдаёт отчёт об ошибках | нет |
| `docx_compile(ast_json, output_path)` | Собирает `.docx` из готового AST | нет |
| `docx_interview(prompt)` | Предполётный анализ ТЗ: список уточняющих вопросов | нет |
| `docx_generate(prompt, output_path, provider, model)` | Полный цикл: ТЗ → AST → `.docx` | да |

Все выходные пути ограничены рабочей директорией сервера и должны заканчиваться
на `.docx` — это граница безопасности, потому что инструментами управляет модель.

### 5.2 Команды CLI (`src/cli.py`)

| Команда | Что делает |
|---|---|
| `python -m src.cli generate "<ТЗ>" --output report.docx` | Полный цикл через LLM (флаги `--provider`, `--model`, `--skip-questions`) |
| `python -m src.cli from-json ast.json --output report.docx` | Офлайн-сборка из готового AST, **без ключа** |

---

## 6. Модули проекта

| Модуль | Роль |
|---|---|
| `src/models/ast_schema.py` | Схема Document AST: `DocumentAST`, `Section`, `BlockUnion`, валидация таблиц и id |
| `src/core/ast_normalizer.py` | Приведение ответа модели к схеме: лишние поля, ширины таблиц, уровни заголовков, объединения ячеек |
| `src/core/docx_compiler.py` | Фасад сборки документа |
| `src/core/table_builder.py` | Таблицы: ширины в процентах, `gridSpan`/`vMerge`, повтор шапки, зебра |
| `src/core/callout_builder.py` | Врезки: акцентная левая граница, заливка |
| `src/core/toc_builder.py` | Поле TOC, колонтитулы, `updateFields` |
| `src/core/omml_converter.py` | Формулы: LaTeX → MathML → OMML, изоляция сбоев |
| `src/core/revision_engine.py` | Режим track changes в настройках документа |
| `src/core/settings.py` | Загрузка конфигурации, разрешение `${ПЕРЕМЕННАЯ}`, маскирование секретов |
| `src/agents/interviewer.py` | Агент-Интервьюер: эвристические вопросы по ТЗ |
| `src/agents/planner.py` | Агент-Архитектор: LLM → валидный AST, до двух попыток починки JSON |
| `src/agents/state_machine.py` | Граф оркестрации диалога и сборки |
| `src/agents/synthesizer.py` | Синтезатор контента разделов (заготовка) |
| `src/interfaces/mcp_server.py` | MCP-сервер: четыре инструмента поверх пайплайна |
| `src/interfaces/cli.py` | Консольный интерфейс |
| `src/config.py` | Провайдер, модель, лимиты, разрешение ключа из окружения |
| `config/settings.yaml` | Единый конфиг: профиль провайдера, лимиты генерации, пути |

---

## 7. Ассеты

| Файл | Назначение |
|---|---|
| `assets/templates/default.docx` | Базовый шаблон оформления (стили, оглавление, колонтитулы) |
| `assets/xslt/MML2OMML.XSL` | Маппинг MathML → OMML; ограниченный набор конструкций |

---

## 8. Контроль качества и разработка

| Инструмент | Назначение |
|---|---|
| `pytest` | 58 тестов: компилятор, формулы, расширения, MCP-инструменты, конфигурация, зависимости, нормализация AST, устойчивость планировщика |
| `scripts/check_secrets.py` | Поиск похожих на ключи строк в отслеживаемых файлах, проверка `.env` вне индекса |
| `scripts/check_mcp.py` | Поднимает MCP-сервер и проверяет, что отдаёт все четыре инструмента |
| `scripts/smoke_test.py` | Живой запрос к LLM-провайдеру; без ключа завершается кодом 0 с пометкой «пропущено» |
| `scripts/set-api-key.ps1` | Безопасная настройка ключа: `Read-Host -AsSecureString` → переменная уровня User |
| GitHub Actions | `ci.yml`: установка зависимостей → сканер утечек → `pytest` → проверка MCP → smoke-тест |
| `git`, `gh CLI` | Версионирование, публикация, авторизация на GitHub |
| Тест полноты `requirements.txt` | Сверяет все сторонние импорты проекта с списком зависимостей |

---

## 9. Что пока не реализовано

Зафиксировано по итогам аудита (`REVIEW_REPORT.md`):

- RAG и векторный контекст для агента-Архитектора;
- разделение Planner/Synthesizers и параллельная генерация разделов;
- дифференциальные правки AST с реальными `w:ins` / `w:del`;
- поддержка шаблонов `.dotx` и интерфейс бота;
- полный официальный XSLT MathML → OMML (в комплекте ограниченный преобразователь);
- строгая валидация ECMA-376 и нагрузочный benchmark (3,5 секунды / 50 страниц).

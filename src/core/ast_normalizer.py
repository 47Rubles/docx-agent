"""Нормализация ответа модели к схеме Document AST.

Модель почти всегда выдаёт «почти-валидный» JSON. Типичные расхождения:

* лишние поля — схема запрещает их (``extra='forbid'``), и любая новая
  деталь в ответе модели ломает валидацию;
* ширины колонок таблицы не дают 100 % или их нет вовсе;
* объединённые ячейки вылезают за границы таблицы или пересекаются;
* уровень заголовка глубже третьего;
* неизвестный тип блока.

Часть этих ошибок однозначна и чинится без участия модели. Здесь они
исправляются, а к модели уходит только то, что она способна решить
смысловым текстом: расхождения в содержании разделов.

Принцип деградации: блок, который не приводится к корректному виду,
заменяется ближайшим корректным эквивалентом (например, таблица теряет
объединения, но остаётся таблицей), а не выбрасывается целиком.
"""

from __future__ import annotations

from typing import Any

MAX_HEADING_LEVEL = 3

BLOCK_TYPES = ('paragraph', 'formula', 'table', 'callout')
CALLOUT_TYPES = ('info', 'warning', 'critical', 'success')
ALIGN_VALUES = ('left', 'center', 'right')

_METADATA_FIELDS = (
    'title', 'subtitle', 'author', 'version', 'template_name',
    'enable_toc', 'enable_track_changes',
)
_SECTION_FIELDS = ('id', 'title', 'level', 'blocks')
_PARAGRAPH_FIELDS = ('type', 'text', 'style', 'runs', 'bold', 'italic')
_FORMULA_FIELDS = ('type', 'latex', 'display_mode')
_TABLE_FIELDS = ('type', 'headers', 'rows', 'col_widths', 'zebra_striping', 'caption')
_CALLOUT_FIELDS = ('type', 'callout_type', 'title', 'text')
_RUN_FIELDS = ('text', 'bold', 'italic', 'code')
_CELL_FIELDS = ('text', 'bold', 'italic', 'align', 'col_span', 'row_span')


def _keep(source: dict, allowed: tuple[str, ...]) -> dict:
    """Оставляет только разрешённые поля — схема запрещает лишние."""
    return {key: value for key, value in source.items() if key in allowed}


def _as_text(value: Any, default: str = '') -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_metadata(raw: Any) -> dict:
    source = raw if isinstance(raw, dict) else {}
    metadata = {
        'title': _as_text(source.get('title')).strip() or 'Документ',
        'subtitle': _as_text(source.get('subtitle')),
        'author': _as_text(source.get('author')),
        'version': _as_text(source.get('version')).strip() or '1.0',
        'template_name': _as_text(source.get('template_name')).strip() or 'default.docx',
        'enable_toc': _as_bool(source.get('enable_toc'), True),
        'enable_track_changes': _as_bool(source.get('enable_track_changes'), False),
    }
    return _keep(metadata, _METADATA_FIELDS)


def _normalize_run(raw: Any) -> dict:
    source = raw if isinstance(raw, dict) else {}
    return {
        'text': _as_text(source.get('text')),
        'bold': _as_bool(source.get('bold')),
        'italic': _as_bool(source.get('italic')),
        'code': _as_bool(source.get('code')),
    }


def _normalize_paragraph(raw: dict) -> dict:
    runs = raw.get('runs')
    normalized = {
        'type': 'paragraph',
        'text': _as_text(raw.get('text')),
        'style': _as_text(raw.get('style')).strip() or 'Normal',
        'runs': [_normalize_run(run) for run in runs if isinstance(run, dict)] if isinstance(runs, list) else [],
        'bold': _as_bool(raw.get('bold')),
        'italic': _as_bool(raw.get('italic')),
    }
    return _keep(normalized, _PARAGRAPH_FIELDS)


def _normalize_formula(raw: dict) -> dict | None:
    latex = _as_text(raw.get('latex')).strip()
    if not latex:
        return None
    display_mode = raw.get('display_mode', raw.get('mode'))
    normalized = {
        'type': 'formula',
        'latex': latex,
        'display_mode': display_mode if display_mode in ('inline', 'block') else 'block',
    }
    return _keep(normalized, _FORMULA_FIELDS)


def _normalize_cell(raw: Any) -> dict:
    source = raw if isinstance(raw, dict) else {}
    align = source.get('align')
    normalized = {
        'text': _as_text(source.get('text')),
        'bold': _as_bool(source.get('bold')),
        'italic': _as_bool(source.get('italic')),
        'align': align if align in ALIGN_VALUES else 'left',
        'col_span': max(1, _as_int(source.get('col_span'), 1)),
        'row_span': max(1, _as_int(source.get('row_span'), 1)),
    }
    return _keep(normalized, _CELL_FIELDS)


def _normalize_table(raw: dict) -> dict | None:
    headers = raw.get('headers')
    if not isinstance(headers, list) or not headers:
        return None
    header_texts = [_as_text(header).strip() for header in headers]
    if not any(header_texts):
        return None
    column_count = len(header_texts)

    raw_rows = raw.get('rows')
    rows: list[list[dict]] = []
    if isinstance(raw_rows, list):
        for raw_row in raw_rows:
            if not isinstance(raw_row, list):
                continue
            rows.append([_normalize_cell(cell) for cell in raw_row])

    # Ширины: пересчитываем, если их нет или они не дают ровно 100 %.
    widths = raw.get('col_widths')
    if not isinstance(widths, list) or len(widths) != column_count:
        widths = [100 / column_count] * column_count
    else:
        widths = [float(width) for width in widths if isinstance(width, (int, float))]
        if len(widths) != column_count or abs(sum(widths) - 100) > 0.01:
            widths = [100 / column_count] * column_count

    _repair_spans(rows, column_count)

    normalized = {
        'type': 'table',
        'headers': header_texts,
        'rows': rows,
        'col_widths': widths,
        'zebra_striping': _as_bool(raw.get('zebra_striping'), True),
        'caption': raw.get('caption') if isinstance(raw.get('caption'), str) else None,
    }
    return _keep(normalized, _TABLE_FIELDS)


def _repair_spans(rows: list[list[dict]], column_count: int) -> None:
    """Гасит объединения, которые вылезают за границы или пересекаются.

    Объединение — украшение; его потеря не ломает документ, а вот
    некорректная геометрия ломает всю сборку.
    """
    occupied: set[tuple[int, int]] = set()
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while column < column_count and (row_index, column) in occupied:
                column += 1
            col_span = cell['col_span']
            row_span = cell['row_span']
            out_of_bounds = (
                column + col_span > column_count
                or row_index + row_span > len(rows)
            )
            coords = {
                (r, c)
                for r in range(row_index, row_index + row_span)
                for c in range(column, column + col_span)
            }
            if out_of_bounds or occupied.intersection(coords):
                cell['col_span'] = 1
                cell['row_span'] = 1
                col_span = 1
                row_span = 1
                coords = {(row_index, column)}
            occupied.update(coords)
            column += col_span


def _normalize_callout(raw: dict) -> dict:
    callout_type = raw.get('callout_type')
    normalized = {
        'type': 'callout',
        'callout_type': callout_type if callout_type in CALLOUT_TYPES else 'info',
        'title': _as_text(raw.get('title')),
        'text': _as_text(raw.get('text')),
    }
    return _keep(normalized, _CALLOUT_FIELDS)


def _normalize_block(raw: Any) -> dict | None:
    """Приводит блок к одному из поддерживаемых типов или отбрасывает его."""
    if not isinstance(raw, dict):
        return None
    block_type = raw.get('type')
    if block_type == 'paragraph':
        return _normalize_paragraph(raw)
    if block_type == 'formula':
        return _normalize_formula(raw)
    if block_type == 'table':
        return _normalize_table(raw)
    if block_type == 'callout':
        return _normalize_callout(raw)

    # Неизвестный тип: сохраняем текст как обычный абзац, чтобы содержимое
    # не потерялось.
    text = _as_text(raw.get('text')) or _as_text(raw.get('latex')) or _as_text(raw.get('title'))
    if not text.strip():
        return None
    return _normalize_paragraph({**raw, 'type': 'paragraph', 'text': text})


def _normalize_section(raw: Any, index: int) -> dict:
    source = raw if isinstance(raw, dict) else {}
    raw_blocks = source.get('blocks')
    blocks = []
    if isinstance(raw_blocks, list):
        for raw_block in raw_blocks:
            block = _normalize_block(raw_block)
            if block is not None:
                blocks.append(block)
    level = min(max(_as_int(source.get('level'), 1), 1), MAX_HEADING_LEVEL)
    normalized = {
        'id': _as_text(source.get('id')).strip() or f'sec{index + 1}',
        'title': _as_text(source.get('title')).strip() or f'Раздел {index + 1}',
        'level': level,
        'blocks': blocks,
    }
    return _keep(normalized, _SECTION_FIELDS)


def normalize_document(payload: dict) -> dict:
    """Приводит разобранный ответ модели к виду, принимаемому схемой."""
    metadata = _normalize_metadata(payload.get('metadata'))

    raw_sections = payload.get('sections')
    sections = []
    if isinstance(raw_sections, list):
        for index, raw_section in enumerate(raw_sections):
            sections.append(_normalize_section(raw_section, index))

    if not sections:
        sections = [{
            'id': 'sec1',
            'title': 'Раздел 1',
            'level': 1,
            'blocks': [],
        }]

    # Идентификаторы разделов должны быть уникальными.
    seen: set[str] = set()
    for index, section in enumerate(sections):
        base = section['id']
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f'{base}-{suffix}'
            suffix += 1
        section['id'] = candidate
        seen.add(candidate)

    return {'metadata': metadata, 'sections': sections}

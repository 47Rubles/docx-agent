"""Нормализация ответа модели к схеме Document AST.

Каждый тест — реальная форма, в которой отвечает LLM.
"""

from __future__ import annotations

import pytest

from src.core.ast_normalizer import normalize_document
from src.models.ast_schema import DocumentAST


def test_extra_fields_are_dropped():
    """Схема запрещает лишние поля, и модель их добавляет постоянно."""
    payload = {
        'metadata': {'title': 'Отчёт', 'author': 'AI', 'unknown': 'лишнее'},
        'sections': [
            {
                'id': 's1',
                'title': 'Раздел',
                'level': 1,
                'blocks': [{'type': 'paragraph', 'text': 'текст', 'note': 'лишнее'}],
                'extra': 1,
            }
        ],
        'unexpected_root': True,
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    assert document.metadata.title == 'Отчёт'
    assert document.sections[0].blocks[0].text == 'текст'


def test_table_widths_are_recomputed():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [
            {
                'id': 's1',
                'title': 'Раздел',
                'level': 1,
                'blocks': [
                    {
                        'type': 'table',
                        'headers': ['A', 'B'],
                        'rows': [[{'text': '1'}, {'text': '2'}]],
                        'col_widths': [30, 30],
                    }
                ],
            }
        ],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    table = document.sections[0].blocks[0]
    assert abs(sum(table.col_widths) - 100) < 0.01
    assert len(table.col_widths) == 2


def test_table_without_widths_gets_even_split():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [
            {
                'id': 's1',
                'title': 'Раздел',
                'level': 1,
                'blocks': [
                    {
                        'type': 'table',
                        'headers': ['A', 'B', 'C', 'D'],
                        'rows': [[{'text': '1'}, {'text': '2'}, {'text': '3'}, {'text': '4'}]],
                    }
                ],
            }
        ],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    table = document.sections[0].blocks[0]
    assert len(table.col_widths) == 4
    assert abs(sum(table.col_widths) - 100) < 0.01


def test_overspanning_cell_loses_merge_but_table_survives():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [
            {
                'id': 's1',
                'title': 'Раздел',
                'level': 1,
                'blocks': [
                    {
                        'type': 'table',
                        'headers': ['A', 'B'],
                        'rows': [[{'text': 'широкая', 'col_span': 5}, {'text': '2'}]],
                        'col_widths': [50, 50],
                    }
                ],
            }
        ],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    table = document.sections[0].blocks[0]
    assert table.rows[0][0].col_span == 1


def test_heading_level_is_clamped():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [{'id': 's1', 'title': 'Раздел', 'level': 7, 'blocks': []}],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    assert document.sections[0].level == 3


def test_unknown_block_type_becomes_paragraph():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [
            {
                'id': 's1',
                'title': 'Раздел',
                'level': 1,
                'blocks': [{'type': 'diagram', 'text': 'описание схемы'}],
            }
        ],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    block = document.sections[0].blocks[0]
    assert block.type == 'paragraph'
    assert block.text == 'описание схемы'


def test_duplicate_section_ids_are_made_unique():
    payload = {
        'metadata': {'title': 'Отчёт'},
        'sections': [
            {'id': 's1', 'title': 'Первый', 'level': 1, 'blocks': []},
            {'id': 's1', 'title': 'Второй', 'level': 1, 'blocks': []},
        ],
    }
    document = DocumentAST.model_validate(normalize_document(payload))
    ids = [section.id for section in document.sections]
    assert len(ids) == len(set(ids))


def test_missing_metadata_gets_defaults():
    payload = {'sections': [{'id': 's1', 'title': 'Раздел', 'level': 1, 'blocks': []}]}
    document = DocumentAST.model_validate(normalize_document(payload))
    assert document.metadata.title
    assert document.metadata.enable_toc is True


def test_document_without_sections_is_repaired():
    payload = {'metadata': {'title': 'Отчёт'}, 'sections': []}
    document = DocumentAST.model_validate(normalize_document(payload))
    assert len(document.sections) == 1


@pytest.mark.parametrize(
    'payload',
    [
        {'metadata': {'title': 'Отчёт'}, 'sections': [{'id': 's1', 'title': 'Р', 'level': 1,
                                                      'blocks': [{'type': 'formula', 'latex': 'E=mc^2'}]}]},
        {'metadata': {'title': 'Отчёт'}, 'sections': [{'id': 's1', 'title': 'Р', 'level': 1,
                                                      'blocks': [{'type': 'callout', 'callout_type': 'info',
                                                                   'title': 'T', 'text': 'X'}]}]},
    ],
)
def test_typical_valid_documents_survive(payload):
    document = DocumentAST.model_validate(normalize_document(payload))
    assert document.sections

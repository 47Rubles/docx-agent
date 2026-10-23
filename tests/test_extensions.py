"""Regression for unsupported commands observed on Windows."""
from zipfile import ZipFile
from docx import Document
from src.models.ast_schema import DocumentAST
from src.core.docx_compiler import compile_document


def test_new_ast_spans_and_runs(tmp_path):
    ast = DocumentAST.model_validate({'metadata': {'title': 'Тест', 'enable_track_changes': True}, 'sections': [{'id': '1', 'title': '1. Раздел', 'level': 1, 'blocks': [
        {'type': 'paragraph', 'runs': [{'text': 'Важно: ', 'bold': True}, {'text': 'значение', 'italic': True}]},
        {'type': 'table', 'headers': ['A', 'B', 'C'], 'col_widths': [30, 30, 40], 'rows': [
            [{'text': 'Объединено', 'col_span': 2}, {'text': 'X'}],
            [{'text': 'Вертикально', 'row_span': 2}, {'text': '1'}, {'text': '2'}],
            [{'text': '3'}, {'text': '4'}]]},
        {'type': 'callout', 'callout_type': 'critical', 'title': 'Риск', 'text': 'Тест'},
        {'type': 'formula', 'latex': r'\unknownCommand{x}', 'display_mode': 'block'}
    ]}]})
    out = compile_document(ast, tmp_path / 'result.docx')
    document = Document(out)
    assert len(document.tables) == 2
    with ZipFile(out) as z:
        xml = z.read('word/document.xml'); settings = z.read('word/settings.xml')
        assert b'gridSpan' in xml and b'vMerge' in xml
        assert b'trackRevisions' in settings
        assert 'Формула не преобразована' in xml.decode()

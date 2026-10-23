"""Offline MCP tool tests: validation, compilation, interview, path safety."""
import json

import pytest

from src.interfaces.mcp_server import (
    _safe_output,
    docx_compile,
    docx_interview,
    docx_validate_ast,
)

AST_PATH = 'tests/fixtures/sample_ast.json'


@pytest.fixture()
def ast_json():
    return open(AST_PATH, encoding='utf-8').read()


def test_validate_accepts_sample(ast_json):
    report = json.loads(docx_validate_ast(ast_json))
    assert report['valid'] is True
    assert report['sections'] >= 1


def test_validate_reports_bad_json():
    report = json.loads(docx_validate_ast('{"metadata": nope'))
    assert report['valid'] is False
    assert report['errors']


def test_compile_builds_docx(ast_json, tmp_path, monkeypatch):
    # keep writes inside the current working directory for this tool
    monkeypatch.chdir(tmp_path)
    out = '_mcp_test.docx'
    result = json.loads(docx_compile(ast_json, out))
    assert result['bytes'] > 0
    assert (tmp_path / out).exists()


def test_interview_flags_missing_numbers():
    report = json.loads(docx_interview('Финансовый прогноз без вводных'))
    assert report['ready'] is False
    assert report['questions']


@pytest.mark.parametrize('bad', ['C:/Windows/evil.docx', '../up.docx', 'out.txt'])
def test_output_path_restricted(bad):
    with pytest.raises(ValueError):
        _safe_output(bad)


def test_generate_without_key_returns_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    from src.interfaces.mcp_server import docx_generate
    report = json.loads(docx_generate('Отчёт', '_x.docx', provider='groq'))
    assert 'GROQ_API_KEY' in report['error']

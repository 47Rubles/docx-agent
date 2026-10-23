"""MCP server: DocxGen Agent tools over stdio.

Exposes the document pipeline to any MCP client (OpenCode, Claude Desktop, ...):
  docx_validate_ast - offline JSON AST validation (Pydantic v2)
  docx_compile      - offline AST -> DOCX compilation
  docx_interview    - offline preflight questions for a prompt
  docx_generate     - full LLM pipeline (Groq / Anthropic) -> DOCX

Run: python -m src.interfaces.mcp_server
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from src.agents.interviewer import analyze_requirements
from src.agents.planner import plan_document
from src.core.docx_compiler import compile_document
from src.models.ast_schema import DocumentAST

#: Абсолютный путь в соглашении Windows: диск («C:\…») или UNC («\\server\share»).
#: На POSIX такой путь считается относительным, поэтому его нужно проверять явно.
_WINDOWS_ABSOLUTE = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\)')

#: Хост — POSIX? Вынесено в константу, чтобы поведение можно было проверить
#: тестом на любой платформе (подменять os.name нельзя: pathlib выбирает
#: реализацию путей при импорте и после подмены ломается).
_IS_POSIX = os.name != 'nt'

server = MCPServer(
    name='docx-agent',
    instructions=(
        'DocxGen Agent: build professional Word (.docx) documents from a strict '
        'Document AST. Use docx_validate_ast to check JSON, docx_compile to '
        'render a validated AST, docx_interview to preflight a prompt, and '
        'docx_generate for the full LLM pipeline (needs GROQ_API_KEY or '
        'ANTHROPIC_API_KEY in the server environment).'
    ),
)

def _safe_output(output_path: str) -> Path:
    """Resolve an output path and confine writes to the working directory."""
    root = Path.cwd().resolve()
    raw = output_path.strip()
    if not raw:
        raise ValueError('Output path must not be empty')

    if _IS_POSIX and _WINDOWS_ABSOLUTE.match(raw):
        # На POSIX путь вида C:\Windows\evil.docx считается относительным и
        # прошёл бы проверку вхождения в рабочую директорию, хотя запрошен
        # абсолютный путь Windows. Отвергаем такой путь явно.
        raise ValueError(
            f'Output path must stay inside the working directory {root}: {output_path}')

    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if root not in resolved.parents and resolved != root:
        raise ValueError(
            f'Output path must stay inside the working directory {root}: {output_path}')
    if resolved.suffix.lower() != '.docx':
        raise ValueError('Output path must end with .docx')
    return resolved


def _load_ast(ast_json: str) -> DocumentAST:
    try:
        return DocumentAST.model_validate_json(ast_json)
    except Exception as exc:  # pydantic ValidationError and JSON parse errors
        raise ValueError(f'Invalid Document AST: {exc}') from exc


@server.tool()
def docx_validate_ast(ast_json: str) -> str:
    """Validate a Document AST JSON string against the strict Pydantic schema.

    Returns a JSON report: {"valid": true, "title": ...} on success or
    {"valid": false, "errors": [...]} with human-readable validation details.
    """
    try:
        ast = _load_ast(ast_json)
    except ValueError as exc:
        return json.dumps({'valid': False, 'errors': [str(exc)]}, ensure_ascii=False)
    return json.dumps({
        'valid': True,
        'title': ast.metadata.title,
        'sections': len(ast.sections),
    }, ensure_ascii=False)


@server.tool()
def docx_compile(ast_json: str, output_path: str = 'output.docx') -> str:
    """Compile a Document AST JSON string into a Word .docx file (offline).

    Output must stay inside the working directory and end with .docx.
    Returns JSON {"output": "<absolute path>", "bytes": <size>}.
    """
    ast = _load_ast(ast_json)
    output = _safe_output(output_path)
    result = compile_document(ast, output)
    return json.dumps({'output': str(result), 'bytes': result.stat().st_size},
                      ensure_ascii=False)


@server.tool()
def docx_interview(prompt: str) -> str:
    """Preflight analysis of a document brief (offline heuristic).

    Returns JSON {"ready": bool, "questions": [...]} - clarifying questions to
    ask the user before generation when critical gaps are detected.
    """
    result = analyze_requirements(prompt)
    return json.dumps({'ready': result.is_ready, 'questions': result.questions},
                      ensure_ascii=False)


@server.tool()
def docx_generate(prompt: str, output_path: str = 'output.docx',
                  provider: str | None = None, model: str | None = None) -> str:
    """Full pipeline: LLM prompt -> validated Document AST -> .docx.

    provider: 'groq' or 'anthropic' (default from DOCX_LLM_PROVIDER env).
    model: provider model id; defaults to the provider's default model.
    Requires GROQ_API_KEY or ANTHROPIC_API_KEY in the server environment.
    Returns JSON {"output": "<path>", "bytes": <size>} on success or
    {"error": "..."} when the key is missing or the LLM pipeline fails.
    """
    try:
        output = _safe_output(output_path)
        ast = plan_document(prompt, model=model, provider=provider)
        result = compile_document(ast, output)
    except ValueError as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=False)
    return json.dumps({'output': str(result), 'bytes': result.stat().st_size},
                      ensure_ascii=False)


if __name__ == '__main__':
    server.run(transport='stdio')

from pathlib import Path
import typer
from src.agents.interviewer import analyze_requirements
from src.agents.planner import plan_document
from src.models.ast_schema import DocumentAST
from src.core.docx_compiler import compile_document

app = typer.Typer(help='Document AST -> professional Word documents')

@app.command()
def generate(prompt: str, output: Path = typer.Option(Path('output.docx'),'--output','-o'), model: str = typer.Option(None,'--model'), provider: str = typer.Option(None,'--provider', help='anthropic or groq'), skip_questions: bool = typer.Option(False,'--skip-questions')):
    if not skip_questions:
        result = analyze_requirements(prompt)
        if not result.is_ready:
            typer.echo('Уточните ТЗ:\n'+'\n'.join(f'- {q}' for q in result.questions))
            raise typer.Exit(2)
    ast = plan_document(prompt, model=model, provider=provider)
    compile_document(ast, output)
    typer.echo(f'Готово: {output}')

@app.command('from-json')
def from_json(source: Path, output: Path = typer.Option(Path('output.docx'),'--output','-o')):
    ast = DocumentAST.model_validate_json(source.read_text(encoding='utf-8'))
    compile_document(ast,output)
    typer.echo(f'Готово: {output}')

if __name__ == '__main__': app()

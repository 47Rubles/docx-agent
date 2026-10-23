from zipfile import ZipFile
from docx import Document
from pydantic import ValidationError
import pytest
from src.models.ast_schema import DocumentAST
from src.core.docx_compiler import compile_document


def sample(blocks):
    return {'metadata':{'title':'Проверка','author':'QA','enable_toc':False,'enable_track_changes':True},'sections':[{'id':'s1','title':'1. Тест','level':1,'blocks':blocks}]}


def test_runs_and_critical_callout(tmp_path):
    ast=DocumentAST.model_validate(sample([{'type':'paragraph','runs':[{'text':'Термин','bold':True},{'text':' — определение'}]},{'type':'callout','callout_type':'critical','title':'Риск','text':'Проверка'}]))
    path=compile_document(ast,tmp_path/'runs.docx')
    d=Document(path)
    assert any(r.bold for p in d.paragraphs for r in p.runs)
    with ZipFile(path) as z:
        assert b'trackRevisions' in z.read('word/settings.xml')
        assert b'D32F2F' in z.read('word/document.xml')


def test_merge_and_bad_formula_fallback(tmp_path):
    ast=DocumentAST.model_validate(sample([{'type':'table','headers':['A','B','C'],'col_widths':[40,30,30],'rows':[[{'text':'Merged','col_span':2},{'text':'C'}],[{'text':'A'},{'text':'B'},{'text':'C'}]]},{'type':'formula','latex':r'\\broken{invalid','display_mode':'block'}]))
    path=compile_document(ast,tmp_path/'merge.docx')
    with ZipFile(path) as z:
        xml=z.read('word/document.xml')
        assert b'gridSpan' in xml
        assert 'Формула не преобразована'.encode() in xml


def test_invalid_table_widths_rejected():
    with pytest.raises(ValidationError):
        DocumentAST.model_validate(sample([{'type':'table','headers':['A','B'],'col_widths':[50,40],'rows':[]}]))

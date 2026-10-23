from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from docx import Document
from src.models.ast_schema import DocumentAST
from src.core.docx_compiler import compile_document

SAMPLE = {
 'title':'Демонстрационный аналитический отчёт','author':'Docx Agent','enable_toc':True,
 'sections':[{'id':'intro','title':'Обзор','level':1,'blocks':[
 {'type':'paragraph','text':'Пример автоматически сформированного документа с таблицей, формулой и информационной врезкой.'},
 {'type':'formula','latex':r'E = mc^2','mode':'display'},
 {'type':'callout','callout_type':'info','title':'Примечание','text':'Все данные ниже демонстрационные.'},
 {'type':'table','headers':['Показатель','2025','2026'],'rows':[
 [{'text':'Объём'},{'text':'120'},{'text':'145','bold':True}],
 [{'text':'Темп роста'},{'text':'—'},{'text':'20,8 %'}],
 [{'text':'Статус'},{'text':'Базовый'},{'text':'Плановый'}]],
 'col_widths':[50,25,25],'zebra_striping':True,'caption':'Таблица 1. Условные показатели'}
 ]},{'id':'conclusion','title':'Заключение','level':1,'blocks':[
 {'type':'paragraph','text':'Прототип успешно формирует основные элементы документа.'}]}]
}

def test_compiler(tmp_path):
    ast=DocumentAST.model_validate(SAMPLE)
    out=compile_document(ast,tmp_path/'output_sample.docx')
    assert out.exists()
    assert len(Document(out).tables)==2
    with ZipFile(out) as z:
        xml=z.read('word/document.xml')
        settings=z.read('word/settings.xml')
        assert b'oMath' in xml and b'tblHeader' in xml and b'cantSplit' in xml
        assert b'updateFields' in settings and b'TOC' in xml
        etree.fromstring(xml)

def test_sample_export():
    compile_document(DocumentAST.model_validate(SAMPLE),Path(__file__).resolve().parents[1]/'output_sample.docx')

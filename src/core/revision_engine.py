"""Paragraph-level tracked changes on DOCX, with explicit old/new content."""
from datetime import datetime, timezone
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def apply_paragraph_revision(paragraph, old_text: str, new_text: str, author: str='AI Agent', revision_id: int=1):
    """Replace paragraph content with w:del and w:ins, preserving no previous rich formatting."""
    for child in list(paragraph._p):
        if child.tag != qn('w:pPr'): paragraph._p.remove(child)
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for tag, text, ident in (('del',old_text,revision_id),('ins',new_text,revision_id+1)):
        node=OxmlElement('w:'+tag)
        for k,v in {'w:id':str(ident),'w:author':author,'w:date':stamp}.items(): node.set(qn(k),v)
        run=OxmlElement('w:r'); t=OxmlElement('w:delText' if tag=='del' else 'w:t'); t.text=text
        t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        run.append(t); node.append(run); paragraph._p.append(node)
    return paragraph

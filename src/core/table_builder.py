from docx.shared import Twips
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH


def _element(parent, name, **attrs):
    el = parent.find(qn(name))
    if el is None:
        el = OxmlElement(name); parent.append(el)
    for key, value in attrs.items(): el.set(qn(key), str(value))
    return el


def build_table(doc, block):
    n = len(block.headers)
    table = doc.add_table(rows=len(block.rows)+1, cols=n)
    table.style = 'Table Grid'; table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    sec = doc.sections[-1]
    usable_twips = int((sec.page_width-sec.left_margin-sec.right_margin)/635)
    widths = [round(usable_twips*w/100) for w in block.col_widths]
    widths[-1] += usable_twips-sum(widths)
    tblpr = table._tbl.tblPr
    _element(tblpr,'w:tblW',**{'w:w':usable_twips,'w:type':'dxa'})
    for grid, width in zip(table._tbl.tblGrid.gridCol_lst,widths): grid.set(qn('w:w'),str(width))
    for idx,row in enumerate(table.rows):
        trpr = row._tr.get_or_add_trPr(); _element(trpr,'w:cantSplit')
        if idx==0: _element(trpr,'w:tblHeader',**{'w:val':'true'})
        for j,cell in enumerate(row.cells):
            cell.width = Twips(widths[j]); _element(cell._tc.get_or_add_tcPr(),'w:tcW',**{'w:w':widths[j],'w:type':'dxa'})
            if idx==0: _element(cell._tc.get_or_add_tcPr(),'w:shd',**{'w:fill':'DCE7F5'})
            elif block.zebra_striping and idx%2==0: _element(cell._tc.get_or_add_tcPr(),'w:shd',**{'w:fill':'F4F5F7'})
    for j,value in enumerate(block.headers):
        table.cell(0,j).text=value
        for run in table.cell(0,j).paragraphs[0].runs: run.bold=True
    occupied = {}  # (row,col) -> remaining span bookkeeping
    for ri,data in enumerate(block.rows, start=1):
        col = 0
        for item in data:
            while col<n and (ri,col) in occupied: col += 1
            if col>=n or col+item.col_span>n: raise ValueError('Invalid table cell span')
            cell = table.cell(ri,col)
            target = table.cell(ri+item.row_span-1,col+item.col_span-1) if ri+item.row_span-1<len(table.rows) else None
            if target is None: raise ValueError('row_span extends beyond table')
            if item.col_span>1 or item.row_span>1:
                for rr in range(ri,ri+item.row_span):
                    for cc in range(col,col+item.col_span):
                        if (rr,cc)!=(ri,col): occupied[(rr,cc)]=True
                cell = cell.merge(target)
            cell.text=item.text
            cell.paragraphs[0].alignment={'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,'right':WD_ALIGN_PARAGRAPH.RIGHT}[item.align]
            for run in cell.paragraphs[0].runs: run.bold=item.bold; run.italic=item.italic
            col += item.col_span
    if block.caption: doc.add_paragraph(block.caption,style='Caption')
    return table

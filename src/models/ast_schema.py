from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Metadata(StrictModel):
    title: str = Field(min_length=1)
    subtitle: str = ''
    author: str = ''
    version: str = '1.0'
    template_name: str = 'default.docx'
    enable_toc: bool = True
    enable_track_changes: bool = False

class TextRun(StrictModel):
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False

class ParagraphBlock(StrictModel):
    type: Literal['paragraph'] = 'paragraph'
    text: str = ''
    style: str = 'Normal'
    runs: list[TextRun] = Field(default_factory=list)
    bold: bool = False
    italic: bool = False

class FormulaBlock(StrictModel):
    type: Literal['formula'] = 'formula'
    latex: str = Field(min_length=1)
    display_mode: Literal['inline','block'] = 'block'

class TableCell(StrictModel):
    text: str = ''
    bold: bool = False
    italic: bool = False
    align: Literal['left','center','right'] = 'left'
    col_span: int = Field(default=1,ge=1)
    row_span: int = Field(default=1,ge=1)

class TableBlock(StrictModel):
    type: Literal['table'] = 'table'
    headers: list[str] = Field(min_length=1)
    rows: list[list[TableCell]]
    col_widths: list[float]
    zebra_striping: bool = True
    caption: str | None = None

    @model_validator(mode='after')
    def check_dimensions(self):
        n = len(self.headers)
        if any(not x.strip() for x in self.headers):
            raise ValueError('Table headers cannot be empty')
        if len(self.col_widths) != n or any(v <= 0 for v in self.col_widths) or abs(sum(self.col_widths)-100) > .01:
            raise ValueError('col_widths must match headers and total 100%')
        occupied: set[tuple[int,int]] = set()
        for ri,row in enumerate(self.rows):
            col = 0
            for cell in row:
                while col < n and (ri,col) in occupied: col += 1
                if col + cell.col_span > n or ri + cell.row_span > len(self.rows):
                    raise ValueError('Cell spans exceed table boundaries')
                coords = {(r,c) for r in range(ri,ri+cell.row_span) for c in range(col,col+cell.col_span)}
                if occupied.intersection(coords): raise ValueError('Overlapping merged cells')
                occupied.update(coords)
                col += cell.col_span
        return self

class CalloutBlock(StrictModel):
    type: Literal['callout'] = 'callout'
    callout_type: Literal['info','warning','critical','success']
    title: str
    text: str

BlockUnion = Annotated[ParagraphBlock | FormulaBlock | TableBlock | CalloutBlock, Field(discriminator='type')]

class Section(StrictModel):
    id: str = Field(min_length=1)
    title: str
    level: int = Field(ge=1,le=3)
    blocks: list[BlockUnion] = Field(default_factory=list)

class DocumentAST(StrictModel):
    metadata: Metadata
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode='before')
    @classmethod
    def legacy(cls, data):
        if isinstance(data,dict) and 'metadata' not in data and 'title' in data:
            data = dict(data)
            data['metadata'] = {key:data.pop(key) for key in ('title','author','enable_toc') if key in data}
        if isinstance(data,dict):
            for s in data.get('sections',[]):
                for b in s.get('blocks',[]):
                    if b.get('type') == 'formula' and 'mode' in b:
                        b['display_mode'] = 'block' if b.pop('mode') == 'display' else 'inline'
                    if b.get('type') == 'table' and b.get('col_widths') is None:
                        b['col_widths'] = [100/len(b['headers'])]*len(b['headers'])
        return data

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [s.id for s in self.sections]
        if len(ids) != len(set(ids)): raise ValueError('Section IDs must be unique')
        return self

    @property
    def title(self): return self.metadata.title
    @property
    def author(self): return self.metadata.author
    @property
    def enable_toc(self): return self.metadata.enable_toc

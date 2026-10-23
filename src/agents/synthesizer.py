"""Validated section synthesis adapter; use model-generated section JSON."""
from src.models.ast_schema import Section

def validate_synthesized_section(payload: dict)->Section:
    return Section.model_validate(payload)

"""Offline deterministic stages; RAG and synthesis are explicit optional integrations."""
from enum import Enum
class State(str,Enum):
    INTERVIEW='INTERVIEW'
    RAG_RETRIEVAL='RAG_RETRIEVAL'
    PLANNING='PLANNING'
    SYNTHESIS='SYNTHESIS'
    AST_VALIDATION='AST_VALIDATION'
    REPAIR_AST='REPAIR_AST'
    COMPILATION='COMPILATION'
    REVISION='REVISION'

TRANSITIONS={
 State.INTERVIEW:{State.RAG_RETRIEVAL}, State.RAG_RETRIEVAL:{State.PLANNING},
 State.PLANNING:{State.SYNTHESIS},State.SYNTHESIS:{State.AST_VALIDATION},
 State.AST_VALIDATION:{State.COMPILATION,State.REPAIR_AST},
 State.REPAIR_AST:{State.AST_VALIDATION},State.COMPILATION:{State.REVISION},State.REVISION:set()
}
def transition(current:State,next_state:State)->State:
    if next_state not in TRANSITIONS[current]: raise ValueError(f'Invalid transition: {current} -> {next_state}')
    return next_state

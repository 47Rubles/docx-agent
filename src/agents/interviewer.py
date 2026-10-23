from dataclasses import dataclass
import re

@dataclass
class InterviewResult:
    is_ready: bool
    questions: list[str]

def analyze_requirements(prompt: str) -> InterviewResult:
    """Heuristic preflight; absence of numbers is only a problem for quantitative briefs."""
    questions = []
    p = prompt.lower()
    if not any(s in p for s in ('отчёт','отчет','договор','инструкция','план','предложение','статья','report','proposal','memo','документ')):
        questions.append('Какой тип документа нужно подготовить?')
    if not any(s in p for s in ('для руковод','для клиент','для сотруд','для студент','для инвестор','аудитори','читател','for managers','for clients','audience')):
        questions.append('Кто целевая аудитория документа?')
    if any(s in p for s in ('бюджет','финанс','прогноз','выручк','стоимост','budget','revenue','forecast')) and not re.search(r'\d',p):
        questions.append('Какие числовые вводные и допущения необходимо использовать?')
    return InterviewResult(not questions, questions[:4])

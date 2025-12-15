from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

from app.utils.text_norm import normalize_answer
from app.utils.similarity import similarity_score

class Verdict(str, Enum):
    OK = "OK"
    ALMOST = "ALMOST"
    BAD = "BAD"

@dataclass(frozen=True)
class GradeResult:
    score: int
    verdict: Verdict
    best_match: str

def grade(user_text: str, correct_text: str, alt_answers: list[str], ok: int, almost: int) -> GradeResult:
    u = normalize_answer(user_text or "")
    candidates = [correct_text] + (alt_answers or [])
    best_score = -1
    best_match = correct_text
    for c in candidates:
        cn = normalize_answer(c or "")
        sc = similarity_score(u, cn)
        if sc > best_score:
            best_score = sc
            best_match = c
    if best_score >= ok:
        v = Verdict.OK
    elif best_score >= almost:
        v = Verdict.ALMOST
    else:
        v = Verdict.BAD
    return GradeResult(score=int(best_score), verdict=v, best_match=best_match)

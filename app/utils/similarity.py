from __future__ import annotations

from rapidfuzz import fuzz

def similarity_score(a: str, b: str) -> int:
    # 0..100
    return int(round(fuzz.ratio(a, b)))

from __future__ import annotations
import re

_PUNCT_RE = re.compile(r"[\.,!?;:\"“”\(\)\[\]\{\}—\-…]")
_APOS_RE = re.compile(r"[’`´]")

def normalize_answer(text: str) -> str:
    if text is None:
        return ""
    t = text.strip().lower()
    t = _APOS_RE.sub("'", t)
    t = _PUNCT_RE.sub(" ", t)
    # Remove any remaining stray punctuation-like chars
    t = re.sub(r"[^a-z0-9\s']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

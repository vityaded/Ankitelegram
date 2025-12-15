from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from typing import List, Tuple

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")

def _tokens(text: str) -> List[str]:
    if not text:
        return []
    return _WORD_RE.findall(text)

def highlight_diff(correct: str, user: str) -> tuple[str, str]:
    """Return (correct_html, user_html) with minimal markup.
    - In Correct: underline (<u>) words the user missed or got wrong.
    - In You: bold (<b>) extra/wrong words.
    """
    c = _tokens(correct)
    u = _tokens(user)

    c_low = [t.lower() for t in c]
    u_low = [t.lower() for t in u]

    sm = SequenceMatcher(a=c_low, b=u_low)
    c_out: list[str] = []
    u_out: list[str] = []

    def esc(t: str) -> str:
        return html.escape(t, quote=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for t in c[i1:i2]:
                c_out.append(esc(t))
            for t in u[j1:j2]:
                u_out.append(esc(t))
        elif tag == "delete":
            # present in correct, missing in user
            for t in c[i1:i2]:
                c_out.append(f"<u>{esc(t)}</u>")
        elif tag == "insert":
            # extra in user
            for t in u[j1:j2]:
                u_out.append(f"<b>{esc(t)}</b>")
        elif tag == "replace":
            for t in c[i1:i2]:
                c_out.append(f"<u>{esc(t)}</u>")
            for t in u[j1:j2]:
                u_out.append(f"<b>{esc(t)}</b>")

    return (" ".join(c_out).strip(), " ".join(u_out).strip())

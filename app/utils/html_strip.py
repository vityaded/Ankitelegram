from __future__ import annotations
import re
import html

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"(?i)<br\s*/?>")

def strip_html(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = _BR_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[\t\r]+", " ", s)
    s = re.sub(r"\n+", "\n", s)
    return s.strip()

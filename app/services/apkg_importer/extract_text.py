from __future__ import annotations
import re
from app.utils.html_strip import strip_html

SOUND_TAG_RE = re.compile(r"\[sound:[^\]]+\]", re.IGNORECASE)

def extract_answer_text(back_field: str) -> tuple[str, list[str]]:
    txt = strip_html(back_field or "")
    # Remove Anki sound tags if present in the back field.
    txt = SOUND_TAG_RE.sub("", txt).strip()

    if "||" in txt:
        parts = [p.strip() for p in txt.split("||") if p.strip()]
        if not parts:
            return "", []
        return parts[0], parts[1:]
    return txt.strip(), []

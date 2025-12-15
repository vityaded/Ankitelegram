from __future__ import annotations
import re

SOUND_RE = re.compile(r"\[sound:([^\]]+)\]", re.IGNORECASE)
VIDEO_SRC_RE = re.compile(r'(?i)(?:src|data-src)\s*=\s*["\']([^"\']+)["\']')

def find_media_names(text: str) -> list[str]:
    if not text:
        return []
    names = []
    for m in SOUND_RE.finditer(text):
        names.append(m.group(1).strip())
    # also HTML video/audio tags
    for m in VIDEO_SRC_RE.finditer(text):
        names.append(m.group(1).strip())
    # de-dup preserve order
    out = []
    seen = set()
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out

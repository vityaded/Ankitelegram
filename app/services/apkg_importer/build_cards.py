from __future__ import annotations

import json, hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services.apkg_importer.extract_media import find_media_names
from app.services.apkg_importer.extract_text import extract_answer_text
from app.utils.html_strip import strip_html

@dataclass
class CardDTO:
    note_guid: str
    answer_text: str
    alt_answers: list[str]
    filename: str
    media_bytes: bytes
    media_sha256: str
    media_kind: str  # "video" or "audio"

VIDEO_EXT = {".mp4",".webm",".mov",".mkv",".m4v"}
AUDIO_EXT = {".mp3",".m4a",".ogg",".wav",".flac"}

def _kind_from_filename(name: str) -> str:
    n = name.lower()
    for ext in VIDEO_EXT:
        if n.endswith(ext):
            return "video"
    for ext in AUDIO_EXT:
        if n.endswith(ext):
            return "audio"
    return "video"

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _load_media_map(media_path: Path) -> dict[str,str]:
    # media file is JSON mapping index->filename
    raw = media_path.read_text(encoding="utf-8")
    return json.loads(raw)

def _resolve_media_file(base_dir: Path, media_map: dict[str,str], name: str) -> tuple[str, bytes]:
    # Try direct filename
    direct = base_dir / name
    if direct.exists() and direct.is_file():
        return name, direct.read_bytes()

    # Sometimes media files are stored by numeric keys (0,1,2) with mapping to names
    # Find index that matches this filename
    idx = None
    for k, v in media_map.items():
        if v == name:
            idx = k
            break
    if idx is not None:
        p = base_dir / idx
        if p.exists() and p.is_file():
            return name, p.read_bytes()

    # If name itself is numeric
    p2 = base_dir / name
    if p2.exists() and p2.is_file():
        # try map it back to a filename for extension
        mapped_name = media_map.get(name, name)
        return mapped_name, p2.read_bytes()

    raise FileNotFoundError(f"Media not found for: {name}")

def build_cards_from_notes(
    base_dir: Path,
    notes: list[tuple[str,str]],
) -> list[CardDTO]:
    collection = base_dir / "collection.anki2"
    media_file = base_dir / "media"
    if not collection.exists():
        raise FileNotFoundError("collection.anki2 not found in apkg")
    if not media_file.exists():
        raise FileNotFoundError("media mapping file not found in apkg")

    media_map = _load_media_map(media_file)

    dtos: list[CardDTO] = []
    for guid, flds in notes:
        fields = flds.split("\x1f")
        # Find first field containing media reference
        media_field_idx = None
        media_names: list[str] = []
        for i, field in enumerate(fields):
            mn = find_media_names(field)
            if mn:
                media_field_idx = i
                media_names = mn
                break
        if not media_names:
            # skip notes without media
            continue

        # Pick first media reference only (one snippet per card)
        media_name = media_names[0]

        # Choose back field: prefer second field if exists and not the media field
        back_candidates = []
        if len(fields) >= 2:
            back_candidates.append(fields[1])
        # Add all fields except media field
        for i, field in enumerate(fields):
            if i != media_field_idx:
                back_candidates.append(field)

        answer_text = ""
        alt_answers: list[str] = []
        for cand in back_candidates:
            a, alts = extract_answer_text(cand)
            if a:
                answer_text, alt_answers = a, alts
                break

        if not answer_text:
            # invalid for our bot
            continue

        try:
            resolved_name, media_bytes = _resolve_media_file(base_dir, media_map, media_name)
        except FileNotFoundError:
            continue

        sha = _sha(media_bytes)
        kind = _kind_from_filename(resolved_name)

        dtos.append(CardDTO(
            note_guid=guid,
            answer_text=answer_text,
            alt_answers=alt_answers,
            filename=resolved_name,
            media_bytes=media_bytes,
            media_sha256=sha,
            media_kind=kind,
        ))

    return dtos

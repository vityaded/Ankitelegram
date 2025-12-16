from __future__ import annotations
import secrets

VALID_MODES = {"anki", "watch"}


def generate_deck_token() -> str:
    return secrets.token_urlsafe(18)


def build_payload(deck_token: str, mode: str = "anki") -> str:
    m = (mode or "anki").lower()
    if m not in VALID_MODES:
        m = "anki"
    return f"deck.{m}.{deck_token}"


def parse_payload(payload: str | None) -> tuple[str, str] | None:
    if not payload:
        return None
    if payload.startswith("deck_"):
        return payload[len("deck_"):], "anki"
    if payload.startswith("deck."):
        parts = payload.split(".", 2)
        if len(parts) != 3:
            return None
        mode = parts[1].lower()
        token = parts[2]
        if mode not in VALID_MODES or not token:
            return None
        return token, mode
    return None

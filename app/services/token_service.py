from __future__ import annotations
import secrets

def generate_deck_token() -> str:
    return secrets.token_urlsafe(18)

def build_payload(deck_token: str) -> str:
    return f"deck_{deck_token}"

def parse_payload(payload: str | None) -> str | None:
    if not payload:
        return None
    if payload.startswith("deck_"):
        return payload[len("deck_"):]
    return None

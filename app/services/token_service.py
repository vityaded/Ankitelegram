from __future__ import annotations
import secrets

VALID_MODES = {"anki", "watch"}


def generate_deck_token() -> str:
    return secrets.token_urlsafe(18)


def build_payload(deck_token: str, mode: str = "anki") -> str:
    m = (mode or "anki").lower()
    if m not in VALID_MODES:
        m = "anki"
    # Telegram deep-link safe: only [A-Za-z0-9_-]
    # anki keeps legacy format
    if m == "watch":
        return f"deckw_{deck_token}"
    return f"deck_{deck_token}"


def parse_payload(payload: str | None) -> tuple[str, str] | None:
    if not payload:
        return None
    # NEW watch format
    if payload.startswith("deckw_"):
        token = payload[len("deckw_"):]
        return (token, "watch") if token else None

    # Legacy / anki format (keep working forever)
    if payload.startswith("deck_"):
        token = payload[len("deck_"):]
        return (token, "anki") if token else None

    # Optional: accept old dot format if user manually types it (deep-link won’t send it)
    if payload.startswith("deck.watch."):
        token = payload[len("deck.watch."):]
        return (token, "watch") if token else None
    if payload.startswith("deck.anki."):
        token = payload[len("deck.anki."):]
        return (token, "anki") if token else None

    return None

from __future__ import annotations

def start_message() -> str:
    return (
        "Students: open a deck link to start (the first card is sent immediately).\n"
        "Every day at 07:00 you will receive today's first card automatically.\n"
        "Admins: send .apkg (small) or use 'Upload deck (large)'."
    )

def admin_import_prompt() -> str:
    return "Upload received. Importing... Please wait."

def ask_new_per_day() -> str:
    return "How many NEW cards per day should students get? Send a number (e.g., 10)."

def invalid_number() -> str:
    return "Please send a valid integer number."

def deck_link(bot_username: str, deck_token: str) -> str:
    return f"https://t.me/{bot_username}?start=deck_{deck_token}"

def join_ok(deck_title: str) -> str:
    return f"Joined deck: {deck_title}"

def deck_inactive() -> str:
    return "This deck is inactive."

def deck_not_found() -> str:
    return "Deck not found (invalid link)."

def no_cards_today() -> str:
    return "It's all for today."

def done_today() -> str:
    return "It's all for today."

def need_today_first() -> str:
    return "No active card. Open the deck link (or wait for 07:00)."

def flagged_bad() -> str:
    return "Flagged as bad card. Skipping..."

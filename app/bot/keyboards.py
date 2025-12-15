from __future__ import annotations
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.services.admin_auth import make_upload_token

def kb_bad_card(deck_id: str, card_id: str) -> InlineKeyboardMarkup:
    # Telegram callback_data max is 64 bytes.
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Bad card", callback_data=f"bad:{card_id}")]
    ])

def kb_study_more(deck_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Study more", callback_data=f"more:{deck_id}")]
    ])

def kb_admin_deck(deck_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Stats", callback_data=f"ad_stats:{deck_id}")],
        [InlineKeyboardButton(text="Export bad cards", callback_data=f"ad_export:{deck_id}")],
        [InlineKeyboardButton(text="Set N/day", callback_data=f"ad_setn:{deck_id}")],
        [InlineKeyboardButton(text="Rotate link", callback_data=f"ad_rot:{deck_id}")],
        [InlineKeyboardButton(text="Disable deck", callback_data=f"ad_dis:{deck_id}")],
        [InlineKeyboardButton(text="Delete deck", callback_data=f"ad_del:{deck_id}")],
    ])


def kb_admin_deck_list(items: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    """items: (deck_id, title, is_active)"""
    rows = []
    for deck_id, title, is_active in items:
        status = "✅" if is_active else "🚫"
        rows.append([
            InlineKeyboardButton(text=f"{status} {title[:40]}", callback_data=f"ad_open:{deck_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"ad_del:{deck_id}"),
        ])
    rows.append([InlineKeyboardButton(text="Close", callback_data="ad_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_home(settings, admin_id: int) -> InlineKeyboardMarkup:
    tok = make_upload_token(settings.upload_secret, admin_id, ttl_seconds=3600)
    url = f"{settings.web_base_url}/upload?token={tok}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="All decks", callback_data="ad_list")],
        [InlineKeyboardButton(text="Upload deck (large)", url=url)],
])

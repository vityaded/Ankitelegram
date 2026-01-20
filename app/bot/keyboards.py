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
        [InlineKeyboardButton(text="Student list", callback_data=f"ad_students:{deck_id}:0")],
        [InlineKeyboardButton(text="Export bad cards", callback_data=f"ad_export:{deck_id}")],
        [InlineKeyboardButton(text="Set N/day", callback_data=f"ad_setn:{deck_id}")],
        [InlineKeyboardButton(text="Rotate link", callback_data=f"ad_rot:{deck_id}")],
        [InlineKeyboardButton(text="Unenroll everyone", callback_data=f"ad_unenroll_all:{deck_id}")],
        [InlineKeyboardButton(text="Disable deck", callback_data=f"ad_dis:{deck_id}")],
        [InlineKeyboardButton(text="Delete deck", callback_data=f"ad_del:{deck_id}")],
    ])


def kb_admin_deck_list(items: list[tuple[str, str, bool]], back_callback: str | None = None) -> InlineKeyboardMarkup:
    """items: (deck_id, title, is_active)"""
    rows = []
    for deck_id, title, is_active in items:
        status = "✅" if is_active else "🚫"
        rows.append([
            InlineKeyboardButton(text=f"{status} {title[:40]}", callback_data=f"ad_open:{deck_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"ad_del:{deck_id}"),
        ])
    if back_callback:
        rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="Close", callback_data="ad_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_folder_root(folders: list[tuple[str, str]], ungrouped_count: int) -> InlineKeyboardMarkup:
    rows = []
    for folder_id, path in folders:
        rows.append([InlineKeyboardButton(text=f"📁 {path[:48]}", callback_data=f"adm_folder:{folder_id}")])
    if ungrouped_count:
        rows.append([InlineKeyboardButton(text=f"Ungrouped decks ({ungrouped_count})", callback_data="adm_ungrouped")])
    rows.append([InlineKeyboardButton(text="Close", callback_data="ad_close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_home(settings, admin_id: int) -> InlineKeyboardMarkup:
    tok = make_upload_token(settings.upload_secret, admin_id, ttl_seconds=3600)
    url = f"{settings.web_base_url}/upload?token={tok}"
    admin_url = f"{settings.web_base_url}/admin?token={tok}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="All decks", callback_data="adm_decks_root")],
        [InlineKeyboardButton(text="Upload deck (large)", url=url)],
        [InlineKeyboardButton(text="Open web admin", url=admin_url)],
])

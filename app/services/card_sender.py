from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from app.bot.keyboards import kb_bad_card

async def send_card_to_chat(bot: Bot, chat_id: int, card, deck_id: str) -> None:
    # card has: media_kind, tg_file_id, id
    rm: InlineKeyboardMarkup = kb_bad_card(deck_id, card.id)
    if card.media_kind == "audio":
        await bot.send_audio(chat_id, card.tg_file_id, reply_markup=rm)
    else:
        await bot.send_video(chat_id, card.tg_file_id, reply_markup=rm)

from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from app.bot.keyboards import kb_bad_card


def _first_last_letters(text: str) -> tuple[str, str] | None:
    letters = [ch for ch in text if ch.isalpha()]
    if letters:
        return letters[0], letters[-1]
    stripped = text.strip()
    if not stripped:
        return None
    return stripped[0], stripped[-1]


def _dot_tip(text: str) -> str | None:
    words = text.strip().split()
    if not words:
        return None
    letters = _first_last_letters(text)
    if not letters:
        return None
    first_letter, last_letter = letters
    dot_words: list[list[str]] = []
    for word in words:
        letters_count = sum(1 for ch in word if ch.isalpha())
        if letters_count == 0:
            letters_count = len(word)
        if letters_count == 0:
            letters_count = 1
        dot_words.append(list("." * letters_count))
    dot_words[0][0] = first_letter
    dot_words[-1][-1] = last_letter
    return " ".join("".join(chars) for chars in dot_words)

async def send_card_to_chat(bot: Bot, chat_id: int, card, deck_id: str) -> None:
    # card has: media_kind, tg_file_id, id
    rm: InlineKeyboardMarkup = kb_bad_card(deck_id, card.id)
    tip = _dot_tip(card.answer_text)
    caption = f"Tip: {tip}" if tip else None
    if card.media_kind == "audio":
        await bot.send_audio(chat_id, card.tg_file_id, caption=caption, reply_markup=rm)
    else:
        await bot.send_video(chat_id, card.tg_file_id, caption=caption, reply_markup=rm)

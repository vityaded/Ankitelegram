from __future__ import annotations

from datetime import datetime

from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.token_service import parse_payload
from app.bot.messages import deck_not_found, deck_inactive, done_today
from app.bot.keyboards import kb_study_more
from app.db.repo import get_deck_by_token, get_or_create_user, enroll_user, get_card, ensure_review_placeholder
from app.utils.locks import LockRegistry
from app.utils.timez import today_date
from app.services.study_engine import ensure_current_card, start_or_resume_today
from app.services.card_sender import send_card_to_chat

router = Router()

@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: Message, session: AsyncSession, settings, locks: LockRegistry, bot: Bot):
    payload = message.text.split(maxsplit=1)[1] if message.text and len(message.text.split()) > 1 else None
    parsed = parse_payload(payload)
    if not parsed:
        await message.answer(deck_not_found())
        return

    token, mode = parsed

    deck = await get_deck_by_token(session, token)
    if not deck:
        await message.answer(deck_not_found())
        return

    # Read required fields BEFORE any commit to avoid async lazy-load issues.
    deck_id = deck.id
    is_active = deck.is_active

    if not is_active:
        await message.answer(deck_inactive())
        return

    user = await get_or_create_user(session, message.from_user.id)
    # IMPORTANT: capture primitive IDs before enroll_user().
    # enroll_user() may hit IntegrityError (already enrolled) and perform rollback(),
    # which expires ORM objects; accessing user.id after rollback can trigger async
    # lazy-loading and crash with MissingGreenlet.
    user_id = user.id
    await enroll_user(session, user_id, deck_id, mode=mode)

    lock = locks.lock((user_id, deck_id))
    async with lock:
        now_utc = datetime.utcnow()
        sdate = today_date(settings.tz)
        sess, _created = await start_or_resume_today(session, user_id, deck_id, sdate, now_utc)
        cid = await ensure_current_card(session, user_id, deck_id, sdate, now_utc)

        if not getattr(sess, "queue", None) or not cid:
            await message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            return

        card = await get_card(session, cid)
        if not card:
            await message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            return

        # Minimal UX: send the card immediately (no extra menus).
        await ensure_review_placeholder(session, user_id, card.id)
        await send_card_to_chat(bot, message.chat.id, card, deck_id)

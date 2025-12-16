from __future__ import annotations

from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.locks import LockRegistry
from app.utils.timez import today_date
from app.bot.messages import flagged_bad, done_today, need_today_first
from app.bot.keyboards import kb_study_more
from app.db.repo import get_or_create_user, get_today_session, get_card
from app.db.models import StudySession
from app.services.flag_service import flag_bad_card
from app.services.study_engine import ensure_current_card, record_answered_card
from app.services.card_sender import send_card_to_chat

router = Router()


@router.callback_query(F.data.startswith("bad:"))
async def cb_bad_card(call: CallbackQuery, session: AsyncSession, settings, locks: LockRegistry, bot: Bot):
    # bad:<card_id>
    parts = call.data.split(":", 1)
    if len(parts) != 2:
        await call.answer()
        return
    card_id = parts[1]

    user = await get_or_create_user(session, call.from_user.id)

    sdate = today_date(settings.tz)
    # find most recent active session today (deck inferred)
    res = await session.execute(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.study_date == sdate, StudySession.current_card_id.is_not(None))
        .order_by(StudySession.updated_at.desc())
        .limit(1)
    )
    sess = res.scalar_one_or_none()
    if not sess:
        await call.message.answer(need_today_first())
        await call.answer()
        return

    deck_id = sess.deck_id
    lock = locks.lock((user.id, deck_id))

    async with lock:
        await flag_bad_card(session, user.id, card_id)
        await call.message.answer(flagged_bad())

        sess2 = await get_today_session(session, user.id, deck_id, sdate)
        if not sess2:
            await call.message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            await call.answer()
            return

        await record_answered_card(session, sess2, card_id)
        next_id = await ensure_current_card(session, user.id, deck_id, sdate, datetime.utcnow())
        if not next_id:
            await call.message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            await call.answer()
            return
        next_card = await get_card(session, next_id)
        if not next_card:
            await call.message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            await call.answer()
            return
        await send_card_to_chat(bot, call.message.chat.id, next_card, deck_id)
        await call.answer()

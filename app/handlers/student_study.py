from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram import Bot

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.locks import LockRegistry
from app.utils.timez import today_date
from app.bot.messages import no_cards_today, done_today, need_today_first
from app.bot.keyboards import kb_bad_card, kb_study_more
from app.db.repo import get_or_create_user, get_deck_by_id, is_enrolled, get_card, get_review, upsert_review, get_today_session, get_card_translation_uk
from app.db.models import StudySession
from app.services.study_engine import ensure_current_card, extend_today_with_more, record_answered_card, start_or_resume_today
from app.services.grader import grade
from app.services.comparer import format_compare
from app.services.srs import apply_srs
from app.services.card_sender import send_card_to_chat

router = Router()


async def _send_card(bot: Bot, chat_id: int, card, deck_id: str):
    await send_card_to_chat(bot, chat_id, card, deck_id)


@router.callback_query(F.data.startswith("more:"))
async def cb_more(call: CallbackQuery, session: AsyncSession, settings, locks: LockRegistry, bot: Bot):
    deck_id = call.data.split(":", 1)[1]
    user = await get_or_create_user(session, call.from_user.id)
    deck = await get_deck_by_id(session, deck_id)
    if not deck or not deck.is_active:
        await call.message.answer("Deck inactive or not found.")
        await call.answer()
        return
    if not await is_enrolled(session, user.id, deck_id):
        await call.message.answer("Not enrolled. Open the deck link again.")
        await call.answer()
        return

    lock = locks.lock((user.id, deck_id))
    async with lock:
        now_utc = datetime.utcnow()
        sdate = today_date(settings.tz)

        sess = await get_today_session(session, user.id, deck_id, sdate)
        if not sess:
            sess, _ = await start_or_resume_today(session, user.id, deck_id, sdate, now_utc)

        cid = await ensure_current_card(session, user.id, deck_id, sdate, now_utc)
        if not cid:
            # try extending queue with more work
            sess = await extend_today_with_more(session, user.id, deck_id, sdate, now_utc, extra_new=30)
            cid = await ensure_current_card(session, user.id, deck_id, sdate, now_utc)

        if not cid:
            await call.message.answer(no_cards_today(), reply_markup=kb_study_more(deck_id))
            await call.answer()
            return

        card = await get_card(session, cid)
        if not card:
            await call.message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            await call.answer()
            return

        await _send_card(bot, call.message.chat.id, card, deck_id)
        await call.answer()


@router.message(F.text)
async def on_answer(message: Message, session: AsyncSession, settings, locks: LockRegistry, bot: Bot):
    # Find any active session for today where current_card_id is not null.
    user = await get_or_create_user(session, message.from_user.id)

    sdate = today_date(settings.tz)
    res = await session.execute(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.study_date == sdate, StudySession.current_card_id.is_not(None))
        .order_by(StudySession.updated_at.desc())
        .limit(1)
    )
    sess = res.scalar_one_or_none()
    if not sess or not sess.current_card_id:
        await message.answer(need_today_first())
        return

    deck_id = sess.deck_id
    lock = locks.lock((user.id, deck_id))
    async with lock:
        sess2 = await get_today_session(session, user.id, deck_id, sdate)
        if not sess2 or not sess2.current_card_id:
            await message.answer(need_today_first())
            return

        card_id = sess2.current_card_id
        card = await get_card(session, card_id)
        if not card:
            await record_answered_card(session, sess2, card_id)
            cid = await ensure_current_card(session, user.id, deck_id, sdate, datetime.utcnow())
            if cid:
                next_card = await get_card(session, cid)
                if next_card:
                    await _send_card(bot, message.chat.id, next_card, deck_id)
            else:
                await message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            return

        now_utc = datetime.utcnow()
        review = await get_review(session, user.id, card.id)
        gr = grade(
            user_text=message.text,
            correct_text=card.answer_text,
            alt_answers=card.alt_answers,
            ok=settings.similarity_ok,
            almost=settings.similarity_almost,
        )

        updated = apply_srs(
            review=review,
            verdict=gr.verdict,
            now_utc=now_utc,
            learning_steps_minutes=settings.learning_steps_minutes,
            graduate_days=settings.learning_graduate_days,
            last_answer_raw=message.text,
            last_score=gr.score,
        )
        updated.user_id = user.id
        updated.card_id = card.id
        await upsert_review(session, updated)

        uk_text = await get_card_translation_uk(session, card.id)
        cmp = format_compare(card.answer_text, message.text, gr.score, gr.verdict, uk=uk_text)
        await message.answer(cmp, parse_mode='HTML', disable_web_page_preview=True)

        await asyncio.sleep(1)

        await record_answered_card(session, sess2, card_id)
        next_id = await ensure_current_card(session, user.id, deck_id, sdate, datetime.utcnow())
        if not next_id:
            await message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            return
        next_card = await get_card(session, next_id)
        if not next_card:
            await message.answer(done_today(), reply_markup=kb_study_more(deck_id))
            return
        await _send_card(bot, message.chat.id, next_card, deck_id)

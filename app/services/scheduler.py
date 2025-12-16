from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import select, func

from aiogram import Bot

from app.utils.timez import today_date
from app.db.models import Enrollment, User, Deck, StudySession
from app.services.study_engine import ensure_current_card, start_or_resume_today
from app.db.repo import (
    claim_current_if_none,
    get_card,
    get_due_learning_cards,
    update_session_progress,
    get_today_session,
)
from app.services.card_sender import send_card_to_chat


async def _sleep_until_next_7am(tz_name: str) -> None:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = datetime.combine(now.date(), time(7, 0), tzinfo=tz)
    if now >= target:
        target = target + timedelta(days=1)
    delta = (target - now).total_seconds()
    if delta < 1:
        delta = 1
    await asyncio.sleep(delta)


async def run_daily_7am_push(
    *,
    bot: Bot,
    settings,
    sessionmaker: async_sessionmaker[AsyncSession],
):
    # On startup: if local time already past 07:00, do a one-time catch-up (create missing sessions for today).
    tz = ZoneInfo(settings.tz)
    now_local = datetime.now(tz)
    if now_local.time() >= time(7, 0):
        await push_today_cards(bot=bot, settings=settings, sessionmaker=sessionmaker)

    # Runs forever: at 07:00 in settings.tz, create today's sessions (if missing) and send first card.
    while True:
        await _sleep_until_next_7am(settings.tz)
        await push_today_cards(bot=bot, settings=settings, sessionmaker=sessionmaker)


async def push_today_cards(*, bot: Bot, settings, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    now_utc = datetime.utcnow()
    sdate = today_date(settings.tz)

    async with sessionmaker() as session:
        # Active enrollments only
        stmt = (
            select(User.tg_id, User.id, Deck.id)
            .select_from(Enrollment)
            .join(User, User.id == Enrollment.user_id)
            .join(Deck, Deck.id == Enrollment.deck_id)
            .where(Deck.is_active == True)
        )
        rows = (await session.execute(stmt)).all()

    # Process each enrollment; create its own session scope to keep transactions small
    for tg_id, user_id, deck_id in rows:
        try:
            async with sessionmaker() as s:
                sess, _created = await start_or_resume_today(s, user_id, deck_id, sdate, now_utc)
                cid = await ensure_current_card(s, user_id, deck_id, sdate, now_utc)
                if not getattr(sess, "queue", None) or not cid:
                    continue

                card = await get_card(s, cid)
                if not card:
                    continue
                await send_card_to_chat(bot, tg_id, card, deck_id)

            # basic rate limit
            await asyncio.sleep(0.05)
        except Exception:
            # user blocked bot / network error / etc -> ignore
            continue


async def run_due_learning_push(
    *,
    bot: Bot,
    settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    interval_seconds: int = 45,
    send_card_fn=send_card_to_chat,
):
    while True:
        try:
            await _run_due_learning_push_once(bot=bot, settings=settings, sessionmaker=sessionmaker, send_card_fn=send_card_fn)
        except Exception:
            # swallow errors to keep loop alive
            pass
        await asyncio.sleep(interval_seconds)


async def _run_due_learning_push_once(
    *,
    bot: Bot,
    settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    send_card_fn=send_card_to_chat,
):
    now_utc = datetime.utcnow()
    sdate = today_date(settings.tz)

    async with sessionmaker() as session:
        stmt = (
            select(StudySession)
            .where(
                StudySession.study_date == sdate,
                StudySession.current_card_id.is_(None),
                StudySession.pos >= func.json_array_length(StudySession.queue),
            )
        )
        sessions = (await session.execute(stmt)).scalars().all()

    for sess in sessions:
        async with sessionmaker() as s:
            # Re-fetch to ensure we have fresh state inside transaction
            current = await get_today_session(s, sess.user_id, sess.deck_id, sdate)
            if not current or current.current_card_id is not None:
                continue
            queue = current.queue or []
            if current.pos < len(queue):
                continue

            due_learning = await get_due_learning_cards(s, current.user_id, current.deck_id, now_utc, limit=1)
            if not due_learning:
                continue
            cid = due_learning[0]
            claimed = await claim_current_if_none(s, current.id, cid)
            if not claimed:
                continue

            card = await get_card(s, cid)
            if not card:
                await update_session_progress(s, current.id, current.pos, None)
                continue

            tg_id = (await s.execute(select(User.tg_id).where(User.id == current.user_id))).scalar_one()
            await send_card_fn(bot, tg_id, card, current.deck_id)

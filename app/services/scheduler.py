from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import select

from aiogram import Bot

from app.utils.timez import today_date
from app.db.models import Enrollment, User, Deck, StudySession
from app.services.study_engine import start_or_resume_today
from app.db.repo import get_card
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
                # Only if today's session doesn't exist yet -> create and send first card
                existing = await s.execute(
                    select(StudySession.id).where(
                        StudySession.user_id == user_id,
                        StudySession.deck_id == deck_id,
                        StudySession.study_date == sdate
                    )
                )
                if existing.first() is not None:
                    continue

                sess, _created = await start_or_resume_today(s, user_id, deck_id, sdate, now_utc)
                if not getattr(sess, "queue", None):
                    continue
                cid = sess.current_card_id
                if not cid:
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

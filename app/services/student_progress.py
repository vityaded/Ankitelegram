from __future__ import annotations

from datetime import date, timedelta, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import (
    compute_overall_progress,
    get_study_sessions_for_user_deck_in_range,
    get_today_session,
)


def _session_progress(session_obj) -> tuple[int, int]:
    if not session_obj:
        return 0, 0
    total = len(session_obj.queue or [])
    done = min(session_obj.pos, total)
    return done, total


async def get_today_progress(session: AsyncSession, user_id: str, deck_id: str, study_date: date) -> tuple[int, int]:
    today_session = await get_today_session(session, user_id, deck_id, study_date)
    return _session_progress(today_session)


async def get_daily_progress_history(
    session: AsyncSession, user_id: str, deck_id: str, end_date: date, days: int = 7
) -> list[tuple[date, int, int]]:
    start_date = end_date - timedelta(days=days - 1)
    sessions = await get_study_sessions_for_user_deck_in_range(session, user_id, deck_id, start_date, end_date)
    by_date = {s.study_date: _session_progress(s) for s in sessions}
    history: list[tuple[date, int, int]] = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        done, total = by_date.get(day, (0, 0))
        history.append((day, done, total))
    return history


async def get_overall_progress_summary(
    session: AsyncSession, user_id: str, deck_id: str, now: datetime | None = None
) -> dict:
    return await compute_overall_progress(session, user_id, deck_id, now=now)

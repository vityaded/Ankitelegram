from __future__ import annotations
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import Enrollment, Review, Deck, Flag, Card, StudySession

async def student_stats(session: AsyncSession, user_id: str, deck_id: str, study_date: date) -> str:
    # count answers today by checking reviews updated_at within today range (UTC approximation)
    # Minimal: show session progress.
    res = await session.execute(
        select(StudySession).where(StudySession.user_id==user_id, StudySession.deck_id==deck_id, StudySession.study_date==study_date)
    )
    ss = res.scalar_one_or_none()
    if not ss:
        return "No session today."
    total = len(ss.queue or [])
    done = min(ss.pos, total)
    return f"Today: {done}/{total} cards."

async def admin_stats(session: AsyncSession, deck_id: str) -> str:
    # enrolled
    enrolled = await session.execute(select(func.count(Enrollment.id)).where(Enrollment.deck_id==deck_id))
    enrolled_n = int(enrolled.scalar() or 0)
    # flagged
    flagged = await session.execute(
        select(func.count(Flag.id))
        .join(Card, Card.id==Flag.card_id)
        .where(Card.deck_id==deck_id)
    )
    flagged_n = int(flagged.scalar() or 0)
    return f"Enrolled: {enrolled_n}\nFlags: {flagged_n}"

from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.db.models import Review, ReviewState
from app.db.repo import add_flag, get_review

async def flag_bad_card(session: AsyncSession, user_id: str, card_id: str) -> None:
    await add_flag(session, user_id, card_id, reason="bad_card")
    review = await get_review(session, user_id, card_id)
    if review is None:
        review = Review(user_id=user_id, card_id=card_id, state=ReviewState.suspended.value, updated_at=datetime.utcnow())
        session.add(review)
        await session.commit()
        return
    review.state = ReviewState.suspended.value
    review.updated_at = datetime.utcnow()
    session.add(review)
    await session.commit()

from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import get_new_cards, get_due_review_cards, get_enrollment_mode
from app.db.repo import get_deck_by_id


def _dedupe_preserve_order(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in ids:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


async def build_today_queue(session: AsyncSession, user_id: str, deck_id: str, now_utc: datetime) -> list[str]:
    deck = await get_deck_by_id(session, deck_id)
    if deck is None:
        return []
    mode = await get_enrollment_mode(session, user_id, deck_id)
    new_limit = None if mode == "watch" else deck.new_per_day
    due_review = await get_due_review_cards(session, user_id, deck_id, now_utc, limit=50)
    new = await get_new_cards(session, deck_id, user_id, new_limit)
    queue = _dedupe_preserve_order(due_review + new)
    return queue

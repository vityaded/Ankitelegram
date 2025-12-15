from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import get_due_cards, get_new_cards
from app.db.repo import get_deck_by_id

async def build_today_queue(session: AsyncSession, user_id: str, deck_id: str, now_utc: datetime) -> list[str]:
    deck = await get_deck_by_id(session, deck_id)
    if deck is None:
        return []
    due = await get_due_cards(session, user_id, deck_id, now_utc)
    new = await get_new_cards(session, deck_id, user_id, deck.new_per_day)
    # avoid duplicates
    seen = set()
    queue: list[str] = []
    for cid in due + new:
        if cid not in seen:
            seen.add(cid)
            queue.append(cid)
    return queue

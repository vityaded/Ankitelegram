from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import get_today_session, create_today_session, update_session_progress, update_session_queue
from app.services.study_planner import build_today_queue
from app.db.repo import get_deck_by_id, get_due_cards, get_new_cards

async def start_or_resume_today(
    session: AsyncSession,
    user_id: str,
    deck_id: str,
    study_date,
    now_utc: datetime,
) -> tuple[object, bool]:
    existing = await get_today_session(session, user_id, deck_id, study_date)
    if existing:
        return existing, False
    queue = await build_today_queue(session, user_id, deck_id, now_utc)
    created = await create_today_session(session, user_id, deck_id, study_date, queue)
    return created, True

async def advance(
    session: AsyncSession,
    sess_id: str,
    queue: list[str],
    pos: int
) -> tuple[int, str | None]:
    new_pos = pos + 1
    new_current = queue[new_pos] if new_pos < len(queue) else None
    await update_session_progress(session, sess_id, new_pos, new_current)
    return new_pos, new_current

async def extend_today_with_more(
    session: AsyncSession,
    user_id: str,
    deck_id: str,
    study_date,
    now_utc: datetime,
    extra_new: int = 30,
) -> object | None:
    sess = await get_today_session(session, user_id, deck_id, study_date)
    if not sess:
        # create a fresh session if none
        created, _ = await start_or_resume_today(session, user_id, deck_id, study_date, now_utc)
        return created

    # if session already active, nothing to do
    if getattr(sess, "current_card_id", None):
        return sess

    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        return None

    due = await get_due_cards(session, user_id, deck_id, now_utc)

    # fetch more new cards than daily limit; filter out already in today's queue
    new = await get_new_cards(session, deck_id, user_id, deck.new_per_day + extra_new)

    seen = set(sess.queue or [])
    add: list[str] = []
    for cid in due + new:
        if cid not in seen:
            seen.add(cid)
            add.append(cid)

    if not add:
        return sess

    new_queue = (sess.queue or []) + add
    # when done, pos points at end, so current becomes first appended
    pos = getattr(sess, "pos", 0)
    current = new_queue[pos] if pos < len(new_queue) else None
    await update_session_queue(session, sess.id, new_queue, current)
    # re-fetch
    sess2 = await get_today_session(session, user_id, deck_id, study_date)
    return sess2

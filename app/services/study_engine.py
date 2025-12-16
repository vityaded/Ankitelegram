from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import (
    claim_current_if_none,
    create_today_session,
    get_deck_by_id,
    get_due_learning_cards,
    get_due_review_cards,
    get_new_cards,
    get_today_session,
    update_session_progress,
    update_session_queue,
)
from app.services.study_planner import build_today_queue


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


async def ensure_current_card(
    session: AsyncSession,
    user_id: str,
    deck_id: str,
    study_date,
    now_utc: datetime,
) -> str | None:
    sess = await get_today_session(session, user_id, deck_id, study_date)
    if not sess:
        queue = await build_today_queue(session, user_id, deck_id, now_utc)
        sess, _ = await start_or_resume_today(session, user_id, deck_id, study_date, now_utc)
        # persist the freshly built queue in case start_or_resume_today reused a stale queue
        await update_session_queue(session, sess.id, queue, None)
        sess = await get_today_session(session, user_id, deck_id, study_date)

    if getattr(sess, "current_card_id", None):
        return sess.current_card_id

    pos = getattr(sess, "pos", 0) or 0
    queue = getattr(sess, "queue", []) or []

    learning_due = await get_due_learning_cards(session, user_id, deck_id, now_utc, limit=1)
    if learning_due:
        cid = learning_due[0]
        claimed = await claim_current_if_none(session, sess.id, cid)
        if claimed:
            return cid
        sess = await get_today_session(session, user_id, deck_id, study_date)
        return getattr(sess, "current_card_id", None)

    if pos < len(queue):
        cid = queue[pos]
        claimed = await claim_current_if_none(session, sess.id, cid)
        if claimed:
            return cid
        sess = await get_today_session(session, user_id, deck_id, study_date)
        return getattr(sess, "current_card_id", None)

    return None


async def record_answered_card(
    session: AsyncSession,
    study_session,
    answered_card_id: str,
) -> tuple[int, bool]:
    """Update session after a card was answered.

    Returns (new_pos, was_main_queue_card).
    """

    was_main_queue = False
    pos = getattr(study_session, "pos", 0) or 0
    queue = getattr(study_session, "queue", []) or []
    if pos < len(queue) and queue[pos] == answered_card_id:
        was_main_queue = True
        pos += 1

    await update_session_progress(session, study_session.id, pos, None)
    return pos, was_main_queue


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
        created, _ = await start_or_resume_today(session, user_id, deck_id, study_date, now_utc)
        return created

    if getattr(sess, "current_card_id", None):
        return sess

    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        return None

    due_review = await get_due_review_cards(session, user_id, deck_id, now_utc, limit=50)
    new = await get_new_cards(session, deck_id, user_id, deck.new_per_day + extra_new)

    seen = set(sess.queue or [])
    add: list[str] = []
    for cid in due_review + new:
        if cid not in seen:
            seen.add(cid)
            add.append(cid)

    if not add:
        return sess

    new_queue = (sess.queue or []) + add
    await update_session_queue(session, sess.id, new_queue, None)
    return await get_today_session(session, user_id, deck_id, study_date)

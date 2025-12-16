from datetime import datetime, timedelta, date
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from app.db.models import Deck, Card, User, Review
from app.services.study_engine import ensure_current_card, record_answered_card
from app.services.scheduler import _run_due_learning_push_once
from app.db.repo import create_today_session, get_today_session, update_session_progress


async def _seed_basic(session):
    deck = Deck(admin_tg_id=1, title="Deck", token="tok", new_per_day=10)
    user = User(tg_id=100)
    session.add_all([deck, user])
    await session.commit()
    await session.refresh(deck)
    await session.refresh(user)
    return deck, user


def _make_card(deck_id: str, note_guid: str, suffix: str) -> Card:
    return Card(
        deck_id=deck_id,
        note_guid=note_guid,
        answer_text=f"ans-{suffix}",
        alt_answers=[],
        media_kind="audio",
        tg_file_id=f"file-{suffix}",
        media_sha256=f"sha-{suffix}",
    )


@pytest.mark.asyncio
async def test_learning_card_prioritized_over_main_queue(sessionmaker):
    async with sessionmaker() as session:
        deck, user = await _seed_basic(session)
        main_card = _make_card(deck.id, "n1", "main")
        learn_card = _make_card(deck.id, "n2", "learn")
        session.add_all([main_card, learn_card])
        await session.commit()
        await session.refresh(main_card)
        await session.refresh(learn_card)

        session.add(
            Review(
                user_id=user.id,
                card_id=learn_card.id,
                state="learning",
                due_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        await session.commit()

        study_date = date.today()
        cid = await ensure_current_card(session, user.id, deck.id, study_date, datetime.utcnow())
        assert cid == learn_card.id


@pytest.mark.asyncio
async def test_record_answered_card_updates_pos_only_for_main_queue(sessionmaker):
    async with sessionmaker() as session:
        deck, user = await _seed_basic(session)
        main_card = _make_card(deck.id, "n1", "main")
        learn_card = _make_card(deck.id, "n2", "learn")
        session.add_all([main_card, learn_card])
        await session.commit()
        await session.refresh(main_card)
        await session.refresh(learn_card)

        study_date = date.today()
        sess = await create_today_session(session, user.id, deck.id, study_date, [main_card.id])

        # main queue card increments pos
        await record_answered_card(session, sess, main_card.id)
        updated = await get_today_session(session, user.id, deck.id, study_date)
        assert updated.pos == 1

        # learning repeat does not increment
        await update_session_progress(session, sess.id, 0, None)
        session.add(
            Review(
                user_id=user.id,
                card_id=learn_card.id,
                state="learning",
                due_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        await session.commit()
        await record_answered_card(session, sess, learn_card.id)
        sess_after = await get_today_session(session, user.id, deck.id, study_date)
        assert sess_after.pos == 0


@pytest.mark.asyncio
async def test_scheduler_skips_when_current_card_active(sessionmaker):
    calls = []

    async with sessionmaker() as session:
        deck, user = await _seed_basic(session)
        learn_card = _make_card(deck.id, "n1", "learn")
        session.add(learn_card)
        await session.commit()
        await session.refresh(learn_card)

        session.add(
            Review(
                user_id=user.id,
                card_id=learn_card.id,
                state="learning",
                due_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        await session.commit()

        study_date = date.today()
        sess = await create_today_session(session, user.id, deck.id, study_date, [])
        sess.current_card_id = learn_card.id
        await session.commit()

    async def _send(bot, chat_id, card, deck_id):
        calls.append(card.id)

    await _run_due_learning_push_once(bot=None, settings=type("S", (), {"tz": "UTC"}), sessionmaker=sessionmaker, send_card_fn=_send)
    assert calls == []


@pytest.mark.asyncio
async def test_scheduler_sends_learning_after_main_queue(sessionmaker):
    calls = []

    async with sessionmaker() as session:
        deck, user = await _seed_basic(session)
        learn_card = _make_card(deck.id, "n1", "learn")
        session.add(learn_card)
        await session.commit()
        await session.refresh(learn_card)

        session.add(
            Review(
                user_id=user.id,
                card_id=learn_card.id,
                state="learning",
                due_at=datetime.utcnow() - timedelta(minutes=1),
            )
        )
        await session.commit()

        study_date = date.today()
        sess = await create_today_session(session, user.id, deck.id, study_date, [])
        sess.pos = 0
        await session.commit()

    async def _send(bot, chat_id, card, deck_id):
        calls.append(card.id)

    await _run_due_learning_push_once(bot=None, settings=type("S", (), {"tz": "UTC"}), sessionmaker=sessionmaker, send_card_fn=_send)
    assert calls == [learn_card.id]

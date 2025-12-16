from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import Deck, Card, User, Review, Enrollment, StudySession, Flag
from app.db.repo import (
    unenroll_student_wipe_progress,
    unenroll_all_students_wipe_progress,
    compute_overall_progress,
)
from app.services.student_progress import get_daily_progress_history, get_today_progress


@pytest.mark.asyncio
async def test_unenroll_student_wipe_progress(sessionmaker):
    async with sessionmaker() as session:
        deck = Deck(admin_tg_id=1, title="Deck", token="t1", new_per_day=10)
        other_deck = Deck(admin_tg_id=1, title="Deck2", token="t2", new_per_day=10)
        user = User(tg_id=100)
        other_user = User(tg_id=200)
        session.add_all([deck, other_deck, user, other_user])
        await session.commit()
        await session.refresh(deck)
        await session.refresh(other_deck)
        await session.refresh(user)
        await session.refresh(other_user)

        card = Card(deck_id=deck.id, note_guid="n1", answer_text="a1", alt_answers=[], media_kind="audio", tg_file_id="f1", media_sha256="s1")
        other_card = Card(deck_id=other_deck.id, note_guid="n2", answer_text="a2", alt_answers=[], media_kind="audio", tg_file_id="f2", media_sha256="s2")
        session.add_all([card, other_card])
        await session.commit()
        await session.refresh(card)
        await session.refresh(other_card)

        session.add_all([
            Enrollment(user_id=user.id, deck_id=deck.id),
            Enrollment(user_id=user.id, deck_id=other_deck.id),
            Enrollment(user_id=other_user.id, deck_id=deck.id),
            Review(user_id=user.id, card_id=card.id, state="learning"),
            Review(user_id=user.id, card_id=other_card.id, state="learning"),
            Review(user_id=other_user.id, card_id=card.id, state="review"),
            StudySession(user_id=user.id, deck_id=deck.id, study_date=date.today(), queue=["c1"], pos=1),
            StudySession(user_id=user.id, deck_id=other_deck.id, study_date=date.today(), queue=["c2"], pos=1),
            Flag(user_id=user.id, card_id=card.id),
            Flag(user_id=other_user.id, card_id=card.id),
        ])
        await session.commit()

        await unenroll_student_wipe_progress(session, user.id, deck.id)

        enr_rows = await session.execute(select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.deck_id == deck.id))
        assert enr_rows.first() is None
        # Other enrollments intact
        other_enr = await session.execute(select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.deck_id == other_deck.id))
        assert other_enr.first() is not None
        other_user_enr = await session.execute(select(Enrollment).where(Enrollment.user_id == other_user.id, Enrollment.deck_id == deck.id))
        assert other_user_enr.first() is not None

        rev_rows = await session.execute(select(Review).where(Review.user_id == user.id, Review.card_id == card.id))
        assert rev_rows.first() is None
        other_review = await session.execute(select(Review).where(Review.user_id == user.id, Review.card_id == other_card.id))
        assert other_review.first() is not None
        other_user_review = await session.execute(select(Review).where(Review.user_id == other_user.id, Review.card_id == card.id))
        assert other_user_review.first() is not None

        ss_rows = await session.execute(select(StudySession).where(StudySession.user_id == user.id, StudySession.deck_id == deck.id))
        assert ss_rows.first() is None
        other_ss = await session.execute(select(StudySession).where(StudySession.user_id == user.id, StudySession.deck_id == other_deck.id))
        assert other_ss.first() is not None

        flag_rows = await session.execute(select(Flag).where(Flag.user_id == user.id, Flag.card_id == card.id))
        assert flag_rows.first() is None
        other_flag = await session.execute(select(Flag).where(Flag.user_id == other_user.id, Flag.card_id == card.id))
        assert other_flag.first() is not None


@pytest.mark.asyncio
async def test_unenroll_all_students_wipe_progress(sessionmaker):
    async with sessionmaker() as session:
        deck = Deck(admin_tg_id=1, title="Deck", token="t1", new_per_day=10)
        other_deck = Deck(admin_tg_id=1, title="Deck2", token="t2", new_per_day=10)
        user = User(tg_id=100)
        other_user = User(tg_id=200)
        session.add_all([deck, other_deck, user, other_user])
        await session.commit()
        await session.refresh(deck)
        await session.refresh(other_deck)
        await session.refresh(user)
        await session.refresh(other_user)

        card = Card(deck_id=deck.id, note_guid="n1", answer_text="a1", alt_answers=[], media_kind="audio", tg_file_id="f1", media_sha256="s1")
        other_card = Card(deck_id=other_deck.id, note_guid="n2", answer_text="a2", alt_answers=[], media_kind="audio", tg_file_id="f2", media_sha256="s2")
        session.add_all([card, other_card])
        await session.commit()
        await session.refresh(card)
        await session.refresh(other_card)

        session.add_all([
            Enrollment(user_id=user.id, deck_id=deck.id),
            Enrollment(user_id=other_user.id, deck_id=deck.id),
            Enrollment(user_id=user.id, deck_id=other_deck.id),
            Review(user_id=user.id, card_id=card.id, state="learning"),
            Review(user_id=other_user.id, card_id=card.id, state="learning"),
            Review(user_id=user.id, card_id=other_card.id, state="learning"),
            StudySession(user_id=user.id, deck_id=deck.id, study_date=date.today(), queue=["c1"], pos=1),
            Flag(user_id=user.id, card_id=card.id),
            Flag(user_id=other_user.id, card_id=card.id),
        ])
        await session.commit()

        await unenroll_all_students_wipe_progress(session, deck.id)

        assert (await session.execute(select(Enrollment).where(Enrollment.deck_id == deck.id))).first() is None
        assert (await session.execute(select(Review).where(Review.card_id == card.id))).first() is None
        assert (await session.execute(select(StudySession).where(StudySession.deck_id == deck.id))).first() is None
        assert (await session.execute(select(Flag).where(Flag.card_id == card.id))).first() is None
        # Other deck untouched
        assert (await session.execute(select(Enrollment).where(Enrollment.deck_id == other_deck.id))).first() is not None
        assert (await session.execute(select(Review).where(Review.card_id == other_card.id))).first() is not None


@pytest.mark.asyncio
async def test_progress_history_and_overall(sessionmaker):
    async with sessionmaker() as session:
        deck = Deck(admin_tg_id=1, title="Deck", token="t1", new_per_day=10)
        user = User(tg_id=100)
        session.add_all([deck, user])
        await session.commit()
        await session.refresh(deck)
        await session.refresh(user)

        card = Card(deck_id=deck.id, note_guid="n1", answer_text="a1", alt_answers=[], media_kind="audio", tg_file_id="f1", media_sha256="s1")
        session.add(card)
        await session.commit()
        await session.refresh(card)

        base_date = date(2024, 1, 10)
        sessions = [
            StudySession(user_id=user.id, deck_id=deck.id, study_date=base_date, queue=["c1", "c2", "c3"], pos=2),
            StudySession(user_id=user.id, deck_id=deck.id, study_date=base_date + timedelta(days=1), queue=["c4"], pos=1),
            StudySession(user_id=user.id, deck_id=deck.id, study_date=base_date + timedelta(days=3), queue=["c5", "c6"], pos=0),
        ]
        session.add_all(sessions)
        session.add(Review(user_id=user.id, card_id=card.id, state="review", due_at=datetime.utcnow() - timedelta(days=1)))
        await session.commit()

        today_progress = await get_today_progress(session, user.id, deck.id, base_date + timedelta(days=3))
        assert today_progress == (0, 2)

        history = await get_daily_progress_history(session, user.id, deck.id, base_date + timedelta(days=3), days=7)
        assert len(history) == 7
        history_map = {d: (done, total) for d, done, total in history}
        assert history_map[base_date] == (2, 3)
        assert history_map[base_date + timedelta(days=1)] == (1, 1)
        assert history_map[base_date + timedelta(days=2)] == (0, 0)

        overall = await compute_overall_progress(session, user.id, deck.id, now=datetime.utcnow())
        assert overall["total_cards"] == 1
        assert overall["started"] == 1
        assert overall["states"].get("review") == 1
        assert overall["due"] == 1

from __future__ import annotations

import secrets
from datetime import datetime
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Deck, Card, User, Enrollment, Review, ReviewState, StudySession, Flag, CardTranslation, TranslationCache, DeckFolder

def _new_token() -> str:
    return secrets.token_urlsafe(18)

# --- Deck ---
async def create_deck(session: AsyncSession, admin_tg_id: int, title: str, new_per_day: int, folder_id: str | None = None) -> Deck:
    deck = Deck(
        admin_tg_id=admin_tg_id,
        title=title[:255],
        token=_new_token(),
        new_per_day=new_per_day,
        folder_id=folder_id,
    )
    session.add(deck)
    await session.flush()
    return deck

async def get_deck_by_token(session: AsyncSession, token: str) -> Deck | None:
    res = await session.execute(select(Deck).where(Deck.token == token))
    return res.scalar_one_or_none()

async def get_deck_by_id(session: AsyncSession, deck_id: str) -> Deck | None:
    res = await session.execute(select(Deck).where(Deck.id == deck_id))
    return res.scalar_one_or_none()

async def update_deck_new_per_day(session: AsyncSession, deck_id: str, n: int) -> None:
    await session.execute(update(Deck).where(Deck.id == deck_id).values(new_per_day=n))
    await session.commit()

async def rotate_deck_token(session: AsyncSession, deck_id: str) -> str:
    token = _new_token()
    await session.execute(update(Deck).where(Deck.id == deck_id).values(token=token))
    await session.commit()
    return token

async def set_deck_active(session: AsyncSession, deck_id: str, active: bool) -> None:
    await session.execute(update(Deck).where(Deck.id == deck_id).values(is_active=active))
    await session.commit()

async def get_or_create_folder(session: AsyncSession, admin_tg_id: int, path: str) -> DeckFolder:
    path = path.strip().rstrip("/")
    res = await session.execute(
        select(DeckFolder).where(DeckFolder.admin_tg_id == admin_tg_id, DeckFolder.path == path)
    )
    folder = res.scalar_one_or_none()
    if folder:
        return folder
    folder = DeckFolder(admin_tg_id=admin_tg_id, path=path)
    session.add(folder)
    await session.flush()
    return folder

async def list_admin_folders(session: AsyncSession, admin_tg_id: int) -> list[DeckFolder]:
    res = await session.execute(
        select(DeckFolder).where(DeckFolder.admin_tg_id == admin_tg_id).order_by(DeckFolder.path.asc())
    )
    return list(res.scalars().all())

async def list_all_folders(session: AsyncSession) -> list[DeckFolder]:
    res = await session.execute(
        select(DeckFolder).order_by(DeckFolder.admin_tg_id.asc(), DeckFolder.path.asc())
    )
    return list(res.scalars().all())

async def list_admin_decks(session: AsyncSession, admin_tg_id: int) -> list[Deck]:
    res = await session.execute(select(Deck).where(Deck.admin_tg_id == admin_tg_id).order_by(Deck.created_at.desc()))
    return list(res.scalars().all())


async def list_all_decks(session: AsyncSession) -> list[Deck]:
    res = await session.execute(select(Deck).order_by(Deck.created_at.desc()))
    return list(res.scalars().all())

async def list_decks_in_folder(session: AsyncSession, folder_id: str) -> list[Deck]:
    res = await session.execute(select(Deck).where(Deck.folder_id == folder_id).order_by(Deck.title.asc()))
    return list(res.scalars().all())

async def get_folder_by_id(session: AsyncSession, folder_id: str) -> DeckFolder | None:
    res = await session.execute(select(DeckFolder).where(DeckFolder.id == folder_id))
    return res.scalar_one_or_none()

async def list_ungrouped_decks(session: AsyncSession, admin_tg_id: int | None = None) -> list[Deck]:
    stmt = select(Deck).where(Deck.folder_id.is_(None))
    if admin_tg_id is not None:
        stmt = stmt.where(Deck.admin_tg_id == admin_tg_id)
    res = await session.execute(stmt.order_by(Deck.title.asc()))
    return list(res.scalars().all())

async def count_ungrouped_decks(session: AsyncSession, admin_tg_id: int | None = None) -> int:
    stmt = select(func.count(Deck.id)).where(Deck.folder_id.is_(None))
    if admin_tg_id is not None:
        stmt = stmt.where(Deck.admin_tg_id == admin_tg_id)
    res = await session.execute(stmt)
    return int(res.scalar() or 0)

async def delete_deck_full(session: AsyncSession, deck_id: str) -> dict[str, int]:
    """Delete deck and all associated data (cards, enrollments, reviews, sessions, flags).
    Returns counts for basic visibility.
    """
    # Delete card-linked tables via subquery to avoid SQLite parameter limits.
    card_ids_subq = select(Card.id).where(Card.deck_id == deck_id)

    res_reviews = await session.execute(delete(Review).where(Review.card_id.in_(card_ids_subq)))
    res_flags = await session.execute(delete(Flag).where(Flag.card_id.in_(card_ids_subq)))
    res_card_translations = await session.execute(delete(CardTranslation).where(CardTranslation.card_id.in_(card_ids_subq)))

    res_sessions = await session.execute(delete(StudySession).where(StudySession.deck_id == deck_id))
    res_enroll = await session.execute(delete(Enrollment).where(Enrollment.deck_id == deck_id))

    res_cards = await session.execute(delete(Card).where(Card.deck_id == deck_id))
    res_deck = await session.execute(delete(Deck).where(Deck.id == deck_id))

    await session.commit()

    # SQLAlchemy's rowcount may be -1 on some dialects; normalize to 0 in that case.
    def _rc(x) -> int:
        try:
            return int(getattr(x, "rowcount", 0) or 0)
        except Exception:
            return 0

    return {
        "reviews": _rc(res_reviews),
        "flags": _rc(res_flags),
        "card_translations": _rc(res_card_translations),
        "sessions": _rc(res_sessions),
        "enrollments": _rc(res_enroll),
        "cards": _rc(res_cards),
        "decks": _rc(res_deck),
    }

# --- Cards ---
async def find_file_id_by_sha(session: AsyncSession, sha256: str) -> str | None:
    res = await session.execute(select(Card.tg_file_id).where(Card.media_sha256 == sha256).limit(1))
    row = res.first()
    return row[0] if row else None

async def insert_cards(session: AsyncSession, deck_id: str, cards: list[Card]) -> tuple[int,int]:
    ok = 0
    skipped = 0
    for c in cards:
        c.deck_id = deck_id
        session.add(c)
        try:
            await session.flush()
            ok += 1
        except IntegrityError:
            await session.rollback()
            skipped += 1
    await session.commit()
    return ok, skipped

async def get_card(session: AsyncSession, card_id: str) -> Card | None:
    res = await session.execute(select(Card).where(Card.id == card_id))
    return res.scalar_one_or_none()

async def get_new_cards(session: AsyncSession, deck_id: str, user_id: str, limit: int | None) -> list[str]:
    # Cards that have no review row for this user (never seen).
    subq = select(Review.card_id).where(Review.user_id == user_id).subquery()
    stmt = (
        select(Card.id)
        .where(Card.deck_id == deck_id, Card.is_valid == True)
        .where(~Card.id.in_(select(subq.c.card_id)))
        .order_by(Card.created_at.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    res = await session.execute(stmt)
    return [cid for (cid,) in res.all()]

async def get_due_learning_cards(session: AsyncSession, user_id: str, deck_id: str, now: datetime, limit: int = 1) -> list[str]:
    stmt = (
        select(Review.card_id)
        .join(Card, Card.id == Review.card_id)
        .where(
            Review.user_id == user_id,
            Card.deck_id == deck_id,
            Review.state == "learning",
            Review.due_at.is_not(None),
            Review.due_at <= now,
        )
        .order_by(Review.due_at.asc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return [cid for (cid,) in res.all()]

async def get_due_review_cards(session: AsyncSession, user_id: str, deck_id: str, now: datetime, limit: int = 50) -> list[str]:
    stmt = (
        select(Review.card_id)
        .join(Card, Card.id == Review.card_id)
        .where(
            Review.user_id == user_id,
            Card.deck_id == deck_id,
            Review.state == "review",
            Review.due_at.is_not(None),
            Review.due_at <= now,
        )
        .order_by(Review.due_at.asc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return [cid for (cid,) in res.all()]

# --- Users / Enrollment ---
async def get_or_create_user(session: AsyncSession, tg_id: int) -> User:
    res = await session.execute(select(User).where(User.tg_id == tg_id))
    user = res.scalar_one_or_none()
    if user:
        return user
    user = User(tg_id=tg_id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    res = await session.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()

async def enroll_user(session: AsyncSession, user_id: str, deck_id: str, mode: str = "anki") -> None:
    enr = Enrollment(user_id=user_id, deck_id=deck_id, mode=mode)
    session.add(enr)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()

async def is_enrolled(session: AsyncSession, user_id: str, deck_id: str) -> bool:
    res = await session.execute(select(Enrollment.id).where(Enrollment.user_id==user_id, Enrollment.deck_id==deck_id))
    return res.first() is not None


async def get_enrollment_mode(session: AsyncSession, user_id: str, deck_id: str) -> str:
    res = await session.execute(
        select(Enrollment.mode).where(Enrollment.user_id == user_id, Enrollment.deck_id == deck_id)
    )
    mode = res.scalar_one_or_none()
    if not mode:
        return "anki"
    mode = (mode or "anki").lower()
    return mode if mode in ("anki", "watch") else "anki"

async def list_enrolled_students(session: AsyncSession, deck_id: str, offset: int = 0, limit: int = 10) -> list[User]:
    stmt = (
        select(User)
        .join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.deck_id == deck_id)
        .order_by(Enrollment.joined_at.asc())
        .offset(offset)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())

async def count_enrolled_students(session: AsyncSession, deck_id: str) -> int:
    res = await session.execute(select(func.count(Enrollment.id)).where(Enrollment.deck_id == deck_id))
    return int(res.scalar() or 0)

# --- Reviews ---
async def get_review(session: AsyncSession, user_id: str, card_id: str) -> Review | None:
    res = await session.execute(select(Review).where(Review.user_id==user_id, Review.card_id==card_id))
    return res.scalar_one_or_none()

async def ensure_review_placeholder(session: AsyncSession, user_id: str, card_id: str) -> Review:
    review = await get_review(session, user_id, card_id)
    if review:
        return review
    review = Review(
        user_id=user_id,
        card_id=card_id,
        state=ReviewState.new.value,
        updated_at=datetime.utcnow(),
    )
    session.add(review)
    try:
        await session.commit()
        return review
    except IntegrityError:
        await session.rollback()
        existing = await get_review(session, user_id, card_id)
        if existing:
            return existing
        raise

async def upsert_review(session: AsyncSession, review: Review) -> None:
    session.add(review)
    await session.commit()

async def get_due_cards(session: AsyncSession, user_id: str, deck_id: str, now: datetime) -> list[str]:
    # Join reviews -> cards to filter deck
    stmt = (
        select(Review.card_id)
        .join(Card, Card.id == Review.card_id)
        .where(
            Review.user_id == user_id,
            Card.deck_id == deck_id,
            Review.state.in_(["learning","review"]),
            Review.due_at.is_not(None),
            Review.due_at <= now
        )
        .order_by(Review.due_at.asc())
    )
    res = await session.execute(stmt)
    return [cid for (cid,) in res.all()]

# --- Study Sessions ---
async def get_today_session(session: AsyncSession, user_id: str, deck_id: str, study_date) -> StudySession | None:
    res = await session.execute(
        select(StudySession).where(
            StudySession.user_id==user_id,
            StudySession.deck_id==deck_id,
            StudySession.study_date==study_date
        )
    )
    return res.scalar_one_or_none()

async def get_study_sessions_for_user_deck_in_range(session: AsyncSession, user_id: str, deck_id: str, date_from, date_to) -> list[StudySession]:
    stmt = (
        select(StudySession)
        .where(
            StudySession.user_id == user_id,
            StudySession.deck_id == deck_id,
            StudySession.study_date >= date_from,
            StudySession.study_date <= date_to,
        )
        .order_by(StudySession.study_date.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())

async def create_today_session(session: AsyncSession, user_id: str, deck_id: str, study_date, queue: list[str]) -> StudySession:
    s = StudySession(
        user_id=user_id,
        deck_id=deck_id,
        study_date=study_date,
        queue=queue,
        pos=0,
        current_card_id=None,
        updated_at=datetime.utcnow(),
    )
    session.add(s)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # someone created it concurrently, fetch
        existing = await get_today_session(session, user_id, deck_id, study_date)
        if existing:
            return existing
        raise
    await session.refresh(s)
    return s

async def update_session_progress(session: AsyncSession, session_id: str, pos: int, current_card_id: str | None) -> None:
    await session.execute(
        update(StudySession)
        .where(StudySession.id == session_id)
        .values(pos=pos, current_card_id=current_card_id, updated_at=datetime.utcnow())
    )
    await session.commit()

async def update_session_queue(session: AsyncSession, session_id: str, queue: list[str], current_card_id: str | None) -> None:
    await session.execute(
        update(StudySession)
        .where(StudySession.id == session_id)
        .values(queue=queue, current_card_id=current_card_id, updated_at=datetime.utcnow())
    )
    await session.commit()

async def claim_current_if_none(session: AsyncSession, session_id: str, card_id: str) -> bool:
    res = await session.execute(
        update(StudySession)
        .where(StudySession.id == session_id, StudySession.current_card_id.is_(None))
        .values(current_card_id=card_id, updated_at=datetime.utcnow())
        .returning(StudySession.id)
    )
    row = res.first()
    await session.commit()
    return row is not None

# --- Flags ---
async def add_flag(session: AsyncSession, user_id: str, card_id: str, reason: str="bad_card") -> None:
    session.add(Flag(user_id=user_id, card_id=card_id, reason=reason))
    await session.commit()

async def export_flags(session: AsyncSession, deck_id: str) -> list[tuple[str,str,int]]:
    # returns (note_guid, answer_text, count)
    stmt = (
        select(Card.note_guid, Card.answer_text, func.count(Flag.id))
        .join(Flag, Flag.card_id == Card.id)
        .where(Card.deck_id == deck_id)
        .group_by(Card.note_guid, Card.answer_text)
        .order_by(func.count(Flag.id).desc())
        .limit(200)
    )
    res = await session.execute(stmt)
    return [(a,b,int(c)) for (a,b,c) in res.all()]


# --- Admin progress helpers ---
async def compute_overall_progress(session: AsyncSession, user_id: str, deck_id: str, now: datetime | None = None) -> dict:
    """Return deck-level progress summary for a user."""
    now = now or datetime.utcnow()
    total_cards_res = await session.execute(select(func.count(Card.id)).where(Card.deck_id == deck_id))
    total_cards = int(total_cards_res.scalar() or 0)

    state_rows = await session.execute(
        select(Review.state, func.count(Review.card_id))
        .join(Card, Card.id == Review.card_id)
        .where(Review.user_id == user_id, Card.deck_id == deck_id)
        .group_by(Review.state)
    )
    state_counts = {state: int(count) for state, count in state_rows.all()}
    started = sum(state_counts.values())

    due_res = await session.execute(
        select(func.count(Review.card_id))
        .join(Card, Card.id == Review.card_id)
        .where(
            Review.user_id == user_id,
            Card.deck_id == deck_id,
            Review.state.in_(["learning", "review"]),
            Review.due_at.is_not(None),
            Review.due_at <= now,
        )
    )
    due_count = int(due_res.scalar() or 0)

    return {
        "total_cards": total_cards,
        "started": started,
        "states": state_counts,
        "due": due_count,
    }


# --- Unenroll helpers ---
async def unenroll_student_wipe_progress(session: AsyncSession, user_id: str, deck_id: str) -> None:
    card_ids_subq = select(Card.id).where(Card.deck_id == deck_id)
    try:
        await session.execute(
            delete(StudySession).where(
                StudySession.user_id == user_id,
                StudySession.deck_id == deck_id,
            )
        )
        await session.execute(
            delete(Flag).where(
                Flag.user_id == user_id,
                Flag.card_id.in_(card_ids_subq),
            )
        )
        await session.execute(
            delete(Review).where(
                Review.user_id == user_id,
                Review.card_id.in_(card_ids_subq),
            )
        )
        await session.execute(
            delete(Enrollment).where(
                Enrollment.user_id == user_id,
                Enrollment.deck_id == deck_id,
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

async def unenroll_all_students_wipe_progress(session: AsyncSession, deck_id: str) -> None:
    card_ids_subq = select(Card.id).where(Card.deck_id == deck_id)
    try:
        await session.execute(delete(StudySession).where(StudySession.deck_id == deck_id))
        await session.execute(delete(Flag).where(Flag.card_id.in_(card_ids_subq)))
        await session.execute(delete(Review).where(Review.card_id.in_(card_ids_subq)))
        await session.execute(delete(Enrollment).where(Enrollment.deck_id == deck_id))
        await session.commit()
    except Exception:
        await session.rollback()
        raise

async def unenroll_user_wipe_progress(session: AsyncSession, user_id: str) -> None:
    try:
        await session.execute(delete(StudySession).where(StudySession.user_id == user_id))
        await session.execute(delete(Flag).where(Flag.user_id == user_id))
        await session.execute(delete(Review).where(Review.user_id == user_id))
        await session.execute(delete(Enrollment).where(Enrollment.user_id == user_id))
        await session.commit()
    except Exception:
        await session.rollback()
        raise


# --- Translations ---
async def get_card_translation_uk(session: AsyncSession, card_id: str) -> str | None:
    """Returns Ukrainian subtitle translation for a card, if available."""
    stmt = (
        select(TranslationCache.translated_text)
        .join(CardTranslation, CardTranslation.cache_key == TranslationCache.key)
        .where(CardTranslation.card_id == card_id)
        .limit(1)
    )
    res = await session.execute(stmt)
    row = res.first()
    return row[0] if row else None

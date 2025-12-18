from __future__ import annotations

import enum
import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, Text, Boolean, Integer, BigInteger, DateTime, Date, Float,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

class Base(DeclarativeBase):
    pass

def _uuid() -> str:
    return str(uuid.uuid4())

class MediaKind(str, enum.Enum):
    video = "video"
    audio = "audio"

class ReviewState(str, enum.Enum):
    new = "new"
    learning = "learning"
    review = "review"
    suspended = "suspended"


class StudyMode(str, enum.Enum):
    anki = "anki"
    watch = "watch"

class Deck(Base):
    __tablename__ = "decks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    folder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("deck_folders.id", ondelete="SET NULL"), nullable=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    new_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    folder: Mapped["DeckFolder | None"] = relationship(back_populates="decks")
    cards: Mapped[list["Card"]] = relationship(back_populates="deck", cascade="all, delete-orphan")


class DeckFolder(Base):
    __tablename__ = "deck_folders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)

    __table_args__ = (UniqueConstraint("admin_tg_id", "path", name="uq_folder_admin_path"),)

    decks: Mapped[list[Deck]] = relationship(back_populates="folder")

class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("deck_id", "note_guid", name="uq_cards_deck_note"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    deck_id: Mapped[str] = mapped_column(String(36), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False)
    note_guid: Mapped[str] = mapped_column(String(64), nullable=False)

    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    alt_answers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    media_kind: Mapped[str] = mapped_column(String(8), nullable=False)  # values from MediaKind
    tg_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    media_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    deck: Mapped["Deck"] = relationship(back_populates="cards")

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "deck_id", name="uq_enroll_user_deck"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    deck_id: Mapped[str] = mapped_column(String(36), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default=StudyMode.anki.value)

class Review(Base):
    __tablename__ = "reviews"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True)

    state: Mapped[str] = mapped_column(String(16), nullable=False, default=ReviewState.new.value)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ease: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_answer_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    watch_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watch_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (UniqueConstraint("user_id", "deck_id", "study_date", name="uq_session_user_deck_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    deck_id: Mapped[str] = mapped_column(String(36), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False)
    study_date: Mapped[date] = mapped_column(Date, nullable=False)
    queue: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_card_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Flag(Base):
    __tablename__ = "flags"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="bad_card")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class TranslationCache(Base):
    __tablename__ = "translation_cache"
    # sha256(source_lang|target_lang|source_text)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CardTranslation(Base):
    __tablename__ = "card_translations"
    card_id: Mapped[str] = mapped_column(String(36), ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), ForeignKey("translation_cache.key", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

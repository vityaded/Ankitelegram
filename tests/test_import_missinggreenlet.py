from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.db.models import Card
from app.db.repo import create_deck
from app.services.import_service import _insert_cards_from_dtos


@dataclass
class _Dto:
    note_guid: str
    answer_text: str
    alt_answers: list[str]
    media_kind: str
    media_sha256: str
    media_bytes: bytes = b""
    filename: str = "file"


@pytest.mark.asyncio
async def test_import_continues_after_integrity_error(sessionmaker):
    async with sessionmaker() as session:
        deck = await create_deck(session, admin_tg_id=1, title="Deck", new_per_day=10)
        deck_id = deck.id

        dtos = [
            _Dto("guid-1", "a1", [], "audio", "sha1"),
            _Dto("guid-1", "a1-dup", [], "audio", "sha1-dup"),  # duplicate note_guid -> IntegrityError
            _Dto("guid-2", "a2", [], "audio", "sha2"),
        ]

        async def file_id_provider(dto: _Dto) -> str:
            return f"file-{dto.note_guid}"

        imported, skipped = await _insert_cards_from_dtos(
            session,
            dtos=dtos,
            deck_id=deck_id,
            translate_cfg=None,
            translate_sem=None,
            file_id_provider=file_id_provider,
        )

        assert imported == 2
        assert skipped == 1

        res = await session.execute(select(Card).where(Card.deck_id == deck_id))
        cards = res.scalars().all()
        assert len(cards) == 2
        guids = [c.note_guid for c in cards]
        assert guids.count("guid-1") == 1
        assert "guid-2" in guids

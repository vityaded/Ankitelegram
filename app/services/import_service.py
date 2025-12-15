from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.db.models import Card
from app.db.repo import create_deck
from app.services.media_store import get_or_upload_file_id
from app.services.apkg_importer.unpack import unpack_apkg
from app.services.apkg_importer.parse_collection import iter_notes
from app.services.apkg_importer.build_cards import build_cards_from_notes
from app.services.translate_service import (
    TranslateConfig,
    get_or_create_translation_cache,
    link_card_translation,
)
from app.bot.messages import deck_link


async def import_apkg_from_path(
    *,
    settings,
    bot: Bot,
    bot_username: str,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin_tg_id: int,
    apkg_path: str,
    deck_title: str,
    new_per_day: int,
) -> dict:
    """Imports an .apkg, uploads media to Telegram, creates deck+cards.

    Additionally (if enabled via env), translates card subtitles to Ukrainian
    and stores them for displaying alongside 'Correct' after answering.
    """

    os.makedirs(settings.import_tmp_dir, exist_ok=True)
    job_id = uuid.uuid4().hex

    # Parse apkg in thread to avoid blocking event loop
    base_dir = await asyncio.to_thread(unpack_apkg, apkg_path, settings.import_tmp_dir, job_id)
    collection_path = Path(base_dir) / "collection.anki2"
    notes = await asyncio.to_thread(lambda: list(iter_notes(collection_path)))
    dtos = await asyncio.to_thread(build_cards_from_notes, Path(base_dir), notes)

    cfg = TranslateConfig(
        enabled=getattr(settings, "subtitle_translate_enabled", True),
        source_lang=getattr(settings, "subtitle_translate_source_lang", "auto"),
        target_lang=getattr(settings, "subtitle_translate_target_lang", "uk"),
        concurrency=getattr(settings, "translate_concurrency", 1),
        min_delay_ms=getattr(settings, "translate_min_delay_ms", 250),
        max_retries=getattr(settings, "translate_max_retries", 30),
        base_delay_ms=getattr(settings, "translate_base_delay_ms", 750),
        max_delay_ms=getattr(settings, "translate_max_delay_ms", 60000),
    )
    translate_sem = asyncio.Semaphore(max(1, int(cfg.concurrency or 1)))

    imported = 0
    skipped = 0

    async with sessionmaker() as session:
        deck = await create_deck(session, admin_tg_id, deck_title, new_per_day=new_per_day)

        # Insert cards. Commit in chunks.
        for dto in dtos:
            try:
                file_id = await get_or_upload_file_id(
                    db=session,
                    bot=bot,
                    admin_tg_id=admin_tg_id,
                    media_bytes=dto.media_bytes,
                    filename=dto.filename,
                    media_sha256=dto.media_sha256,
                    media_kind=dto.media_kind,
                )

                card_id = str(uuid.uuid4())
                card = Card(
                    id=card_id,
                    deck_id=deck.id,
                    note_guid=dto.note_guid,
                    answer_text=dto.answer_text,
                    alt_answers=dto.alt_answers,
                    media_kind=dto.media_kind,
                    tg_file_id=file_id,
                    media_sha256=dto.media_sha256,
                    is_valid=True,
                )
                session.add(card)

                # Translation should not break import.
                try:
                    cache_key = await get_or_create_translation_cache(
                        session,
                        source_lang=cfg.source_lang,
                        target_lang=cfg.target_lang,
                        text=dto.answer_text,
                        cfg=cfg,
                        sem=translate_sem,
                    )
                    if cache_key:
                        await link_card_translation(session, card_id=card_id, cache_key=cache_key)
                except Exception:
                    # ignore translation failures, keep the card
                    pass

                imported += 1
                if imported % 50 == 0:
                    await session.commit()
            except Exception:
                await session.rollback()
                skipped += 1
                continue

        await session.commit()
        link = deck_link(bot_username, deck.token)

    # cleanup unpack dir
    try:
        import shutil

        shutil.rmtree(base_dir, ignore_errors=True)
    except Exception:
        pass

    return {"imported": imported, "skipped": skipped, "link": link}

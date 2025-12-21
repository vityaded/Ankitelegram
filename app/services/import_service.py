from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Iterable

from aiogram import Bot
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.db.models import Card
from app.db.repo import create_deck, get_or_create_folder
from app.services.media_store import get_or_upload_file_id
from app.services.apkg_importer.unpack import unpack_apkg
from app.services.apkg_importer.parse_collection import iter_notes
from app.services.apkg_importer.build_cards import build_cards_from_notes
from app.services.translate_service import (
    TranslateConfig,
    get_or_create_translation_cache,
    link_card_translation,
)
from app.bot.messages import deck_links


FileIdProvider = Callable[[object], Awaitable[str]]


async def _insert_cards_from_dtos(
    session: AsyncSession,
    *,
    dtos: Iterable[object],
    deck_id: str,
    translate_cfg: TranslateConfig | None,
    translate_sem: asyncio.Semaphore | None,
    file_id_provider: FileIdProvider,
    commit_every: int = 50,
) -> tuple[int, int]:
    imported = 0
    skipped = 0

    for dto in dtos:
        try:
            file_id = await file_id_provider(dto)
        except Exception:
            skipped += 1
            continue

        card_id = str(uuid.uuid4())
        try:
            async with session.begin_nested():
                card = Card(
                    id=card_id,
                    deck_id=deck_id,
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
                    if translate_cfg and translate_cfg.enabled:
                        cache_key = await get_or_create_translation_cache(
                            session,
                            source_lang=translate_cfg.source_lang,
                            target_lang=translate_cfg.target_lang,
                            text=dto.answer_text,
                            cfg=translate_cfg,
                            sem=translate_sem or asyncio.Semaphore(1),
                        )
                        if cache_key:
                            await link_card_translation(session, card_id=card_id, cache_key=cache_key)
                except Exception:
                    # ignore translation failures, keep the card
                    pass

                await session.flush()

            imported += 1
            if commit_every and imported % commit_every == 0:
                await session.commit()
        except IntegrityError:
            skipped += 1
            continue
        except Exception:
            await session.rollback()
            raise

    await session.commit()
    return imported, skipped


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
    folder_path: str | None = None,
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

    async with sessionmaker() as session:
        folder_id = None
        if folder_path:
            folder = await get_or_create_folder(session, admin_tg_id=admin_tg_id, path=folder_path)
            folder_id = folder.id

        deck = await create_deck(session, admin_tg_id, deck_title, new_per_day=new_per_day, folder_id=folder_id)
        deck_id = deck.id
        deck_token = deck.token

        async def _file_id_provider(dto):
            return await get_or_upload_file_id(
                db=session,
                bot=bot,
                admin_tg_id=admin_tg_id,
                media_bytes=dto.media_bytes,
                filename=dto.filename,
                media_sha256=dto.media_sha256,
                media_kind=dto.media_kind,
            )

        imported, skipped = await _insert_cards_from_dtos(
            session,
            dtos=dtos,
            deck_id=deck_id,
            translate_cfg=cfg,
            translate_sem=translate_sem,
            file_id_provider=_file_id_provider,
        )

        links = deck_links(bot_username, deck_token)

    # cleanup unpack dir
    try:
        import shutil

        shutil.rmtree(base_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "imported": imported,
        "skipped": skipped,
        "links": links,
        "link": links["anki"],
        "folder_path": folder_path,
        "deck_title": deck_title,
    }

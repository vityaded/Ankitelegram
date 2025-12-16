from __future__ import annotations

import os
import uuid

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import admin_import_prompt, ask_new_per_day, invalid_number
from app.bot.keyboards import kb_admin_deck
from app.db.repo import update_deck_new_per_day, get_deck_by_id
from app.services.import_service import import_apkg_from_path

router = Router()

class ImportFSM(StatesGroup):
    waiting_new_per_day = State()

@router.message(F.document)
async def on_apkg(message: Message, bot: Bot, session: AsyncSession, settings, state: FSMContext, bot_username: str):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".apkg"):
        return

    # Admin-only
    if settings.admin_ids and message.from_user.id not in settings.admin_ids:
        await message.answer("Not allowed.")
        return

    await message.answer(admin_import_prompt())

    # download file (Telegram size limit applies)
    file = await bot.get_file(doc.file_id)
    os.makedirs(settings.import_tmp_dir, exist_ok=True)
    local_path = os.path.join(settings.import_tmp_dir, f"tg_{uuid.uuid4().hex}.apkg")
    await bot.download_file(file.file_path, destination=local_path)

    # store temp path in FSM; import after new_per_day to keep previous flow
    await state.update_data(apkg_path=local_path, deck_title=(doc.file_name or "Deck"))
    await state.set_state(ImportFSM.waiting_new_per_day)
    await message.answer(ask_new_per_day())

@router.message(ImportFSM.waiting_new_per_day, F.text)
async def on_new_per_day(message: Message, settings, state: FSMContext, bot: Bot, bot_username: str, sessionmaker):
    # Admin-only
    if settings.admin_ids and message.from_user.id not in settings.admin_ids:
        await message.answer("Not allowed.")
        await state.clear()
        return

    try:
        n = int(message.text.strip())
        if n <= 0 or n > 500:
            raise ValueError()
    except ValueError:
        await message.answer(invalid_number())
        return

    data = await state.get_data()
    apkg_path = data.get("apkg_path")
    deck_title = data.get("deck_title") or "Deck"
    if not apkg_path:
        await message.answer("Import context lost. Upload the deck again.")
        await state.clear()
        return

    # Import now
    res = await import_apkg_from_path(
        settings=settings,
        bot=bot,
        bot_username=bot_username,
        sessionmaker=sessionmaker,
        admin_tg_id=message.from_user.id,
        apkg_path=str(apkg_path),
        deck_title=deck_title,
        new_per_day=n,
    )

    await message.answer(
        f"Imported: {res['imported']}, skipped: {res['skipped']}\n"
        f"Anki mode: {res['links']['anki']}\n"
        f"Watch mode: {res['links']['watch']}"
    )
    await state.clear()

    try:
        os.remove(apkg_path)
    except Exception:
        pass

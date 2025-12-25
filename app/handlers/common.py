from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import start_message
from app.bot.keyboards import kb_admin_home
from app.db.repo import get_or_create_user, unenroll_user_wipe_progress
from app.services.token_service import parse_payload

router = Router()

def _get_start_payload(message: Message) -> str:
    if not message.text:
        return ""
    parts = message.text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, settings, bot_username: str):
    # Deep-link /start payloads are handled elsewhere
    payload = _get_start_payload(message)
    if payload and parse_payload(payload):
        return

    # Admin menu (if ADMIN_IDS set; if empty -> everyone is admin)
    is_admin = (not settings.admin_ids) or (message.from_user.id in settings.admin_ids)
    if is_admin:
        await message.answer(start_message(), reply_markup=kb_admin_home(settings, message.from_user.id))
        return

    await message.answer(start_message())

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(start_message())

@router.message(Command("unroll_me"))
async def cmd_unroll_me(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user.id)
    await unenroll_user_wipe_progress(session, user.id)
    await message.answer("You have been unenrolled from all decks and your progress was erased.")

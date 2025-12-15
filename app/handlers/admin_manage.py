from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import kb_admin_deck, kb_admin_deck_list
from app.bot.messages import deck_link, invalid_number
from app.db.repo import get_deck_by_id, export_flags, rotate_deck_token, set_deck_active, update_deck_new_per_day, list_admin_decks, list_all_decks, delete_deck_full
from app.services.stats_service import admin_stats

router = Router()

class AdminSetN(StatesGroup):
    waiting = State()

@router.callback_query(F.data.startswith("ad_stats:"))
async def cb_ad_stats(call: CallbackQuery, session: AsyncSession):
    deck_id = call.data.split(":",1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck or deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return
    txt = await admin_stats(session, deck_id)
    await call.message.answer(txt, reply_markup=kb_admin_deck(deck_id))
    await call.answer()

@router.callback_query(F.data.startswith("ad_export:"))
async def cb_ad_export(call: CallbackQuery, session: AsyncSession):
    deck_id = call.data.split(":",1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck or deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return
    rows = await export_flags(session, deck_id)
    if not rows:
        await call.message.answer("No bad cards flagged yet.", reply_markup=kb_admin_deck(deck_id))
        await call.answer()
        return
    lines = ["note_guid,flags,answer"]
    for guid, ans, cnt in rows:
        ans_clean = ans.replace("\n"," ").replace(",",";")
        lines.append(f"{guid},{cnt},{ans_clean}")
    text = "\n".join(lines)
    # split if needed
    for chunk_start in range(0, len(text), 3500):
        await call.message.answer(text[chunk_start:chunk_start+3500])
    await call.message.answer("Export done.", reply_markup=kb_admin_deck(deck_id))
    await call.answer()

@router.callback_query(F.data.startswith("ad_rot:"))
async def cb_ad_rotate(call: CallbackQuery, session: AsyncSession, bot_username: str):
    deck_id = call.data.split(":",1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck or deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return
    token = await rotate_deck_token(session, deck_id)
    link = deck_link(bot_username, token)
    await call.message.answer(f"New link: {link}", reply_markup=kb_admin_deck(deck_id))
    await call.answer()

@router.callback_query(F.data.startswith("ad_dis:"))
async def cb_ad_disable(call: CallbackQuery, session: AsyncSession):
    deck_id = call.data.split(":",1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck or deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return
    await set_deck_active(session, deck_id, False)
    await call.message.answer("Deck disabled.")
    await call.answer()

@router.callback_query(F.data.startswith("ad_setn:"))
async def cb_ad_setn(call: CallbackQuery, state: FSMContext):
    deck_id = call.data.split(":",1)[1]
    await state.update_data(deck_id=deck_id)
    await state.set_state(AdminSetN.waiting)
    await call.message.answer("Send new N/day (integer).")
    await call.answer()

@router.message(AdminSetN.waiting, F.text)
async def on_admin_setn(message: Message, session: AsyncSession, state: FSMContext):
    try:
        n = int(message.text.strip())
        if n <= 0 or n > 500:
            raise ValueError()
    except ValueError:
        await message.answer(invalid_number())
        return
    data = await state.get_data()
    deck_id = data.get("deck_id")
    deck = await get_deck_by_id(session, deck_id)
    if not deck or deck.admin_tg_id != message.from_user.id:
        await message.answer("Not allowed.")
        await state.clear()
        return
    await update_deck_new_per_day(session, deck_id, n)
    await message.answer(f"N/day updated to {n}.", reply_markup=kb_admin_deck(deck_id))
    await state.clear()


def _is_admin(settings, tg_id: int) -> bool:
    return (not settings.admin_ids) or (tg_id in settings.admin_ids)

@router.callback_query(F.data == "ad_list")
async def cb_ad_list(call: CallbackQuery, session: AsyncSession, settings):
    if not _is_admin(settings, call.from_user.id):
        await call.answer("Not allowed", show_alert=True)
        return

    # If ADMIN_IDS is set, treat them as global admins -> show all decks.
    if settings.admin_ids:
        decks = await list_all_decks(session)
    else:
        decks = await list_admin_decks(session, call.from_user.id)

    items = [(d.id, d.title, bool(d.is_active)) for d in decks]
    if not items:
        await call.message.answer("No decks yet.")
        await call.answer()
        return

    await call.message.answer("Decks:", reply_markup=kb_admin_deck_list(items))
    await call.answer()

@router.callback_query(F.data.startswith("ad_open:"))
async def cb_ad_open(call: CallbackQuery, session: AsyncSession, bot_username: str, settings):
    if not _is_admin(settings, call.from_user.id):
        await call.answer("Not allowed", show_alert=True)
        return
    deck_id = call.data.split(":", 1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        await call.answer("Deck not found", show_alert=True)
        return
    # If ADMIN_IDS is empty, restrict to deck owner.
    if not settings.admin_ids and deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return
    link = deck_link(bot_username, deck.token)
    await call.message.answer(f"{deck.title}\n{link}", reply_markup=kb_admin_deck(deck_id))
    await call.answer()

@router.callback_query(F.data == "ad_close")
async def cb_ad_close(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data.startswith("ad_del:"))
async def cb_ad_delete_confirm(call: CallbackQuery, session: AsyncSession, settings):
    if not _is_admin(settings, call.from_user.id):
        await call.answer("Not allowed", show_alert=True)
        return
    deck_id = call.data.split(":", 1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        await call.answer("Deck not found", show_alert=True)
        return
    if not settings.admin_ids and deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return

    await call.message.answer(
        f"Delete deck '{deck.title}'?\nThis will remove all cards, enrollments, reviews, study sessions and flags.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Confirm delete", callback_data=f"ad_del2:{deck_id}")],
            [InlineKeyboardButton(text="Cancel", callback_data="ad_list")],
        ]),
    )
    await call.answer()

@router.callback_query(F.data.startswith("ad_del2:"))
async def cb_ad_delete_do(call: CallbackQuery, session: AsyncSession, settings):
    if not _is_admin(settings, call.from_user.id):
        await call.answer("Not allowed", show_alert=True)
        return
    deck_id = call.data.split(":", 1)[1]
    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        await call.answer("Deck not found", show_alert=True)
        return
    if not settings.admin_ids and deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return

    counts = await delete_deck_full(session, deck_id)
    await call.message.answer(f"Deck deleted. (cards={counts.get('cards',0)}, enrollments={counts.get('enrollments',0)})")
    await call.answer()


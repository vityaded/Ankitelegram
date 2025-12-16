from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo import (
    count_enrolled_students,
    get_deck_by_id,
    get_user_by_id,
    list_enrolled_students,
    unenroll_all_students_wipe_progress,
    unenroll_student_wipe_progress,
)
from app.services.student_progress import (
    get_daily_progress_history,
    get_overall_progress_summary,
    get_today_progress,
)
from app.utils.timez import now_tz, today_date

router = Router()

PAGE_SIZE = 10


def _is_admin(settings, tg_id: int) -> bool:
    return (not settings.admin_ids) or (tg_id in settings.admin_ids)


async def _ensure_deck_admin(call: CallbackQuery, session: AsyncSession, settings, deck_id: str):
    deck = await get_deck_by_id(session, deck_id)
    if not deck:
        await call.answer("Deck not found", show_alert=True)
        return None
    if not _is_admin(settings, call.from_user.id) and deck.admin_tg_id != call.from_user.id:
        await call.answer("Not allowed", show_alert=True)
        return None
    return deck


async def _display_user(bot: Bot, tg_id: int) -> tuple[str, str | None]:
    try:
        chat = await bot.get_chat(tg_id)
        parts = [chat.first_name or "", chat.last_name or ""]
        full_name = " ".join(p for p in parts if p).strip()
        username = chat.username
        if username and not full_name:
            full_name = f"@{username}"
        if not full_name:
            full_name = f"User {tg_id}"
        return full_name, username
    except Exception:
        return f"User {tg_id}", None


async def _student_list_text(bot: Bot, session: AsyncSession, deck_title: str, deck_id: str, settings, page: int):
    total = await count_enrolled_students(session, deck_id)
    if total == 0:
        text = f"{deck_title}\nNo students enrolled yet."
        return text, InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data=f"ad_open:{deck_id}")]]
        )

    today = today_date(settings.tz)
    start = page * PAGE_SIZE
    students = await list_enrolled_students(session, deck_id, offset=start, limit=PAGE_SIZE)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    lines = [f"Students for {deck_title}", f"Page {page + 1}/{total_pages}"]
    buttons: list[list[InlineKeyboardButton]] = []
    for user in students:
        name, _ = await _display_user(bot, user.tg_id)
        today_done, today_total = await get_today_progress(session, user.id, deck_id, today)
        overall = await get_overall_progress_summary(session, user.id, deck_id)
        overall_summary = f"{overall['started']}/{overall['total_cards']} started"
        lines.append(f"• {name}: today {today_done}/{today_total}, {overall_summary}")
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{name} ({today_done}/{today_total} today)",
                    callback_data=f"ad_student:{deck_id}:{user.id}:{page}",
                )
            ]
        )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"ad_students:{deck_id}:{page - 1}"))
    if start + len(students) < total:
        nav_row.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"ad_students:{deck_id}:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="Back", callback_data=f"ad_open:{deck_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    return "\n".join(lines), kb


@router.callback_query(F.data.startswith("ad_students:"))
async def cb_ad_student_list(call: CallbackQuery, session: AsyncSession, bot: Bot, settings):
    _, deck_id, *rest = call.data.split(":", 2)
    page = int(rest[0]) if rest else 0
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return
    text, kb = await _student_list_text(bot, session, deck.title, deck_id, settings, page)
    await call.message.answer(text, reply_markup=kb)
    await call.answer()


def _format_history(history: list[tuple]) -> str:
    lines = []
    for dt, done, total in history:
        lines.append(f"{dt}: {done}/{total}")
    return "\n".join(lines)


def _format_overall(overall: dict) -> str:
    states = overall.get("states", {})
    parts = [f"Total cards: {overall.get('total_cards', 0)}"]
    parts.append(f"Started: {overall.get('started', 0)}")
    if states:
        state_line = ", ".join(f"{k}: {v}" for k, v in states.items())
        parts.append(f"States: {state_line}")
    due = overall.get("due")
    if due is not None:
        parts.append(f"Due now: {due}")
    return "\n".join(parts)


@router.callback_query(F.data.startswith("ad_student:"))
async def cb_ad_student_detail(call: CallbackQuery, session: AsyncSession, bot: Bot, settings):
    _, deck_id, user_id, *rest = call.data.split(":", 3)
    page = int(rest[0]) if rest else 0
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return

    user = await get_user_by_id(session, user_id)
    if not user:
        await call.answer("Student not found", show_alert=True)
        return

    name, username = await _display_user(bot, user.tg_id)
    today = today_date(settings.tz)
    today_done, today_total = await get_today_progress(session, user.id, deck_id, today)
    history = await get_daily_progress_history(session, user.id, deck_id, today, days=7)
    overall = await get_overall_progress_summary(session, user.id, deck_id, now=now_tz(settings.tz))

    lines = [f"Deck: {deck.title}"]
    identity = f"Student: {name} (tg_id={user.tg_id})"
    if username:
        identity += f" @{username}"
    lines.append(identity)
    lines.append("")
    lines.append(f"Today: {today_done}/{today_total}")
    lines.append("Last 7 days:")
    lines.append(_format_history(history))
    lines.append("")
    lines.append("Overall:")
    lines.append(_format_overall(overall))

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Unenroll student", callback_data=f"ad_unenroll:{deck_id}:{user_id}")],
            [InlineKeyboardButton(text="Back", callback_data=f"ad_students:{deck_id}:{page}")],
        ]
    )
    await call.message.answer("\n".join(lines), reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("ad_unenroll:"))
async def cb_ad_unenroll_confirm(call: CallbackQuery, session: AsyncSession, settings):
    _, deck_id, user_id = call.data.split(":", 2)
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return
    text = (
        "Unenroll this student?\n"
        "This will remove enrollment and delete all progress for this deck."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm", callback_data=f"ad_unenroll2:{deck_id}:{user_id}")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"ad_students:{deck_id}:0")],
        ]
    )
    await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("ad_unenroll2:"))
async def cb_ad_unenroll_do(call: CallbackQuery, session: AsyncSession, bot: Bot, settings):
    _, deck_id, user_id = call.data.split(":", 2)
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return
    await unenroll_student_wipe_progress(session, user_id, deck_id)
    text, kb = await _student_list_text(bot, session, deck.title, deck_id, settings, 0)
    await call.message.answer("Student unenrolled and progress erased.")
    await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("ad_unenroll_all:"))
async def cb_ad_unenroll_all_confirm(call: CallbackQuery, session: AsyncSession, settings):
    deck_id = call.data.split(":", 1)[1]
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return
    text = (
        "Unenroll EVERYONE from this deck?\n"
        "This will remove enrollment and delete all progress for this deck."
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm", callback_data=f"ad_unenroll_all2:{deck_id}")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"ad_open:{deck_id}")],
        ]
    )
    await call.message.answer(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("ad_unenroll_all2:"))
async def cb_ad_unenroll_all_do(call: CallbackQuery, session: AsyncSession, bot: Bot, settings):
    deck_id = call.data.split(":", 1)[1]
    deck = await _ensure_deck_admin(call, session, settings, deck_id)
    if not deck:
        return
    await unenroll_all_students_wipe_progress(session, deck_id)
    text, kb = await _student_list_text(bot, session, deck.title, deck_id, settings, 0)
    await call.message.answer("All students unenrolled and progress erased.")
    await call.message.answer(text, reply_markup=kb)
    await call.answer()

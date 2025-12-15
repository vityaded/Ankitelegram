from __future__ import annotations

import hashlib
from dataclasses import dataclass
from aiogram import Bot
from aiogram.types import BufferedInputFile

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repo import find_file_id_by_sha

VIDEO_EXT = {".mp4",".webm",".mov",".mkv",".m4v"}
AUDIO_EXT = {".mp3",".m4a",".ogg",".wav",".flac"}

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def guess_kind(filename: str) -> str:
    fn = filename.lower()
    for ext in VIDEO_EXT:
        if fn.endswith(ext):
            return "video"
    for ext in AUDIO_EXT:
        if fn.endswith(ext):
            return "audio"
    # default video
    return "video"

async def get_or_upload_file_id(
    *,
    db: AsyncSession,
    bot: Bot,
    admin_tg_id: int,
    media_bytes: bytes,
    filename: str,
    media_sha256: str,
    media_kind: str,
) -> str:
    existing = await find_file_id_by_sha(db, media_sha256)
    if existing:
        return existing

    inp = BufferedInputFile(media_bytes, filename=filename)
    if media_kind == "audio":
        msg = await bot.send_audio(chat_id=admin_tg_id, audio=inp)
        if not msg.audio:
            raise RuntimeError("Telegram did not return audio object")
        return msg.audio.file_id
    else:
        msg = await bot.send_video(chat_id=admin_tg_id, video=inp, supports_streaming=True)
        if not msg.video:
            raise RuntimeError("Telegram did not return video object")
        return msg.video.file_id

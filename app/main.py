from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import load_settings
from app.logging_config import setup_logging
from app.bot.factory import create_bot, create_dispatcher
from app.db.engine import init_engine, get_sessionmaker
from app.db.models import Base

from app.utils.locks import LockRegistry

import uvicorn
from app.web.app import create_web_app
from app.services.scheduler import run_daily_7am_push, run_due_learning_push

logger = logging.getLogger("app.main")

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker):
        self._sessionmaker = sessionmaker

    async def __call__(self, handler, event, data):
        async with self._sessionmaker() as session:
            data["session"] = session
            return await handler(event, data)

class SettingsMiddleware(BaseMiddleware):
    def __init__(self, settings):
        self._settings = settings
    async def __call__(self, handler, event, data):
        data["settings"] = self._settings
        return await handler(event, data)

class BotUsernameMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot):
        self._bot = bot
        self._username = None

    async def __call__(self, handler, event, data):
        if self._username is None:
            me = await self._bot.get_me()
            self._username = me.username
        data["bot_username"] = self._username
        return await handler(event, data)

class LocksMiddleware(BaseMiddleware):
    def __init__(self, locks: LockRegistry):
        self._locks = locks
    async def __call__(self, handler, event, data):
        data["locks"] = self._locks
        return await handler(event, data)

class SessionmakerMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker):
        self._sessionmaker = sessionmaker
    async def __call__(self, handler, event, data):
        data["sessionmaker"] = self._sessionmaker
        return await handler(event, data)

async def _init_db(database_url: str):
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(database_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

async def run_web(settings, bot: Bot, bot_username: str, sessionmaker):
    app = create_web_app(settings=settings, bot=bot, bot_username=bot_username, sessionmaker=sessionmaker)
    config = uvicorn.Config(app, host=settings.web_host, port=settings.web_port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    setup_logging()
    settings = load_settings()

    init_engine(settings.database_url)
    sessionmaker = get_sessionmaker()

    # create tables
    await _init_db(settings.database_url)

    bot = create_bot(settings.bot_token)
    dp = create_dispatcher()

    locks = LockRegistry()

    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.update.middleware(SettingsMiddleware(settings))
    dp.update.middleware(BotUsernameMiddleware(bot))
    dp.update.middleware(LocksMiddleware(locks))
    dp.update.middleware(SessionmakerMiddleware(sessionmaker))

    me = await bot.get_me()
    bot_username = me.username

    logger.info("Bot started")
    logger.info("Web server: %s", f"{settings.web_base_url} (listening on {settings.web_host}:{settings.web_port})")

    await asyncio.gather(
        dp.start_polling(bot),
        run_web(settings, bot, bot_username, sessionmaker),
        run_daily_7am_push(bot=bot, settings=settings, sessionmaker=sessionmaker),
        run_due_learning_push(bot=bot, settings=settings, sessionmaker=sessionmaker),
    )

if __name__ == "__main__":
    asyncio.run(main())

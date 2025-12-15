from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

_engine = None
_sessionmaker = None

def init_engine(database_url: str) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url, echo=False, future=True)
    _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)

def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("DB engine not initialized")
    return _sessionmaker

async def get_session() -> AsyncSession:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session

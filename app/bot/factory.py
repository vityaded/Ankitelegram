from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers.student_join import router as student_join_router
from app.handlers.common import router as common_router
from app.handlers.admin_import import router as admin_import_router
from app.handlers.admin_manage import router as admin_manage_router
from app.handlers.admin_students import router as admin_students_router
from app.handlers.student_study import router as student_study_router
from app.handlers.callbacks import router as callbacks_router

def create_bot(token: str) -> Bot:
    return Bot(token=token)

def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Deep-link /start must be handled before generic /start.
    dp.include_router(student_join_router)
    dp.include_router(common_router)

    dp.include_router(admin_import_router)
    dp.include_router(admin_manage_router)
    dp.include_router(admin_students_router)
    dp.include_router(student_study_router)
    dp.include_router(callbacks_router)
    return dp

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

def now_tz(tz_name: str) -> datetime:
    return datetime.now(tz=ZoneInfo(tz_name))

def today_date(tz_name: str):
    return now_tz(tz_name).date()

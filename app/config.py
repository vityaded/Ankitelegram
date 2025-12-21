from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _get_env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v.strip() == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v

def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError as e:
        raise RuntimeError(f"Invalid int for {name}: {v}") from e


def _get_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == '':
        return default
    v = v.strip().lower()
    if v in ('1','true','yes','y','on'):
        return True
    if v in ('0','false','no','n','off'):
        return False
    raise RuntimeError(f"Invalid bool for {name}: {v}")

def _get_int_list(name: str, default_csv: str = "") -> list[int]:
    raw = os.getenv(name, default_csv).strip()
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError as e:
            raise RuntimeError(f"Invalid int in {name}: {part}") from e
    return out

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    tz: str
    similarity_ok: int
    similarity_almost: int
    learning_steps_minutes: list[int]
    learning_graduate_days: int
    import_tmp_dir: str

    subtitle_translate_enabled: bool
    subtitle_translate_source_lang: str
    subtitle_translate_target_lang: str
    translate_concurrency: int
    translate_min_delay_ms: int
    translate_max_retries: int
    translate_base_delay_ms: int
    translate_max_delay_ms: int
    import_concurrency: int

    admin_ids: set[int]
    upload_secret: str
    web_host: str
    web_port: int
    web_base_url: str

def load_settings() -> Settings:
    bot_token = _get_env("BOT_TOKEN")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Default: local SQLite
        database_url = "sqlite+aiosqlite:///./bot.db"

    tz = os.getenv("TZ", "Europe/Kyiv")
    similarity_ok = _get_int("SIMILARITY_OK", 93)
    similarity_almost = _get_int("SIMILARITY_ALMOST", 85)

    steps_raw = os.getenv("LEARNING_STEPS_MINUTES", "1,10")
    try:
        learning_steps_minutes = [int(x.strip()) for x in steps_raw.split(",") if x.strip()]
        if not learning_steps_minutes:
            raise ValueError("empty")
    except Exception as e:
        raise RuntimeError(f"Invalid LEARNING_STEPS_MINUTES: {steps_raw}") from e

    learning_graduate_days = _get_int("LEARNING_GRADUATE_DAYS", 1)
    import_tmp_dir = os.getenv("IMPORT_TMP_DIR", "/tmp/anki_listen_bot_import")

    subtitle_translate_enabled = _get_bool("SUBTITLE_TRANSLATE_ENABLED", True)
    subtitle_translate_source_lang = os.getenv("SUBTITLE_TRANSLATE_SOURCE_LANG", "auto")
    subtitle_translate_target_lang = os.getenv("SUBTITLE_TRANSLATE_TARGET_LANG", "uk")
    translate_concurrency = _get_int("TRANSLATE_CONCURRENCY", 1)
    translate_min_delay_ms = _get_int("TRANSLATE_MIN_DELAY_MS", 250)
    translate_max_retries = _get_int("TRANSLATE_MAX_RETRIES", 30)
    translate_base_delay_ms = _get_int("TRANSLATE_BASE_DELAY_MS", 750)
    translate_max_delay_ms = _get_int("TRANSLATE_MAX_DELAY_MS", 60000)
    import_concurrency = _get_int("IMPORT_CONCURRENCY", 1)

    admin_ids = set(_get_int_list("ADMIN_IDS", ""))
    upload_secret = _get_env("UPLOAD_SECRET", "change_me_to_a_long_random_secret")

    web_host = os.getenv("WEB_HOST", "0.0.0.0")
    web_port = _get_int("WEB_PORT", 8080)
    web_base_url = os.getenv("WEB_BASE_URL", f"http://127.0.0.1:{web_port}")

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        tz=tz,
        similarity_ok=similarity_ok,
        similarity_almost=similarity_almost,
        learning_steps_minutes=learning_steps_minutes,
        learning_graduate_days=learning_graduate_days,
        import_tmp_dir=import_tmp_dir,
        subtitle_translate_enabled=subtitle_translate_enabled,
        subtitle_translate_source_lang=subtitle_translate_source_lang,
        subtitle_translate_target_lang=subtitle_translate_target_lang,
        translate_concurrency=translate_concurrency,
        translate_min_delay_ms=translate_min_delay_ms,
        translate_max_retries=translate_max_retries,
        translate_base_delay_ms=translate_base_delay_ms,
        translate_max_delay_ms=translate_max_delay_ms,
        import_concurrency=import_concurrency,
        admin_ids=admin_ids,
        upload_secret=upload_secret,
        web_host=web_host,
        web_port=web_port,
        web_base_url=web_base_url.rstrip("/"),
    )

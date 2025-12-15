from __future__ import annotations

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TranslationCache, CardTranslation


@dataclass(frozen=True)
class TranslateConfig:
    enabled: bool
    source_lang: str
    target_lang: str
    concurrency: int
    min_delay_ms: int
    max_retries: int
    base_delay_ms: int
    max_delay_ms: int


# Module-level throttling across all imports in this process.
_translate_gate = asyncio.Lock()
_last_request_ts = 0.0


def _key(source_lang: str, target_lang: str, text: str) -> str:
    norm = (text or "").strip()
    raw = f"{source_lang}|{target_lang}|{norm}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def _throttle(min_delay_ms: int) -> None:
    global _last_request_ts
    if min_delay_ms <= 0:
        return
    async with _translate_gate:
        now = time.monotonic()
        wait = (_last_request_ts + (min_delay_ms / 1000.0)) - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_ts = time.monotonic()


def _parse_google_translate(payload) -> str:
    # Expected shape: [[['translated','original',...], ...], ...]
    try:
        parts = payload[0]
        if not isinstance(parts, list):
            return ""
        out = []
        for seg in parts:
            if isinstance(seg, list) and seg:
                t = seg[0]
                if isinstance(t, str):
                    out.append(t)
        return "".join(out).strip()
    except Exception:
        return ""


async def get_or_create_translation_cache(
    db: AsyncSession,
    *,
    source_lang: str,
    target_lang: str,
    text: str,
    cfg: TranslateConfig,
    sem: asyncio.Semaphore,
) -> Optional[str]:
    """Returns cache_key for translation_cache row, or None if translation disabled/failed."""
    if not cfg.enabled:
        return None

    src = (text or "").strip()
    if not src:
        return None

    cache_key = _key(source_lang, target_lang, src)

    # 1) cache hit
    res = await db.execute(select(TranslationCache).where(TranslationCache.key == cache_key))
    existing = res.scalar_one_or_none()
    if existing:
        return existing.key

    # 2) cache miss -> call translate
    translated = await translate_via_google(
        source_lang=source_lang,
        target_lang=target_lang,
        text=src,
        cfg=cfg,
        sem=sem,
    )
    if not translated:
        return None

    db.add(
        TranslationCache(
            key=cache_key,
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=src,
            translated_text=translated,
        )
    )
    # Flush so the row is visible to subsequent selects within the same transaction.
    await db.flush()
    return cache_key


async def translate_via_google(
    *,
    source_lang: str,
    target_lang: str,
    text: str,
    cfg: TranslateConfig,
    sem: asyncio.Semaphore,
) -> Optional[str]:
    """Unofficial endpoint. Retries on 429/5xx with exponential backoff."""
    # NOTE: This is an unofficial Google endpoint. For production, prefer an official provider.
    encoded_text = quote_plus(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={encoded_text}"
    )

    timeout = aiohttp.ClientTimeout(total=25)

    attempt = 0
    while True:
        attempt += 1
        try:
            async with sem:
                await _throttle(cfg.min_delay_ms)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        status = resp.status
                        if status == 200:
                            payload = await resp.json(content_type=None)
                            out = _parse_google_translate(payload)
                            if out:
                                return out
                            # empty/unknown payload: treat as retryable for a few attempts
                        elif status in (429, 500, 502, 503, 504):
                            # retryable
                            pass
                        else:
                            # non-retryable
                            return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        except Exception:
            # Unknown failure: do not loop forever.
            return None

        if attempt >= max(1, cfg.max_retries):
            return None

        # exponential backoff + jitter
        delay = cfg.base_delay_ms * (2 ** (attempt - 1))
        delay = min(delay, cfg.max_delay_ms)
        jitter = random.uniform(0.0, 0.25) * delay
        await asyncio.sleep((delay + jitter) / 1000.0)


async def link_card_translation(db: AsyncSession, *, card_id: str, cache_key: str) -> None:
    """Creates card_translations row (card_id -> translation_cache.key)."""
    if not cache_key:
        return
    db.add(CardTranslation(card_id=card_id, cache_key=cache_key))
    await db.flush()

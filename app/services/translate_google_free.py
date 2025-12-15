from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True)
class TranslationSettings:
    enabled: bool
    source_lang: str
    target_lang: str
    min_delay_s: float = 0.15
    timeout_s: float = 20.0
    max_retries: int = 60
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0


class GoogleFreeTranslator:
    """Unofficial Google Translate endpoint (no API key).

    Uses https://translate.googleapis.com/translate_a/single.

    Note: This endpoint is undocumented; it may be rate-limited or change.
    The implementation is deliberately conservative: low concurrency, delays,
    and exponential backoff on 429/5xx.
    """

    def __init__(self, http: aiohttp.ClientSession, settings: TranslationSettings):
        self._http = http
        self._s = settings
        self._cache: dict[str, str] = {}
        self._last_request_at: float | None = None

    async def translate(self, text: str) -> str | None:
        if not self._s.enabled:
            return None

        t = (text or "").strip()
        if not t:
            return ""

        cached = self._cache.get(t)
        if cached is not None:
            return cached

        # Keep URLs at safe lengths; split overly long text.
        if len(t) > 1500:
            parts = _split_text(t, 1200)
            out_parts: list[str] = []
            for part in parts:
                tr = await self._translate_once_with_retries(part)
                out_parts.append(tr)
            out = "".join(out_parts).strip()
            self._cache[t] = out
            return out

        out = await self._translate_once_with_retries(t)
        self._cache[t] = out
        return out

    async def _translate_once_with_retries(self, text: str) -> str:
        # polite pacing
        await self._sleep_if_needed()

        encoded = quote(text, safe="")
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={self._s.source_lang}&tl={self._s.target_lang}&dt=t&q={encoded}"
        )

        attempt = 0
        while True:
            attempt += 1
            try:
                timeout = aiohttp.ClientTimeout(total=self._s.timeout_s)
                async with self._http.get(url, timeout=timeout) as resp:
                    if resp.status in (429, 503, 502, 504):
                        await self._backoff_sleep(attempt, resp.status)
                        if attempt < self._s.max_retries:
                            continue
                    resp.raise_for_status()
                    data: Any = await resp.json(content_type=None)
                    translated = _parse_google_translate_response(data)
                    return translated

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Network issues: retry with backoff.
                await self._backoff_sleep(attempt, str(e))
                if attempt >= self._s.max_retries:
                    # Give up (return original text so UI doesn't break).
                    return ""

    async def _sleep_if_needed(self) -> None:
        if self._s.min_delay_s <= 0:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_request_at is None:
            self._last_request_at = now
            return
        delta = now - self._last_request_at
        if delta < self._s.min_delay_s:
            await asyncio.sleep(self._s.min_delay_s - delta)
        self._last_request_at = loop.time()

    async def _backoff_sleep(self, attempt: int, reason: Any) -> None:
        # exponential backoff with jitter
        base = self._s.backoff_base_s
        delay = min(self._s.backoff_max_s, base * (2 ** min(attempt, 10)))
        jitter = random.uniform(0, delay * 0.2)
        await asyncio.sleep(delay + jitter)


def _parse_google_translate_response(data: Any) -> str:
    # Typical structure: [[['Привіт', 'Hello', ...], ...], None, 'en', ...]
    try:
        segments = data[0]
        out = "".join((seg[0] or "") for seg in segments if seg and isinstance(seg, list))
        return (out or "").strip()
    except Exception:
        return ""


def _split_text(text: str, max_len: int) -> list[str]:
    # naive splitting by sentence-ish boundaries; falls back to hard splitting
    if len(text) <= max_len:
        return [text]

    seps = [". ", "! ", "? ", "\n", ", "]
    parts: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf:
            parts.append(buf)
            buf = ""

    tokens = [text]
    for sep in seps:
        if len(tokens) == 1:
            tokens = tokens[0].split(sep)
            if len(tokens) > 1:
                # re-add separator except for last
                tokens = [t + (sep if i < len(tokens) - 1 else "") for i, t in enumerate(tokens)]

    for tok in tokens:
        if len(buf) + len(tok) <= max_len:
            buf += tok
        else:
            flush()
            if len(tok) <= max_len:
                buf = tok
            else:
                # hard split
                for i in range(0, len(tok), max_len):
                    parts.append(tok[i : i + max_len])
    flush()
    return parts

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Hashable

class LockRegistry:
    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock(self, key: Hashable) -> asyncio.Lock:
        return self._locks[key]

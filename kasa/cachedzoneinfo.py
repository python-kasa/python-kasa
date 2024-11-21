"""Module for caching ZoneInfos."""

from __future__ import annotations

import asyncio
from zoneinfo import ZoneInfo


class CachedZoneInfo(ZoneInfo):
    """Cache ZoneInfo objects."""

    _cache: dict[str, ZoneInfo] = {}

    @classmethod
    async def get_cached_zone_info(cls, time_zone_str: str) -> ZoneInfo:
        """Get a cached zone info object."""
        if cached := cls._cache.get(time_zone_str):
            return cached
        loop = asyncio.get_running_loop()
        zinfo = await loop.run_in_executor(None, _get_zone_info, time_zone_str)
        cls._cache[time_zone_str] = zinfo
        return zinfo


def _get_zone_info(time_zone_str: str) -> ZoneInfo:
    """Get a time zone object for the given time zone string."""
    return ZoneInfo(time_zone_str)

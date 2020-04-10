"""Python library supporting TP-Link Smart Home devices.

The communication protocol was reverse engineered by Lubomir Stroetmann and
Tobias Esser in 'Reverse Engineering the TP-Link HS110':
https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/

This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
Stroetmann which is licensed under the Apache License, Version 2.0.

You may obtain a copy of the license at
http://www.apache.org/licenses/LICENSE-2.0
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

_LOGGER = logging.getLogger(__name__)


class SmartCache:
    """Base cache class."""

    CACHE_TTLS = {
        "get_daystat": timedelta(seconds=21600),
        "get_monthstat": timedelta(seconds=86400),
    }

    CACHE_INVALIDATE_ON_SET = [
        ["smartlife.iot.common.emeter", "get_realtime"],
        ["smartlife.iot.smartbulb.lightingservice", "get_light_state"],
    ]

    def __init__(self, cache_ttl: int = 3) -> None:
        """Create a new SmartCache instance.

        :param cache_ttl: the default cache ttl
        """
        self.cache_ttl = timedelta(seconds=cache_ttl)
        if cache_ttl == 0:
            self.CACHE_TTLS = {}
        _LOGGER.debug(
            "Initializing cache ttl %s and smart cache: %s",
            self.cache_ttl,
            self.CACHE_TTLS,
        )
        self._cache: Dict = {}

    def _result_from_cache(self, target, cmd) -> Optional[Dict]:
        """Return query result from cache if still fresh.

        Only results from commands starting with `get_` are considered cacheable.

        :param target: Target system
        :param cmd: Command
        :rtype: query result or None if expired.
        """
        _LOGGER.debug("Checking cache for %s %s", target, cmd)

        if target not in self._cache or cmd not in self._cache[target]:
            return None

        if not self._is_cacheable(cmd):
            return None

        cache_ttl = self.CACHE_TTLS.get(cmd, self.cache_ttl)
        _LOGGER.debug("Cache ttl for target:%s cmd:%s is %s", target, cmd, cache_ttl)

        if self._cache[target][cmd]["last_updated"] + cache_ttl > datetime.utcnow():
            _LOGGER.debug("Got cache %s %s", target, cmd)
            return self._cache[target][cmd]
        else:
            _LOGGER.debug("Cleaning expired cache for %s cmd %s", target, cmd)
            del self._cache[target][cmd]

        return None

    def _insert_to_cache(self, target: str, cmd: str, response: Dict) -> None:
        """Add response for a given command to the cache.

        :param target: Target system
        :param cmd: Command
        :param response: Response to be cached
        """
        self._cache.setdefault(target, {})
        response_copy = response.copy()
        response_copy["last_updated"] = datetime.utcnow()
        self._cache[target][cmd] = response_copy

    def _is_cacheable(self, cmd: str) -> bool:
        """Determine if a cmd is cacheable."""
        return cmd.startswith("get_")

    def _is_setter(self, cmd: str) -> bool:
        """Determine if a cmd will change state."""
        return cmd.startswith("set_") or cmd.startswith("transition_")

    def _invalidate_caches_on_set(self) -> None:
        """Invalidate cache on state change."""
        for target, cmd in self.CACHE_INVALIDATE_ON_SET:
            if target not in self._cache:
                continue
            if cmd not in self._cache[target]:
                continue
            _LOGGER.debug(
                "Invalidating the cache for %s cmd %s due to state change", target, cmd,
            )
            del self._cache[target][cmd]

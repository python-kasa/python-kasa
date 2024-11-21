"""Module for io device timezone lookups."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, tzinfo
from typing import cast
from zoneinfo import ZoneInfo

from ..cachedzoneinfo import CachedZoneInfo

_LOGGER = logging.getLogger(__name__)


async def get_timezone(index: int) -> tzinfo:
    """Get the timezone from the index."""
    if index > 109:
        _LOGGER.error(
            "Unexpected index %s not configured as a timezone, defaulting to UTC", index
        )
        return await CachedZoneInfo.get_cached_zone_info("Etc/UTC")

    name = TIMEZONE_INDEX[index]
    return await CachedZoneInfo.get_cached_zone_info(name)


async def get_timezone_index(tzone: tzinfo) -> int:
    """Return the iot firmware index for a valid IANA timezone key."""
    if isinstance(tzone, ZoneInfo):
        name = tzone.key
        rev = {val: key for key, val in TIMEZONE_INDEX.items()}
        if name in rev:
            return rev[name]

    for i in range(110):
        if _is_same_timezone(tzone, await get_timezone(i)):
            return i
    raise ValueError("Device does not support timezone %s", name)


async def get_matching_timezones(tzone: tzinfo) -> list[str]:
    """Return the iot firmware index for a valid IANA timezone key."""
    matches = []
    if isinstance(tzone, ZoneInfo):
        name = tzone.key
        vals = {val for val in TIMEZONE_INDEX.values()}
        if name in vals:
            matches.append(name)

    for i in range(110):
        fw_tz = await get_timezone(i)
        if _is_same_timezone(tzone, fw_tz):
            match_key = cast(ZoneInfo, fw_tz).key
            if match_key not in matches:
                matches.append(match_key)
    return matches


def _is_same_timezone(tzone1: tzinfo, tzone2: tzinfo) -> bool:
    """Return true if the timezones have the same utcffset and dst offset.

    Iot devices only support a limited static list of IANA timezones; this is used to
    check if a static timezone matches the same utc offset and dst settings.
    """
    now = datetime.now()
    start_day = datetime(now.year, 1, 1, 12)
    for i in range(365):
        the_day = start_day + timedelta(days=i)
        if tzone1.utcoffset(the_day) != tzone2.utcoffset(the_day):
            return False
    return True


TIMEZONE_INDEX = {
    0: "Etc/GMT+12",
    1: "Pacific/Samoa",
    2: "US/Hawaii",
    3: "US/Alaska",
    4: "Mexico/BajaNorte",
    5: "Etc/GMT+8",
    6: "PST8PDT",
    7: "US/Arizona",
    8: "America/Mazatlan",
    9: "MST",
    10: "MST7MDT",
    11: "Mexico/General",
    12: "Etc/GMT+6",
    13: "CST6CDT",
    14: "America/Monterrey",
    15: "Canada/Saskatchewan",
    16: "America/Bogota",
    17: "Etc/GMT+5",
    18: "EST",
    19: "America/Indiana/Indianapolis",
    20: "America/Caracas",
    21: "America/Asuncion",
    22: "Etc/GMT+4",
    23: "Canada/Atlantic",
    24: "America/Cuiaba",
    25: "Brazil/West",
    26: "America/Santiago",
    27: "Canada/Newfoundland",
    28: "America/Sao_Paulo",
    29: "America/Argentina/Buenos_Aires",
    30: "America/Cayenne",
    31: "America/Miquelon",
    32: "America/Montevideo",
    33: "Chile/Continental",
    34: "Etc/GMT+2",
    35: "Atlantic/Azores",
    36: "Atlantic/Cape_Verde",
    37: "Africa/Casablanca",
    38: "UCT",
    39: "GB",
    40: "Africa/Monrovia",
    41: "Europe/Amsterdam",
    42: "Europe/Belgrade",
    43: "Europe/Brussels",
    44: "Europe/Sarajevo",
    45: "Africa/Lagos",
    46: "Africa/Windhoek",
    47: "Asia/Amman",
    48: "Europe/Athens",
    49: "Asia/Beirut",
    50: "Africa/Cairo",
    51: "Asia/Damascus",
    52: "EET",
    53: "Africa/Harare",
    54: "Europe/Helsinki",
    55: "Asia/Istanbul",
    56: "Asia/Jerusalem",
    57: "Europe/Kaliningrad",
    58: "Africa/Tripoli",
    59: "Asia/Baghdad",
    60: "Asia/Kuwait",
    61: "Europe/Minsk",
    62: "Europe/Moscow",
    63: "Africa/Nairobi",
    64: "Asia/Tehran",
    65: "Asia/Muscat",
    66: "Asia/Baku",
    67: "Europe/Samara",
    68: "Indian/Mauritius",
    69: "Asia/Tbilisi",
    70: "Asia/Yerevan",
    71: "Asia/Kabul",
    72: "Asia/Ashgabat",
    73: "Asia/Yekaterinburg",
    74: "Asia/Karachi",
    75: "Asia/Kolkata",
    76: "Asia/Colombo",
    77: "Asia/Kathmandu",
    78: "Asia/Almaty",
    79: "Asia/Dhaka",
    80: "Asia/Novosibirsk",
    81: "Asia/Rangoon",
    82: "Asia/Bangkok",
    83: "Asia/Krasnoyarsk",
    84: "Asia/Chongqing",
    85: "Asia/Irkutsk",
    86: "Asia/Singapore",
    87: "Australia/Perth",
    88: "Asia/Taipei",
    89: "Asia/Ulaanbaatar",
    90: "Asia/Tokyo",
    91: "Asia/Seoul",
    92: "Asia/Yakutsk",
    93: "Australia/Adelaide",
    94: "Australia/Darwin",
    95: "Australia/Brisbane",
    96: "Australia/Canberra",
    97: "Pacific/Guam",
    98: "Australia/Hobart",
    99: "Antarctica/DumontDUrville",
    100: "Asia/Magadan",
    101: "Asia/Srednekolymsk",
    102: "Etc/GMT-11",
    103: "Asia/Anadyr",
    104: "Pacific/Auckland",
    105: "Etc/GMT-12",
    106: "Pacific/Fiji",
    107: "Etc/GMT-13",
    108: "Pacific/Apia",
    109: "Etc/GMT-14",
}

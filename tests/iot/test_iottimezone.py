from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pytest_mock import MockerFixture


def test_expected_dst_behavior_for_index_cases():
    """Exercise expected_dst_behavior_for_index for several representative indices."""
    from kasa.iot.iottimezone import expected_dst_behavior_for_index

    # Posix-style DST zones
    assert expected_dst_behavior_for_index(10) is True  # MST7MDT
    assert expected_dst_behavior_for_index(13) is True  # CST6CDT
    # Fixed-offset or fixed-abbreviation zones
    assert expected_dst_behavior_for_index(34) is False  # Etc/GMT+2
    assert expected_dst_behavior_for_index(18) is False  # EST
    # Invalid/unknown index
    assert expected_dst_behavior_for_index(999) is None


async def test_guess_timezone_by_offset_fixed_fallback_unit():
    """When no ZoneInfo matches, return a fixed-offset tzinfo."""
    import kasa.iot.iottimezone as tzmod

    year = datetime.now(UTC).year
    when = datetime(year, 1, 15, 12, tzinfo=UTC)
    offset = timedelta(minutes=2)  # unlikely to match any real zone
    tz = await tzmod.guess_timezone_by_offset(offset, when_utc=when)
    assert tz.utcoffset(when) == offset


async def test_guess_timezone_by_offset_candidates_unit():
    """Cover naive when_utc branch and candidate selection path (non-empty candidates)."""
    import kasa.iot.iottimezone as tzmod

    # naive datetime hits the 'naive -> UTC' branch
    when = datetime(2025, 1, 15, 12)
    offset = timedelta(0)
    tz = await tzmod.guess_timezone_by_offset(offset, when_utc=when)

    # Should choose a ZoneInfo candidate (not the fixed-offset fallback), with matching offset
    assert isinstance(tz, ZoneInfo)
    assert tz.utcoffset(when.replace(tzinfo=UTC)) == offset


async def test_guess_timezone_by_offset_dst_expected_true_filters(
    mocker: MockerFixture,
):
    """dst_expected=True should prefer a DST-observing zone when possible."""
    import kasa.iot.iottimezone as tzmod

    when = datetime(datetime.now(UTC).year, 1, 15, 12, tzinfo=UTC)
    tz = await tzmod.guess_timezone_by_offset(
        timedelta(0), when_utc=when, dst_expected=True
    )
    assert tz.utcoffset(when) == timedelta(0)
    if isinstance(tz, ZoneInfo):
        jan = datetime(when.year, 1, 15, 12, tzinfo=UTC).astimezone(tz).utcoffset()
        jul = datetime(when.year, 7, 15, 12, tzinfo=UTC).astimezone(tz).utcoffset()
        assert jan != jul  # observes DST


async def test_guess_timezone_by_offset_dst_expected_false_prefers_non_dst():
    """dst_expected=False should prefer a non-DST zone and skip DST candidates (covers False branch)."""
    import kasa.iot.iottimezone as tzmod

    when = datetime(datetime.now(UTC).year, 1, 15, 12, tzinfo=UTC)
    tz = await tzmod.guess_timezone_by_offset(
        timedelta(0), when_utc=when, dst_expected=False
    )
    assert tz.utcoffset(when) == timedelta(0)
    if isinstance(tz, ZoneInfo):
        jan = datetime(when.year, 1, 15, 12, tzinfo=UTC).astimezone(tz).utcoffset()
        jul = datetime(when.year, 7, 15, 12, tzinfo=UTC).astimezone(tz).utcoffset()
        assert jan == jul  # non-DST zone chosen


async def test_guess_timezone_by_offset_handles_missing_zoneinfo_unit(
    mocker: MockerFixture,
):
    """Cover the ZoneInfoNotFoundError continue path within guess_timezone_by_offset."""
    from zoneinfo import ZoneInfoNotFoundError as ZNF

    import kasa.iot.iottimezone as tzmod

    original = tzmod.CachedZoneInfo.get_cached_zone_info

    async def flaky_get(name: str):
        # Force the first entry to raise to exercise the except path (143-144)
        first_name = next(iter(tzmod.TIMEZONE_INDEX.values()))
        if name == first_name:
            raise ZNF("unavailable on host")
        return await original(name)

    mocker.patch.object(tzmod.CachedZoneInfo, "get_cached_zone_info", new=flaky_get)

    when = datetime(datetime.now(UTC).year, 1, 15, 12, tzinfo=UTC)
    tz = await tzmod.guess_timezone_by_offset(timedelta(0), when_utc=when)
    assert tz.utcoffset(when) == timedelta(0)


async def test_get_timezone_index_direct_match():
    """If ZoneInfo key is in TIMEZONE_INDEX, return index directly."""
    import kasa.iot.iottimezone as tzmod

    idx = await tzmod.get_timezone_index(ZoneInfo("GB"))
    assert idx == 39  # "GB" is mapped to index 39


async def test_get_timezone_index_non_zoneinfo_unit():
    """Exercise get_timezone_index path when input tzinfo is not a ZoneInfo instance."""
    import kasa.iot.iottimezone as tzmod

    # Fixed offset +0 should match a valid index (e.g., UCT/Africa/Monrovia)
    idx = await tzmod.get_timezone_index(timezone(timedelta(0)))
    assert isinstance(idx, int)
    assert 0 <= idx <= 109


async def test_get_timezone_index_skips_missing_unit(mocker: MockerFixture):
    """Cover ZoneInfoNotFoundError path in get_timezone_index loop and successful match."""
    from zoneinfo import ZoneInfoNotFoundError as ZNF

    import kasa.iot.iottimezone as tzmod

    original_get_tz = tzmod.get_timezone

    async def side_effect(i: int):
        if i < 5:
            raise ZNF("unavailable on host")
        return await original_get_tz(i)

    mocker.patch("kasa.iot.iottimezone.get_timezone", new=side_effect)

    # Use a ZoneInfo not directly present in TIMEZONE_INDEX values to avoid early return
    idx = await tzmod.get_timezone_index(ZoneInfo("Europe/London"))
    assert isinstance(idx, int)
    assert 0 <= idx <= 109
    assert idx >= 5


async def test_get_timezone_index_raises_for_unmatched_unit():
    """Ensure get_timezone_index completes loop and raises when no match exists (covers raise branch)."""
    import kasa.iot.iottimezone as tzmod

    # Uncommon 2-minute offset won't match any real zone in TIMEZONE_INDEX
    with pytest.raises(ValueError, match="Device does not support timezone"):
        await tzmod.get_timezone_index(timezone(timedelta(minutes=2)))


async def test_get_matching_timezones_branches_unit(mocker: MockerFixture):
    """Cover initial append, except path, and duplicate suppression in get_matching_timezones."""
    from zoneinfo import ZoneInfoNotFoundError as ZNF

    import kasa.iot.iottimezone as tzmod

    original_get_tz = tzmod.get_timezone

    async def side_effect(i: int):
        # Force one miss to hit the except path
        if i == 0:
            raise ZNF("unavailable on host")
        return await original_get_tz(i)

    mocker.patch("kasa.iot.iottimezone.get_timezone", new=side_effect)

    # 'GB' is in TIMEZONE_INDEX; passing ZoneInfo('GB') will trigger initial append
    matches = await tzmod.get_matching_timezones(ZoneInfo("GB"))
    assert "GB" in matches  # initial append done
    # Loop should find GB again but not duplicate it


async def test_get_matching_timezones_non_zoneinfo_unit():
    """Exercise get_matching_timezones when input tzinfo is not a ZoneInfo (skips initial append)."""
    import kasa.iot.iottimezone as tzmod

    matches = await tzmod.get_matching_timezones(timezone(timedelta(0)))
    assert isinstance(matches, list)
    assert len(matches) > 0


async def test_get_timezone_out_of_range_defaults_to_utc():
    """Out-of-range index should log and default to UTC."""
    import kasa.iot.iottimezone as tzmod

    tz = await tzmod.get_timezone(-1)
    assert isinstance(tz, ZoneInfo)
    assert tz.key in ("Etc/UTC", "UTC")  # platform alias acceptable

    tz2 = await tzmod.get_timezone(999)
    assert isinstance(tz2, ZoneInfo)
    assert tz2.key in ("Etc/UTC", "UTC")

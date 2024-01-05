import datetime
from unittest.mock import Mock

import pytest

from kasa.modules import Usage


def test_usage_convert_stat_data():
    usage = Usage(None, module="usage")

    test_data = []
    assert usage._convert_stat_data(test_data, "day") == {}

    test_data = [
        {"year": 2016, "month": 5, "day": 2, "time": 20},
        {"year": 2016, "month": 5, "day": 4, "time": 30},
    ]
    d = usage._convert_stat_data(test_data, "day")
    assert len(d) == len(test_data)
    assert isinstance(d, dict)
    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, int)
    assert k == 4 and v == 30


def test_usage_today():
    """Test fetching the usage for today.

    This test uses inline data since the fixtures
    will not have data for the current day.
    """
    emeter_data = {
        "get_daystat": {
            "day_list": [{"day": 1, "time": 8, "month": 1, "year": 2023}],
            "err_code": 0,
        }
    }

    class MockUsage(Usage):
        @property
        def data(self):
            return emeter_data

    usage = MockUsage(Mock(), "usage")
    now = datetime.datetime.now()
    day = now.day
    month = now.month
    year = now.year
    emeter_data["get_daystat"]["day_list"].append(
        {"day": day, "time": 500, "month": month, "year": year}
    )
    assert usage.usage_today == 500


def test_usage_this_month():
    """Test fetching the usage for this month.

    This test uses inline data since the fixtures
    will not have data for the current month.
    """
    emeter_data = {
        "get_monthstat": {
            "month_list": [{"time": 8, "month": 1, "year": 2023}],
            "err_code": 0,
        }
    }

    class MockUsage(Usage):
        @property
        def data(self):
            return emeter_data

    usage = MockUsage(Mock(), "usage")
    now = datetime.datetime.now()
    month = now.month
    year = now.year
    emeter_data["get_monthstat"]["month_list"].append(
        {"time": 500, "month": month, "year": year}
    )
    assert usage.usage_this_month == 500

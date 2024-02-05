import datetime
from unittest.mock import Mock

from kasa.iot.modules import Usage


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
            "day_list": [],
            "err_code": 0,
        }
    }

    class MockUsage(Usage):
        @property
        def data(self):
            return emeter_data

    usage = MockUsage(Mock(), "usage")
    assert usage.usage_today is None
    now = datetime.datetime.now()
    emeter_data["get_daystat"]["day_list"].extend(
        [
            {"day": now.day - 1, "time": 200, "month": now.month - 1, "year": now.year},
            {"day": now.day, "time": 500, "month": now.month, "year": now.year},
            {"day": now.day + 1, "time": 100, "month": now.month + 1, "year": now.year},
        ]
    )
    assert usage.usage_today == 500


def test_usage_this_month():
    """Test fetching the usage for this month.

    This test uses inline data since the fixtures
    will not have data for the current month.
    """
    emeter_data = {
        "get_monthstat": {
            "month_list": [],
            "err_code": 0,
        }
    }

    class MockUsage(Usage):
        @property
        def data(self):
            return emeter_data

    usage = MockUsage(Mock(), "usage")
    assert usage.usage_this_month is None
    now = datetime.datetime.now()
    emeter_data["get_monthstat"]["month_list"].extend(
        [
            {"time": 200, "month": now.month - 1, "year": now.year},
            {"time": 500, "month": now.month, "year": now.year},
            {"time": 100, "month": now.month + 1, "year": now.year},
        ]
    )
    assert usage.usage_this_month == 500

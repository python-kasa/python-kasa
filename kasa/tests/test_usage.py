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

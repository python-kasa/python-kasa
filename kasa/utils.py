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


import collections.abc
from collections import defaultdict
from typing import DefaultDict


def merge(d, u):
    """Update dict recursively."""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = merge(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def merge_sums(dicts):
    """Merge the sum of dicts."""
    total_dict: DefaultDict[int, float] = defaultdict(lambda: 0.0)
    for sum_dict in dicts:
        for day, value in sum_dict.items():
            total_dict[day] += value
    return total_dict

"""Python library supporting TP-Link Smart Home devices."""

from __future__ import annotations


def merge(dest: dict, source: dict) -> dict:
    """Update dict recursively."""
    for k, v in source.items():
        if k in dest and isinstance(v, dict):
            dest[k] = merge(dest[k], v)
        else:
            dest[k] = v
    return dest

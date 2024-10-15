"""Package for experimental."""

from .smartcamera import SmartCamera


class _Experimental:
    enabled = False

    @classmethod
    def set(cls, value):
        cls.enabled = value


__all__ = [
    "SmartCamera",
]

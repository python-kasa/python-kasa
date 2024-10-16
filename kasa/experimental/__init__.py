"""Package for experimental."""

from .smartcamera import SmartCamera
from .smartcameraprotocol import SmartCameraProtocol


class _Experimental:
    enabled = False

    @classmethod
    def set(cls, value):
        cls.enabled = value


__all__ = [
    "SmartCamera",
    "SmartCameraProtocol",
]

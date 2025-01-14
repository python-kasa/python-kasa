"""Modules for SMARTCAM devices."""

from .alarm import Alarm
from .babycrydetection import BabyCryDetection
from .battery import Battery
from .camera import Camera
from .childdevice import ChildDevice
from .device import DeviceModule
from .homekit import HomeKit
from .led import Led
from .lensmask import LensMask
from .matter import Matter
from .motiondetection import MotionDetection
from .pantilt import PanTilt
from .persondetection import PersonDetection
from .tamperdetection import TamperDetection
from .time import Time

__all__ = [
    "Alarm",
    "BabyCryDetection",
    "Battery",
    "Camera",
    "ChildDevice",
    "DeviceModule",
    "Led",
    "PanTilt",
    "PersonDetection",
    "Time",
    "HomeKit",
    "Matter",
    "MotionDetection",
    "LensMask",
    "TamperDetection",
]

"""Modules for SMARTCAM devices."""

from .alarm import Alarm
from .babycrydetection import BabyCryDetection
from .battery import Battery
from .camera import Camera
from .childdevice import ChildDevice
from .childsetup import ChildSetup
from .device import DeviceModule
from .homekit import HomeKit
from .led import Led
from .lensmask import LensMask
from .matter import Matter
from .motiondetection import MotionDetection
from .pantilt import PanTilt
from .persondetection import PersonDetection
from .petdetection import PetDetection
from .tamperdetection import TamperDetection
from .time import Time

__all__ = [
    "Alarm",
    "BabyCryDetection",
    "Battery",
    "Camera",
    "ChildDevice",
    "ChildSetup",
    "DeviceModule",
    "Led",
    "PanTilt",
    "PersonDetection",
    "PetDetection",
    "Time",
    "HomeKit",
    "Matter",
    "MotionDetection",
    "LensMask",
    "TamperDetection",
]

"""Modules for SMARTCAM devices."""

from .alarm import Alarm
from .babycrydetection import BabyCryDetection
from .barkdetection import BarkDetection
from .battery import Battery
from .camera import Camera
from .childdevice import ChildDevice
from .childsetup import ChildSetup
from .device import DeviceModule
from .glassdetection import GlassDetection
from .homekit import HomeKit
from .led import Led
from .lensmask import LensMask
from .linecrossingdetection import LineCrossingDetection
from .lock import Lock
from .lockhistory import LockHistory
from .matter import Matter
from .meowdetection import MeowDetection
from .motiondetection import MotionDetection
from .pantilt import PanTilt
from .persondetection import PersonDetection
from .petdetection import PetDetection
from .tamperdetection import TamperDetection
from .time import Time
from .vehicledetection import VehicleDetection

__all__ = [
    "Alarm",
    "BabyCryDetection",
    "BarkDetection",
    "Battery",
    "Camera",
    "ChildDevice",
    "ChildSetup",
    "DeviceModule",
    "GlassDetection",
    "Led",
    "LineCrossingDetection",
    "Lock",
    "LockHistory",
    "MeowDetection",
    "PanTilt",
    "PersonDetection",
    "PetDetection",
    "Time",
    "HomeKit",
    "Matter",
    "MotionDetection",
    "LensMask",
    "TamperDetection",
    "VehicleDetection",
]

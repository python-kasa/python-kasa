"""Module for a TAPO Plug."""

from __future__ import annotations

import logging
from abc import ABC

from .device import Device

_LOGGER = logging.getLogger(__name__)


class Plug(Device, ABC):
    """Base class to represent a Plug."""

"""Base class for all module implementations."""
import logging
from abc import ABC, abstractmethod
from typing import Dict

from .descriptors import Descriptor
from .device import Device

_LOGGER = logging.getLogger(__name__)


class Module(ABC):
    """Base class implemention for all modules.

    The base classes should implement `query` to return the query they want to be
    executed during the regular update cycle.
    """

    def __init__(self, device: "Device", module: str):
        self._device = device
        self._module = module
        self._module_descriptors: Dict[str, Descriptor] = {}

    def add_descriptor(self, desc):
        """Add module descriptor."""
        module_desc_name = f"{self._module}_{desc.name}"
        if module_desc_name in self._module_descriptors:
            raise Exception("Duplicate name detected %s" % module_desc_name)
        self._module_descriptors[module_desc_name] = desc

    @abstractmethod
    def query(self):
        """Query to execute during the update cycle.

        The inheriting modules implement this to include their wanted
        queries to the query that gets executed when Device.update() gets called.
        """

    @property
    @abstractmethod
    def data(self):
        """Return the module specific raw data from the last update."""

    @property
    @abstractmethod
    def is_supported(self) -> bool:
        """Return whether the module is supported by the device."""

    def __repr__(self) -> str:
        return (
            f"<Module {self.__class__.__name__} ({self._module})"
            f" for {self._device.host}>"
        )

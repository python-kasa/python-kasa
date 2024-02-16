"""Base implementation for SMART modules."""
import logging
from typing import Dict, Type

from ..exceptions import SmartDeviceException
from ..module import Module
from .smartdevice import SmartDevice

_LOGGER = logging.getLogger(__name__)


class SmartModule(Module):
    """Base class for SMART modules."""

    NAME: str
    REQUIRED_COMPONENT: str
    QUERY_GETTER_NAME: str
    REGISTERED_MODULES: Dict[str, Type["SmartModule"]] = {}

    def __init__(self, device: "SmartDevice", module: str):
        self._device: SmartDevice
        super().__init__(device, module)

    def __init_subclass__(cls, **kwargs):
        assert cls.REQUIRED_COMPONENT is not None  # noqa: S101

        name = getattr(cls, "NAME", cls.__name__)
        _LOGGER.debug("Registering %s" % cls)
        cls.REGISTERED_MODULES[name] = cls

    @property
    def name(self) -> str:
        """Name of the module."""
        return getattr(self, "NAME", self.__class__.__name__)

    def query(self) -> Dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        return {self.QUERY_GETTER_NAME: None}

    def call(self, method, params=None):
        """Call a method.

        Just a helper method.
        """
        return self._device._query_helper(method, params)

    @property
    def data(self):
        """Return response data for the module.

        If module performs only a single query, the resulting response is unwrapped.
        """
        q = self.query()
        q_keys = list(q.keys())
        # TODO: hacky way to check if update has been called.
        if q_keys[0] not in self._device._last_update:
            raise SmartDeviceException(
                f"You need to call update() prior accessing module data"
                f" for '{self._module}'"
            )

        filtered_data = {
            k: v for k, v in self._device._last_update.items() if k in q_keys
        }
        if len(filtered_data) == 1:
            return next(iter(filtered_data.values()))

        return filtered_data

    @property
    def is_supported(self) -> bool:
        """Return True modules are initialized if they are seen in the negotiation."""
        return True

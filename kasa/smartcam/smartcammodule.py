"""Base implementation for SMART modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from ..exceptions import DeviceError, KasaException, SmartErrorCode
from ..modulemapping import ModuleName
from ..smart.smartmodule import SmartModule

if TYPE_CHECKING:
    from . import modules
    from .smartcamdevice import SmartCamDevice

_LOGGER = logging.getLogger(__name__)


class SmartCamModule(SmartModule):
    """Base class for SMARTCAM modules."""

    SmartCamAlarm: Final[ModuleName[modules.Alarm]] = ModuleName("SmartCamAlarm")
    SmartCamMotionDetection: Final[ModuleName[modules.MotionDetection]] = ModuleName(
        "MotionDetection"
    )
    SmartCamPersonDetection: Final[ModuleName[modules.PersonDetection]] = ModuleName(
        "PersonDetection"
    )
    SmartCamPetDetection: Final[ModuleName[modules.PetDetection]] = ModuleName(
        "PetDetection"
    )
    SmartCamTamperDetection: Final[ModuleName[modules.TamperDetection]] = ModuleName(
        "TamperDetection"
    )
    SmartCamBabyCryDetection: Final[ModuleName[modules.BabyCryDetection]] = ModuleName(
        "BabyCryDetection"
    )

    SmartCamBattery: Final[ModuleName[modules.Battery]] = ModuleName("Battery")

    SmartCamDeviceModule: Final[ModuleName[modules.DeviceModule]] = ModuleName(
        "devicemodule"
    )

    #: Module name to be queried
    QUERY_MODULE_NAME: str
    #: Section name or names to be queried
    QUERY_SECTION_NAMES: str | list[str] | None = None

    REGISTERED_MODULES = {}

    _device: SmartCamDevice

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        if not self.QUERY_GETTER_NAME:
            return {}
        section_names = (
            {"name": self.QUERY_SECTION_NAMES} if self.QUERY_SECTION_NAMES else {}
        )
        return {self.QUERY_GETTER_NAME: {self.QUERY_MODULE_NAME: section_names}}

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Call a method.

        Just a helper method.
        """
        return await self._device._query_helper(method, params)

    @property
    def data(self) -> dict:
        """Return response data for the module."""
        dev = self._device
        q = self.query()

        if not q:
            return dev.sys_info

        if len(q) == 1:
            query_resp = dev._last_update.get(self.QUERY_GETTER_NAME, {})
            if isinstance(query_resp, SmartErrorCode):
                raise DeviceError(
                    f"Error accessing module data in {self._module}",
                    error_code=query_resp,
                )

            if not query_resp:
                raise KasaException(
                    f"You need to call update() prior accessing module data"
                    f" for '{self._module}'"
                )

            # Some calls return the data under the module, others not
            return query_resp.get(self.QUERY_MODULE_NAME, query_resp)
        else:
            found = {key: val for key, val in dev._last_update.items() if key in q}
            for key in q:
                if key not in found:
                    raise KasaException(
                        f"{key} not found, you need to call update() prior accessing"
                        f" module data for '{self._module}'"
                    )
                if isinstance(found[key], SmartErrorCode):
                    raise DeviceError(
                        f"Error accessing module data {key} in {self._module}",
                        error_code=found[key],
                    )
            return found

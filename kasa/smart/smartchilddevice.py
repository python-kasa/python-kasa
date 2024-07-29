"""Child device implementation."""

from __future__ import annotations

import logging
import time
from typing import Any
from warnings import warn

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..smartprotocol import SmartProtocol, _ChildProtocolWrapper
from .smartdevice import SmartDevice

_LOGGER = logging.getLogger(__name__)


class SmartChildDevice(SmartDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    _parent: SmartDevice

    def __init__(
        self,
        parent: SmartDevice,
        info,
        component_info,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        super().__init__(parent.host, config=parent.config, protocol=parent.protocol)
        self._parent = parent
        self._update_internal_state(info)
        self._components = component_info
        self._id = info["device_id"]
        self.protocol = _ChildProtocolWrapper(self._id, parent.protocol)

    async def update(
        self,
        update_children_or_parent: bool = True,
        *,
        update_children: bool | None = None,
    ):
        """Update the device.

        Calling update directly on a child device will update the parent
        and only this child.
        """
        if update_children is not None:
            warn(
                "update_children is deprecated, use update_children_or_parent",
                DeprecationWarning,
                stacklevel=1,
            )
            update_children_or_parent = False

        if update_children_or_parent:
            await self._parent._update(called_from_child=self)
        else:
            await self._update()

    async def _update(self):
        """Update child module info.

        Internal implementation to allow patching of public update in the cli
        or test framework.
        """
        # Hubs attached devices only update via the parent hub
        if self._parent.device_type is DeviceType.Hub:
            return

        req: dict[str, Any] = {}
        for module in self.modules.values():
            if mod_query := module.query():
                req.update(mod_query)
        if req:
            self._last_update = await self.protocol.query(req)
            self._last_update_time = time.time()

    @classmethod
    async def create(cls, parent: SmartDevice, child_info, child_components):
        """Create a child device based on device info and component listing."""
        child: SmartChildDevice = cls(parent, child_info, child_components)
        await child._initialize_modules()
        return child

    @property
    def device_type(self) -> DeviceType:
        """Return child device type."""
        child_device_map = {
            "plug.powerstrip.sub-plug": DeviceType.Plug,
            "subg.trigger.contact-sensor": DeviceType.Sensor,
            "subg.trigger.temp-hmdt-sensor": DeviceType.Sensor,
            "subg.trigger.water-leak-sensor": DeviceType.Sensor,
            "kasa.switch.outlet.sub-fan": DeviceType.Fan,
            "kasa.switch.outlet.sub-dimmer": DeviceType.Dimmer,
            "subg.trv": DeviceType.Thermostat,
        }
        dev_type = child_device_map.get(self.sys_info["category"])
        if dev_type is None:
            _LOGGER.warning("Unknown child device type, please open issue ")
            dev_type = DeviceType.Unknown
        return dev_type

    def __repr__(self):
        return f"<{self.device_type} {self.alias} ({self.model}) of {self._parent}>"

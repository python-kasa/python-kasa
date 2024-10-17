"""Child device implementation."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..smartprotocol import SmartProtocol, _ChildProtocolWrapper
from .smartdevice import SmartDevice
from .smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class SmartChildDevice(SmartDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    CHILD_DEVICE_TYPE_MAP = {
        "plug.powerstrip.sub-plug": DeviceType.Plug,
        "subg.trigger.contact-sensor": DeviceType.Sensor,
        "subg.trigger.temp-hmdt-sensor": DeviceType.Sensor,
        "subg.trigger.water-leak-sensor": DeviceType.Sensor,
        "kasa.switch.outlet.sub-fan": DeviceType.Fan,
        "kasa.switch.outlet.sub-dimmer": DeviceType.Dimmer,
        "subg.trv": DeviceType.Thermostat,
        "subg.trigger.button": DeviceType.Sensor,
    }

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

    async def update(self, update_children: bool = True):
        """Update child module info.

        The parent updates our internal info so just update modules with
        their own queries.
        """
        await self._update(update_children)

    async def _update(self, update_children: bool = True):
        """Update child module info.

        Internal implementation to allow patching of public update in the cli
        or test framework.
        """
        now = time.monotonic()
        module_queries: list[SmartModule] = []
        req: dict[str, Any] = {}
        for module in self.modules.values():
            if module.disabled is False and (mod_query := module.query()):
                module_queries.append(module)
                req.update(mod_query)
        if req:
            self._last_update = await self.protocol.query(req)

        for module in self.modules.values():
            await self._handle_module_post_update(
                module, now, had_query=module in module_queries
            )
        self._last_update_time = now

    @classmethod
    async def create(cls, parent: SmartDevice, child_info, child_components):
        """Create a child device based on device info and component listing."""
        child: SmartChildDevice = cls(parent, child_info, child_components)
        await child._initialize_modules()
        return child

    @property
    def device_type(self) -> DeviceType:
        """Return child device type."""
        dev_type = self.CHILD_DEVICE_TYPE_MAP.get(self.sys_info["category"])
        if dev_type is None:
            _LOGGER.warning("Unknown child device type, please open issue ")
            dev_type = DeviceType.Unknown
        return dev_type

    def __repr__(self):
        return f"<{self.device_type} {self.alias} ({self.model}) of {self._parent}>"

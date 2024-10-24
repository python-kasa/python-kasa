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
        "subg.trigger.motion-sensor": DeviceType.Sensor,
        "kasa.switch.outlet.sub-fan": DeviceType.Fan,
        "kasa.switch.outlet.sub-dimmer": DeviceType.Dimmer,
        "subg.trv": DeviceType.Thermostat,
        "subg.trigger.button": DeviceType.Sensor,
    }

    def __init__(
        self,
        parent: SmartDevice,
        info: dict,
        component_info: dict,
        *,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        super().__init__(parent.host, config=parent.config, protocol=protocol)
        self._parent = parent
        self._update_internal_state(info)
        self._components = component_info
        self._id = info["device_id"]
        # wrap device protocol if no protocol is given
        self.protocol = protocol or _ChildProtocolWrapper(self._id, parent.protocol)

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
    async def create(
        cls,
        parent: SmartDevice,
        child_info: dict,
        child_components: dict,
        protocol: SmartProtocol | None = None,
        *,
        last_update: dict | None = None,
    ) -> SmartDevice:
        """Create a child device based on device info and component listing.

        If creating a smart child from a different protocol, i.e. a camera hub,
        protocol: SmartProtocol and last_update should be provided as per the
        FIRST_UPDATE_MODULES expected by the update cycle as these cannot be
        derived from the parent.
        """
        child: SmartChildDevice = cls(
            parent, child_info, child_components, protocol=protocol
        )
        if last_update:
            child._last_update = last_update
        await child._initialize_modules()
        return child

    @property
    def device_type(self) -> DeviceType:
        """Return child device type."""
        category = self.sys_info["category"]
        dev_type = self.CHILD_DEVICE_TYPE_MAP.get(category)
        if dev_type is None:
            _LOGGER.warning(
                "Unknown child device type %s for model %s, please open issue",
                category,
                self.model,
            )
            dev_type = DeviceType.Unknown
        return dev_type

    def __repr__(self):
        return f"<{self.device_type} {self.alias} ({self.model}) of {self._parent}>"

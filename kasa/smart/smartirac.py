"""Smart IR AC child device implementation."""

from __future__ import annotations

import logging
from typing import Any

from ..device_type import DeviceType
from .smartchilddevice import SmartChildDevice

_LOGGER = logging.getLogger(__name__)


class SmartIrAC(SmartChildDevice):
    """Presentation of a child IR Air Conditioner device."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._ac_state: dict[str, int] = {}
        super().__init__(*args, **kwargs)

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        try:
            return DeviceType.Climate
        except AttributeError:
            return DeviceType.Thermostat

    def _update_internal_state(self, info: dict[str, Any]) -> None:
        """Update the internal info state."""
        super()._update_internal_state(info)

        ac_status = info.get("ac_status")
        if ac_status:
            parts = ac_status.split("_")
            self._ac_state = {}
            for part in parts:
                if len(part) >= 2:
                    key = part[0]
                    try:
                        value = int(part[1:])
                        self._ac_state[key] = value
                    except ValueError:
                        pass

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        return bool(self._ac_state.get("P", 0))

    @property
    def target_temperature(self) -> int | None:
        """Return the target temperature."""
        return self._ac_state.get("T")

    @property
    def hvac_mode(self) -> int | None:
        """Return the hvac mode."""
        return self._ac_state.get("M")

    @property
    def fan_mode(self) -> int | None:
        """Return the fan mode."""
        return self._ac_state.get("S")

    @property
    def swing_mode(self) -> int | None:
        """Return the swing mode."""
        return self._ac_state.get("D")

    async def _send_ir_cmd(self, **kwargs) -> dict:
        """Send IR command to the AC."""
        payload = {
            "power": bool(self._ac_state.get("P", 0)),
            "on": bool(self._ac_state.get("P", 0)),
            "mode": self._ac_state.get("M", 1),
            "temp": self._ac_state.get("T", 24),
            "wind_speed": self._ac_state.get("S", 1),
            "wind_direct": self._ac_state.get("D", 0),
        }

        for key, value in kwargs.items():
            payload[key] = value
            if key == "power":
                payload["on"] = value

        request = {
            "multipleRequest": {
                "requests": [{"method": "sendIrCmdByStatus", "params": payload}]
            }
        }

        if "power" in payload:
            self._ac_state["P"] = 1 if payload["power"] else 0
        if "mode" in payload:
            self._ac_state["M"] = payload["mode"]
        if "temp" in payload:
            self._ac_state["T"] = payload["temp"]
        if "wind_speed" in payload:
            self._ac_state["S"] = payload["wind_speed"]
        if "wind_direct" in payload:
            self._ac_state["D"] = payload["wind_direct"]

        return await self.protocol.query(request)

    async def set_target_temperature(self, temp: int) -> dict:
        """Set the target temperature."""
        return await self._send_ir_cmd(temp=temp)

    async def set_hvac_mode(self, mode: int) -> dict:
        """Set the hvac mode."""
        return await self._send_ir_cmd(mode=mode)

    async def set_fan_mode(self, speed: int) -> dict:
        """Set the fan mode."""
        return await self._send_ir_cmd(wind_speed=speed)

    async def set_swing_mode(self, swing: int) -> dict:
        """Set the swing mode."""
        return await self._send_ir_cmd(wind_direct=swing)

    async def turn_on(self, **kwargs: Any) -> dict:
        """Turn on the AC."""
        return await self._send_ir_cmd(power=True)

    async def turn_off(self, **kwargs: Any) -> dict:
        """Turn off the AC."""
        return await self._send_ir_cmd(power=False)

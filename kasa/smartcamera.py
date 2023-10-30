"""Module for SmartCameras (EC70)."""
from typing import Any, Dict, Optional

from .credentials import Credentials
from .modules import PTZ, Cloud, Time
from .modules.ptz import Direction, Position
from .smartcameraprotocol import SmartCameraProtocol
from .smartdevice import DeviceType, SmartDevice, requires_update


class SmartCamera(SmartDevice):
    """Representation of a TP-Link Kasa Camera.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()`
    separately.

    Errors reported by the device are raised as
    :class:`SmartDeviceExceptions <kasa.exceptions.SmartDeviceException>`, and should be
    handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> camera = KasaCam("127.0.0.1")
        >>> asyncio.run(camera.update())
        >>> print(camera.alias)
        Camera2

        Cameras, like any other supported devices, can be turned on and off:

        >>> asyncio.run(camera.turn_off())
        >>> asyncio.run(camera.turn_on())
        >>> asyncio.run(camera.update())
        >>> print(camera.is_on)
        True
    """

    def __init__(
        self,
        host: str,
        credentials: Credentials,
        *,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._device_type = DeviceType.Camera
        self.protocol = SmartCameraProtocol(
            host, credentials=credentials, port=port, timeout=timeout
        )
        self.add_module("cloud", Cloud(self, "smartlife.cam.ipcamera.cloud"))
        self.add_module("ptz", PTZ(self, "smartlife.cam.ipcamera.ptz"))
        self.add_module("time", Time(self, "smartlife.cam.ipcamera.dateTime"))

    def _create_request(
        self,
        target: str,
        cmd: str,
        arg: Optional[Dict] = None,
        child_ids=None,
    ):
        # While most devices accept None for an empty arg, Kasa Cameras require {}
        # all other devices seem to accept this as well
        return {target: {cmd: {} if arg is None else arg}}

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether device is on."""
        return self.sys_info["camera_switch"] == "on"

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return camera-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        """
        return {
            "Position": self.position,
            "Patrolling": self.is_patrol_enabled,
        }

    @property
    @requires_update
    def position(self):
        """The camera's current x,y position."""
        return self.modules["ptz"].position

    @property
    @requires_update
    def is_patrol_enabled(self):
        """Whether patrol mode is currently enabled."""
        return self.modules["ptz"].is_patrol_enabled

    async def turn_on(self, **kwargs):
        """Turn the switch on."""
        return await self._query_helper(
            "smartlife.cam.ipcamera.switch", "set_is_enable", {"value": "on"}
        )

    async def turn_off(self, **kwargs):
        """Turn the switch off."""
        return await self._query_helper(
            "smartlife.cam.ipcamera.switch", "set_is_enable", {"value": "off"}
        )

    async def go_to(
        self,
        position: Optional[Position] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ):
        """Send the camera to an x,y position."""
        return await self.modules["ptz"].go_to(position=position, x=x, y=y)

    async def stop(self):
        """Stop the camera where it is."""
        return await self.modules["ptz"].stop()

    async def move(self, direction: Direction, speed: int):
        """Move the camera a relative direction at a given speed."""
        return await self.modules["ptz"].move(direction, speed)

    async def set_enable_patrol(self, enabled: bool):
        """Enable or disable Patrol mode."""
        return await self.modules["ptz"].set_enable_patrol(enabled)

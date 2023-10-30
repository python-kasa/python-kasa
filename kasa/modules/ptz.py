"""Pan/Tilt/Zoom Module."""
from .module import Module, merge

try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel

from typing import Literal, Optional

from ..exceptions import SmartDeviceException


class Position(BaseModel):
    """Camera Position Schema."""

    x: int
    y: int


Direction = Literal["up", "down", "left", "right"]


class PTZ(Module):
    """Module implementing support for pan/tilt/zoom cameras."""

    def query(self):
        """Request PTZ info."""
        q = self.query_for_command("get_position")
        merge(q, self.query_for_command("get_patrol_is_enable"))
        return q

    @property
    def position(self) -> Position:
        """Return the camera's position coordinates."""
        return Position.parse_obj(self.data["get_position"])

    @property
    def is_patrol_enabled(self) -> bool:
        """Whether or not the camera is patrolling."""
        return self.data["get_patrol_is_enable"]["value"] == "on"

    async def set_enable_patrol(self, enabled: bool):
        """Enable or disable camera patrolling."""
        return await self.call(
            "set_patrol_is_enable", {"value": "on" if enabled else "off"}
        )

    async def go_to(
        self,
        position: Optional[Position] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ):
        """Move the camera to the given Position's x,y coordinates."""
        if position is None and x is not None and y is not None:
            position = Position(x=x, y=y)
        if not position:
            raise SmartDeviceException(
                "Either a Position object or both x and y are required."
            )
        return await self.call("set_move", {"x": position.x, "y": position.y})

    async def stop(self):
        """Stop the camera where it is."""
        return await self.call("set_stop")

    async def move(self, direction: Direction, speed: int):
        """Move the camera in a relative direction."""
        return await self.call("set_target", {"direction": direction, "speed": speed})

    # async def add_preset(self):
    #     # public String api_srv_url;
    #     # public Integer index;
    #     # public String name;
    #     # public String path;
    #     # public Integer wait_time;
    #     pass

    # async def delete_preset(self, index: int):
    #     pass

    # async def edit_preset(self, index: int, name: str, wait_time: int):
    #     pass

    # async def get_all_preset(self):
    #     # public Integer maximum;
    #     # public List preset_attr;
    #     pass

    # async def get_patrol_is_enable(self):
    #     pass

    # async def get_position(self):
    #     # public Integer x;
    #     # public Integer y;
    #     pass

    # async def get_ptz_rectify_state(self):
    #     pass

    # async def get_ptz_tracking_is_enable(self):
    #     pass

    # async def set_motor_rectify(self):
    #     pass

    # async def set_move(self, x: int, y: int):
    #     pass

    # async def set_patrol_is_enable(self):
    #     pass

    # async def set_ptz_tracking_is_enable(self):
    #     pass

    # async def set_run_to_preset(self, index: int):
    #     pass

    # async def set_stop(self):
    #     pass

    # async def set_target(self, direction: str, speed: int):
    #     pass

"""Implementation of the ambient light (LAS) module found in some dimmers."""

from ...feature import Feature
from ..iotmodule import IotModule, merge

# TODO create tests and use the config reply there
# [{"hw_id":0,"enable":0,"dark_index":1,"min_adc":0,"max_adc":2450,
# "level_array":[{"name":"cloudy","adc":490,"value":20},
# {"name":"overcast","adc":294,"value":12},
# {"name":"dawn","adc":222,"value":9},
# {"name":"twilight","adc":222,"value":9},
# {"name":"total darkness","adc":111,"value":4},
# {"name":"custom","adc":2400,"value":97}]}]


class AmbientLight(IotModule):
    """Implements ambient light controls for the motion sensor."""

    def __init__(self, device, module):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device=device,
                container=self,
                id="ambient_light",
                name="Ambient Light",
                icon="mdi:brightness-percent",
                attribute_getter="ambientlight_brightness",
                type=Feature.Type.Sensor,
                category=Feature.Category.Primary,
                unit="%",
            )
        )

    def query(self):
        """Request configuration."""
        req = merge(
            self.query_for_command("get_config"),
            self.query_for_command("get_current_brt"),
        )

        return req

    @property
    def presets(self) -> dict:
        """Return device-defined presets for brightness setting."""
        return self.data["level_array"]

    @property
    def enabled(self) -> bool:
        """Return True if the module is enabled."""
        return bool(self.data["enable"])

    @property
    def ambientlight_brightness(self) -> int:
        """Return True if the module is enabled."""
        return int(self.data["get_current_brt"]["value"])

    async def set_enabled(self, state: bool):
        """Enable/disable LAS."""
        return await self.call("set_enable", {"enable": int(state)})

    async def current_brightness(self) -> int:
        """Return current brightness.

        Return value units.
        """
        return await self.call("get_current_brt")

    async def set_brightness_limit(self, value: int):
        """Set the limit when the motion sensor is inactive.

        See `presets` for preset values. Custom values are also likely allowed.
        """
        return await self.call("set_brt_level", {"index": 0, "value": value})

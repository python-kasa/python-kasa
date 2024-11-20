"""Implementation of the ambient light (LAS) module found in some dimmers."""

import logging

from ...feature import Feature
from ..iotmodule import IotModule, merge

_LOGGER = logging.getLogger(__name__)


class AmbientLight(IotModule):
    """Implements ambient light controls for the motion sensor."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="ambient_light_enabled",
                name="Ambient light enabled",
                icon="mdi:brightness-percent",
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="ambient_light",
                name="Ambient Light",
                icon="mdi:brightness-percent",
                attribute_getter="ambientlight_brightness",
                type=Feature.Type.Sensor,
                category=Feature.Category.Primary,
                unit_getter=lambda: "%",
            )
        )

    def query(self) -> dict:
        """Request configuration."""
        req = merge(
            self.query_for_command("get_config"),
            self.query_for_command("get_current_brt"),
        )

        return req

    @property
    def config(self) -> dict:
        """Return current ambient light config."""
        config = self.data["get_config"]
        devs = config["devs"]
        if len(devs) != 1:
            _LOGGER.error("Unexpected number of devs in config: %s", config)

        return devs[0]

    @property
    def presets(self) -> dict:
        """Return device-defined presets for brightness setting."""
        return self.config["level_array"]

    @property
    def enabled(self) -> bool:
        """Return True if the module is enabled."""
        return bool(self.config["enable"])

    @property
    def ambientlight_brightness(self) -> int:
        """Return True if the module is enabled."""
        return int(self.data["get_current_brt"]["value"])

    async def set_enabled(self, state: bool) -> dict:
        """Enable/disable LAS."""
        return await self.call("set_enable", {"enable": int(state)})

    async def current_brightness(self) -> dict:
        """Return current brightness.

        Return value units.
        """
        return await self.call("get_current_brt")

    async def set_brightness_limit(self, value: int) -> dict:
        """Set the limit when the motion sensor is inactive.

        See `presets` for preset values. Custom values are also likely allowed.
        """
        return await self.call("set_brt_level", {"index": 0, "value": value})

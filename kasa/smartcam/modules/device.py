"""Implementation of device module."""

from __future__ import annotations

from ...feature import Feature
from ..smartcammodule import SmartCamModule


class DeviceModule(SmartCamModule):
    """Implementation of device module."""

    NAME = "devicemodule"
    QUERY_GETTER_NAME = "getDeviceInfo"
    QUERY_MODULE_NAME = "device_info"
    QUERY_SECTION_NAMES = ["basic_info", "info"]

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        if self._device.parent is None:
            q["getConnectionType"] = {"network": {"get_connection_type": []}}

        return q

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="device_id",
                name="Device ID",
                attribute_getter="device_id",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        if self.rssi is not None:
            self._add_feature(
                Feature(
                    self._device,
                    container=self,
                    id="rssi",
                    name="RSSI",
                    attribute_getter="rssi",
                    icon="mdi:signal",
                    unit_getter=lambda: "dBm",
                    category=Feature.Category.Debug,
                    type=Feature.Type.Sensor,
                )
            )
            self._add_feature(
                Feature(
                    self._device,
                    container=self,
                    id="signal_level",
                    name="Signal Level",
                    attribute_getter="signal_level",
                    icon="mdi:signal",
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )

    async def _post_update_hook(self) -> None:
        """Overriden to prevent module disabling.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return self._device._info["device_id"]

    @property
    def rssi(self) -> int | None:
        """Return the device id."""
        return self.data.get("getConnectionType", {}).get("rssiValue")

    @property
    def signal_level(self) -> int | None:
        """Return the device id."""
        return self.data.get("getConnectionType", {}).get("rssi")

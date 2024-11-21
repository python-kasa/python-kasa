"""Implementation of device module."""

from __future__ import annotations

import base64
import logging
from urllib.parse import quote_plus

from ...credentials import Credentials
from ...device_type import DeviceType
from ...feature import Feature
from ...json import loads as json_loads
from ..smartcameramodule import SmartCameraModule

_LOGGER = logging.getLogger(__name__)

LOCAL_STREAMING_PORT = 554


class Camera(SmartCameraModule):
    """Implementation of device module."""

    QUERY_GETTER_NAME = "getLensMaskConfig"
    QUERY_MODULE_NAME = "lens_mask"
    QUERY_SECTION_NAMES = "lens_mask_info"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="state",
                name="State",
                attribute_getter="is_on",
                attribute_setter="set_state",
                type=Feature.Type.Switch,
                category=Feature.Category.Primary,
            )
        )

    @property
    def is_on(self) -> bool:
        """Return the device id."""
        return self.data["lens_mask_info"]["enabled"] == "off"

    def _get_credentials(self) -> Credentials | None:
        """Get credentials from ."""
        config = self._device.config
        if credentials := config.credentials:
            return credentials

        if credentials_hash := config.credentials_hash:
            try:
                decoded = json_loads(
                    base64.b64decode(credentials_hash.encode()).decode()
                )
            except Exception:
                _LOGGER.warning(
                    "Unable to deserialize credentials_hash: %s", credentials_hash
                )
                return None
            if (username := decoded.get("un")) and (password := decoded.get("pwd")):
                return Credentials(username, password)

        return None

    def stream_rtsp_url(self, credentials: Credentials | None = None) -> str | None:
        """Return the local rtsp streaming url.

        :param credentials: Credentials for camera account.
            These could be different credentials to tplink cloud credentials.
            If not provided will use tplink credentials if available
        :return: rtsp url with escaped credentials or None if no credentials or
            camera is off.
        """
        if not self.is_on:
            return None
        dev = self._device
        if not credentials:
            credentials = self._get_credentials()

        if not credentials or not credentials.username or not credentials.password:
            return None
        username = quote_plus(credentials.username)
        password = quote_plus(credentials.password)
        return f"rtsp://{username}:{password}@{dev.host}:{LOCAL_STREAMING_PORT}/stream1"

    async def set_state(self, on: bool) -> dict:
        """Set the device state."""
        # Turning off enables the privacy mask which is why value is reversed.
        params = {"enabled": "off" if on else "on"}
        return await self._device._query_setter_helper(
            "setLensMaskConfig", self.QUERY_MODULE_NAME, "lens_mask_info", params
        )

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return self._device.device_type is DeviceType.Camera

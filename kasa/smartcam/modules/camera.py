"""Implementation of camera module."""

from __future__ import annotations

import base64
import logging
from enum import StrEnum
from typing import Annotated
from urllib.parse import quote_plus

from ...credentials import Credentials
from ...feature import Feature
from ...json import loads as json_loads
from ...module import FeatureAttribute, Module
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)

LOCAL_STREAMING_PORT = 554
ONVIF_PORT = 2020


class StreamResolution(StrEnum):
    """Class for stream resolution."""

    HD = "HD"
    SD = "SD"


class Camera(SmartCamModule):
    """Implementation of device module."""

    REQUIRED_COMPONENT = "video"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        if Module.LensMask in self._device.modules:
            self._add_feature(
                Feature(
                    self._device,
                    id="state",
                    name="State",
                    container=self,
                    attribute_getter="is_on",
                    attribute_setter="set_state",
                    type=Feature.Type.Switch,
                    category=Feature.Category.Primary,
                )
            )

    @property
    def is_on(self) -> bool:
        """Return the device on state."""
        if lens_mask := self._device.modules.get(Module.LensMask):
            return not lens_mask.enabled
        return True

    async def set_state(self, on: bool) -> Annotated[dict, FeatureAttribute()]:
        """Set the device on state.

        If the device does not support setting state will do nothing.
        """
        if lens_mask := self._device.modules.get(Module.LensMask):
            # Turning off enables the privacy mask which is why value is reversed.
            return await lens_mask.set_enabled(not on)
        return {}

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

    def stream_rtsp_url(
        self,
        credentials: Credentials | None = None,
        *,
        stream_resolution: StreamResolution = StreamResolution.HD,
    ) -> str | None:
        """Return the local rtsp streaming url.

        :param credentials: Credentials for camera account.
            These could be different credentials to tplink cloud credentials.
            If not provided will use tplink credentials if available
        :return: rtsp url with escaped credentials or None if no credentials or
            camera is off.
        """
        if self._device._is_hub_child:
            return None

        streams = {
            StreamResolution.HD: "stream1",
            StreamResolution.SD: "stream2",
        }
        if (stream := streams.get(stream_resolution)) is None:
            return None

        if not credentials:
            credentials = self._get_credentials()

        if not credentials or not credentials.username or not credentials.password:
            return None

        username = quote_plus(credentials.username)
        password = quote_plus(credentials.password)

        return f"rtsp://{username}:{password}@{self._device.host}:{LOCAL_STREAMING_PORT}/{stream}"

    def onvif_url(self) -> str | None:
        """Return the onvif url."""
        if self._device._is_hub_child:
            return None

        return f"http://{self._device.host}:{ONVIF_PORT}/onvif/device_service"

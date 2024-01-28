"""Module for Device base class."""
import logging
from typing import Optional

from .deviceconfig import DeviceConfig

_LOGGER = logging.getLogger(__name__)


class Device:
    """Placeholder for interface or base class."""

    @staticmethod
    async def connect(
        *,
        host: Optional[str] = None,
        config: Optional[DeviceConfig] = None,
    ) -> "Device":
        """Connect to a single device by the given hostname or device configuration.

        This method avoids the UDP based discovery process and
        will connect directly to the device.

        It is generally preferred to avoid :func:`discover_single()` and
        use this function instead as it should perform better when
        the WiFi network is congested or the device is not responding
        to discovery requests.

        :param host: Hostname of device to query
        :param config: Connection parameters to ensure the correct protocol
            and connection options are used.
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        from .device_factory import connect  # pylint: disable=import-outside-toplevel

        return await connect(host=host, config=config)  # type: ignore[arg-type]

"""Implementation of the emeter module."""
from ..emeterstatus import EmeterStatus
from .usage import Usage


class Emeter(Usage):
    """Emeter module."""

    def query(self):
        """Prepare query for emeter data."""
        return self._device._create_emeter_request()

    @property  # type: ignore
    def realtime(self) -> EmeterStatus:
        """Return current energy readings."""
        return EmeterStatus(self.data["get_realtime"])

    async def erase_stats(self):
        """Erase all stats."""
        return await self.call("erase_emeter_stat")

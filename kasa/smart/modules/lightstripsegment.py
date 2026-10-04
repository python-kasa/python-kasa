"""Implementation of the light strip segment module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule

# The device reports no maximum, so it cannot be queried: a run is 5m in 10cm
# segments. Multi-spool products drive every run from this one value, making
# the limit per-run rather than per-model.
SEGMENTS_MIN = 0
SEGMENTS_MAX = 50


class LightStripSegment(SmartModule):
    """Implementation of the configurable light strip length."""

    REQUIRED_COMPONENT = "segment"
    QUERY_GETTER_NAME = "get_device_segment"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="strip_segments",
                name="Strip segments",
                container=self,
                attribute_getter="segments",
                attribute_setter="set_segments",
                range_getter=lambda: (SEGMENTS_MIN, SEGMENTS_MAX),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

    @property
    def segments(self) -> int:
        """Return the number of 10cm segments the strip is configured for."""
        return self.data["segment"]

    async def set_segments(self, segments: int) -> dict:
        """Set the number of 10cm segments the strip is cut to."""
        if not isinstance(segments, int) or not (
            SEGMENTS_MIN <= segments <= SEGMENTS_MAX
        ):
            raise ValueError(
                f"Invalid segment count: {segments} "
                f"(valid range: {SEGMENTS_MIN}-{SEGMENTS_MAX})"
            )

        return await self.call("set_device_segment", {"segment": segments})

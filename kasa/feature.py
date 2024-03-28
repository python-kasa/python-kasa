"""Generic interface for defining device features."""
import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    TypedDict,
    Union,
)

if sys.version_info < (3, 10):
    from typing_extensions import Unpack
else:
    from typing import Unpack

if TYPE_CHECKING:
    from .device import Device


class FeatureType(Enum):
    """Type to help decide how to present the feature."""

    Sensor = auto()
    BinarySensor = auto()
    Switch = auto()
    Button = auto()
    Number = auto()


@dataclass
class Feature:
    """Feature defines a generic interface for device features."""

    #: Device instance required for getting and setting values
    device: "Device"
    #: User-friendly short description
    name: str
    #: Name of the property that allows accessing the value
    attribute_getter: Union[str, Callable]
    #: Name of the method that allows changing the value
    attribute_setter: Optional[str] = None
    #: Container storing the data, this overrides 'device' for getters
    container: Any = None
    #: Icon suggestion
    icon: Optional[str] = None
    #: Type of the feature
    type: FeatureType = FeatureType.Sensor

    # Number-specific attributes
    #: Minimum value
    minimum_value: int = 0
    #: Maximum value
    maximum_value: int = 2**16  # Arbitrary max
    #: Attribute containing the name of the range getter property.
    #: If set, this property will be used to set *minimum_value* and *maximum_value*.
    range_getter: Optional[str] = None

    def __post_init__(self):
        """Handle late-binding of members."""
        container = self.container if self.container is not None else self.device
        if self.range_getter is not None:
            self.minimum_value, self.maximum_value = getattr(
                container, self.range_getter
            )

    @property
    def value(self):
        """Return the current value."""
        container = self.container if self.container is not None else self.device
        if isinstance(self.attribute_getter, Callable):
            return self.attribute_getter(container)
        return getattr(container, self.attribute_getter)

    async def set_value(self, value):
        """Set the value."""
        if self.attribute_setter is None:
            raise ValueError("Tried to set read-only feature.")
        if self.type == FeatureType.Number:  # noqa: SIM102
            if value < self.minimum_value or value > self.maximum_value:
                raise ValueError(
                    f"Value {value} out of range "
                    f"[{self.minimum_value}, {self.maximum_value}]"
                )

        container = self.container if self.container is not None else self.device
        if isinstance(self.attribute_setter, Callable):
            return await self.attribute_setter(value)
        return await getattr(container, self.attribute_setter)(value)


class FeatureNames:
    """Class for feature names."""

    BRIGHTNESS = "Brightness"
    RSSI = "RSSI"
    STATE = "State"


class FeatureKwargs(TypedDict, total=False):
    """Type class for feature kwargs."""

    attribute_setter: str
    container: Any
    icon: str
    type: FeatureType
    minimum_value: int
    maximum_value: int


class StandardFeature:
    """Factory class for standard features."""

    @staticmethod
    def brightness(
        device,
        container=None,
        name=FeatureNames.BRIGHTNESS,
        icon=None,
        attribute_getter="brightness",
        attribute_setter="set_brightness",
        minimum_value=1,
        maximum_value=100,
        type=FeatureType.Number,
    ) -> "Feature":
        """Brightness feature."""
        return Feature(
            device=device,
            container=container,
            name=name,
            icon=icon,
            attribute_getter=attribute_getter,
            attribute_setter=attribute_setter,
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            type=type,
        )

    @staticmethod
    def rssi(
        device: "Device",
        attribute_getter: Union[str, Callable],
        name: str = FeatureNames.RSSI,
        **kwargs: Unpack[FeatureKwargs],
    ) -> Feature:
        """RSSI feature."""
        kwargs.setdefault("icon", "mdi:signal")
        return Feature(device, name, attribute_getter, **kwargs)

    @staticmethod
    def state(
        device: "Device",
        attribute_getter: Union[str, Callable],
        name: str = FeatureNames.STATE,
        **kwargs: Unpack[FeatureKwargs],
    ) -> Feature:
        """State feature."""
        kwargs.setdefault("type", FeatureType.Switch)
        return Feature(device, name, attribute_getter, **kwargs)

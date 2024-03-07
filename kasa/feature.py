"""Generic interface for defining device features."""
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

if TYPE_CHECKING:
    from .device import Device


class FeatureType(Enum):
    """Type to help decide how to present the feature."""

    Sensor = auto()
    BinarySensor = auto()
    Switch = auto()
    Button = auto()
    Number = auto()


class MetaFeature(type):
    """Class for feature names."""

    state = "State"
    rssi = "RSSI"
    brightness = "Brightness"


@dataclass
class Feature(metaclass=MetaFeature):
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

    @staticmethod
    def _brightness(device, container=None) -> "Feature":
        return Feature(
            device=device,
            container=container,
            name=Feature.brightness,
            attribute_getter="brightness",
            attribute_setter="set_brightness",
            minimum_value=1,
            maximum_value=100,
            type=FeatureType.Number,
        )

    @staticmethod
    def _rssi(device, attribute_getter) -> "Feature":
        return Feature(
            device,
            Feature.rssi,
            attribute_getter=attribute_getter,
            icon="mdi:signal",
        )

    @staticmethod
    def _state(device, attribute_getter, attribute_setter) -> "Feature":
        return Feature(
            device,
            Feature.state,
            attribute_getter=attribute_getter,
            attribute_setter=attribute_setter,
            type=FeatureType.Switch,
        )

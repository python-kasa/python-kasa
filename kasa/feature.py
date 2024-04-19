"""Generic interface for defining device features."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .device import Device


# TODO: This is only useful for Feature, so maybe move to Feature.Type?
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

    class Category(Enum):
        """Category hint for downstreams."""

        #: Primary features control the device state directly.
        #: Examples including turning the device on, or adjust its brightness.
        Primary = auto()
        #: Config features change device behavior without immediate state changes.
        Config = auto()
        #: Informative/sensor features deliver some potentially interesting information.
        Info = auto()
        #: Debug features deliver more verbose information then informative features.
        #: You may want to hide these per default to avoid cluttering your UI.
        Debug = auto()
        #: The default category if none is specified.
        Unset = -1

    #: Device instance required for getting and setting values
    device: Device
    #: User-friendly short description
    name: str
    #: Name of the property that allows accessing the value
    attribute_getter: str | Callable
    #: Name of the method that allows changing the value
    attribute_setter: str | None = None
    #: Container storing the data, this overrides 'device' for getters
    container: Any = None
    #: Icon suggestion
    icon: str | None = None
    #: Unit, if applicable
    unit: str | None = None
    #: Category hint for downstreams
    category: Feature.Category = Category.Unset
    #: Type of the feature
    type: FeatureType = FeatureType.Sensor

    # Number-specific attributes
    #: Minimum value
    minimum_value: int = 0
    #: Maximum value
    maximum_value: int = 2**16  # Arbitrary max
    #: Attribute containing the name of the range getter property.
    #: If set, this property will be used to set *minimum_value* and *maximum_value*.
    range_getter: str | None = None

    def __post_init__(self):
        """Handle late-binding of members."""
        container = self.container if self.container is not None else self.device
        if self.range_getter is not None:
            self.minimum_value, self.maximum_value = getattr(
                container, self.range_getter
            )
        if self.category is Feature.Category.Unset:
            if self.attribute_setter:
                self.category = Feature.Category.Config
            else:
                self.category = Feature.Category.Info

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
        return await getattr(container, self.attribute_setter)(value)

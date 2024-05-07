"""Generic interface for defining device features."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .device import Device


_LOGGER = logging.getLogger(__name__)


@dataclass
class Feature:
    """Feature defines a generic interface for device features."""

    class Type(Enum):
        """Type to help decide how to present the feature."""

        #: Sensor is an informative read-only value
        Sensor = auto()
        #: BinarySensor is a read-only boolean
        BinarySensor = auto()
        #: Switch is a boolean setting
        Switch = auto()
        #: Action triggers some action on device
        Action = auto()
        #: Number defines a numeric setting
        #: See :ref:`range_getter`, :ref:`minimum_value`, and :ref:`maximum_value`
        Number = auto()
        #: Choice defines a setting with pre-defined values
        Choice = auto()
        Unknown = -1

    # TODO: unsure if this is a great idea..
    Sensor = Type.Sensor
    BinarySensor = Type.BinarySensor
    Switch = Type.Switch
    Action = Type.Action
    Number = Type.Number
    Choice = Type.Choice

    class Category(Enum):
        """Category hint to allow feature grouping."""

        #: Primary features control the device state directly.
        #: Examples include turning the device on/off, or adjusting its brightness.
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
    #: Identifier
    id: str
    #: User-friendly short description
    name: str
    #: Name of the property that allows accessing the value
    attribute_getter: str | Callable | None = None
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
    type: Feature.Type = Type.Sensor

    # Display hints offer a way suggest how the value should be shown to users
    #: Hint to help rounding the sensor values to given after-comma digits
    precision_hint: int | None = None

    # Number-specific attributes
    #: Minimum value
    minimum_value: int = 0
    #: Maximum value
    maximum_value: int = 2**16  # Arbitrary max
    #: Attribute containing the name of the range getter property.
    #: If set, this property will be used to set *minimum_value* and *maximum_value*.
    range_getter: str | None = None

    # Choice-specific attributes
    #: List of choices as enum
    choices: list[str] | None = None
    #: Attribute name of the choices getter property.
    #: If set, this property will be used to set *choices*.
    choices_getter: str | None = None

    def __post_init__(self):
        """Handle late-binding of members."""
        # Populate minimum & maximum values, if range_getter is given
        container = self.container if self.container is not None else self.device
        if self.range_getter is not None:
            self.minimum_value, self.maximum_value = getattr(
                container, self.range_getter
            )

        # Populate choices, if choices_getter is given
        if self.choices_getter is not None:
            self.choices = getattr(container, self.choices_getter)

        # Set the category, if unset
        if self.category is Feature.Category.Unset:
            if self.attribute_setter:
                self.category = Feature.Category.Config
            else:
                self.category = Feature.Category.Info

        if self.category == Feature.Category.Config and self.type in [
            Feature.Type.Sensor,
            Feature.Type.BinarySensor,
        ]:
            raise ValueError(
                f"Invalid type for configurable feature: {self.name} ({self.id}):"
                f" {self.type}"
            )

    @property
    def value(self):
        """Return the current value."""
        if self.type == Feature.Type.Action:
            return "<Action>"
        if self.attribute_getter is None:
            raise ValueError("Not an action and no attribute_getter set")

        container = self.container if self.container is not None else self.device
        if isinstance(self.attribute_getter, Callable):
            return self.attribute_getter(container)
        return getattr(container, self.attribute_getter)

    async def set_value(self, value):
        """Set the value."""
        if self.attribute_setter is None:
            raise ValueError("Tried to set read-only feature.")
        if self.type == Feature.Type.Number:  # noqa: SIM102
            if value < self.minimum_value or value > self.maximum_value:
                raise ValueError(
                    f"Value {value} out of range "
                    f"[{self.minimum_value}, {self.maximum_value}]"
                )
        elif self.type == Feature.Type.Choice:  # noqa: SIM102
            if value not in self.choices:
                raise ValueError(
                    f"Unexpected value for {self.name}: {value}"
                    f" - allowed: {self.choices}"
                )

        container = self.container if self.container is not None else self.device
        if self.type == Feature.Type.Action:
            return await getattr(container, self.attribute_setter)()

        return await getattr(container, self.attribute_setter)(value)

    def __repr__(self):
        try:
            value = self.value
            choices = self.choices
        except Exception as ex:
            return f"Unable to read value ({self.id}): {ex}"

        if self.type == Feature.Type.Choice:
            if not isinstance(choices, list) or value not in choices:
                _LOGGER.warning(
                    "Invalid value for for choice %s (%s): %s not in %s",
                    self.name,
                    self.id,
                    value,
                    choices,
                )
                return (
                    f"{self.name} ({self.id}): invalid value '{value}' not in {choices}"
                )
            value = " ".join(
                [f"*{choice}*" if choice == value else choice for choice in choices]
            )
        if self.precision_hint is not None and value is not None:
            value = round(self.value, self.precision_hint)

        s = f"{self.name} ({self.id}): {value}"
        if self.unit is not None:
            s += f" {self.unit}"

        if self.type == Feature.Type.Number:
            s += f" (range: {self.minimum_value}-{self.maximum_value})"

        return s

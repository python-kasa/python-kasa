"""Typing stub file for ModuleMapping."""

from abc import ABCMeta
from collections.abc import Mapping
from typing import Generic, TypeVar, overload

from .module import Module

__all__ = [
    "ModuleMapping",
    "ModuleName",
]

_ModuleT = TypeVar("_ModuleT", bound=Module, covariant=True)
_ModuleBaseT = TypeVar("_ModuleBaseT", bound=Module, covariant=True)

class ModuleName(Generic[_ModuleT]):
    """Class for typed Module names. At runtime delegated to str."""

    def __init__(self, value: str, /) -> None: ...
    def __len__(self) -> int: ...
    def __hash__(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...
    def __getitem__(self, index: int) -> str: ...

class ModuleMapping(
    Mapping[ModuleName[_ModuleBaseT] | str, _ModuleBaseT], metaclass=ABCMeta
):
    """Custom dict type to provide better value type hints for Module key types."""

    @overload
    def __getitem__(self, key: ModuleName[_ModuleT], /) -> _ModuleT: ...
    @overload
    def __getitem__(self, key: str, /) -> _ModuleBaseT: ...
    @overload
    def __getitem__(
        self, key: ModuleName[_ModuleT] | str, /
    ) -> _ModuleT | _ModuleBaseT: ...
    @overload  # type: ignore[override]
    def get(self, key: ModuleName[_ModuleT], /) -> _ModuleT | None: ...
    @overload
    def get(self, key: str, /) -> _ModuleBaseT | None: ...
    @overload
    def get(
        self, key: ModuleName[_ModuleT] | str, /
    ) -> _ModuleT | _ModuleBaseT | None: ...

def _test_module_mapping_typing() -> None:
    """Test ModuleMapping overloads work as intended.

    This is tested during the mypy run and needs to be in this file.
    """
    from typing import Any, NewType, cast

    from typing_extensions import assert_type

    from .iot.iotmodule import IotModule
    from .module import Module
    from .smart.smartmodule import SmartModule

    NewCommonModule = NewType("NewCommonModule", Module)
    NewIotModule = NewType("NewIotModule", IotModule)
    NewSmartModule = NewType("NewSmartModule", SmartModule)
    NotModule = NewType("NotModule", list)

    NEW_COMMON_MODULE: ModuleName[NewCommonModule] = ModuleName("NewCommonModule")
    NEW_IOT_MODULE: ModuleName[NewIotModule] = ModuleName("NewIotModule")
    NEW_SMART_MODULE: ModuleName[NewSmartModule] = ModuleName("NewSmartModule")

    # TODO Enable --warn-unused-ignores
    NOT_MODULE: ModuleName[NotModule] = ModuleName("NotModule")  # type: ignore[type-var]  # noqa: F841
    NOT_MODULE_2 = ModuleName[NotModule]("NotModule2")  # type: ignore[type-var]  # noqa: F841

    device_modules: ModuleMapping[Module] = cast(ModuleMapping[Module], {})
    assert_type(device_modules[NEW_COMMON_MODULE], NewCommonModule)
    assert_type(device_modules[NEW_IOT_MODULE], NewIotModule)
    assert_type(device_modules[NEW_SMART_MODULE], NewSmartModule)
    assert_type(device_modules["foobar"], Module)
    assert_type(device_modules[3], Any)  # type: ignore[call-overload]

    assert_type(device_modules.get(NEW_COMMON_MODULE), NewCommonModule | None)
    assert_type(device_modules.get(NEW_IOT_MODULE), NewIotModule | None)
    assert_type(device_modules.get(NEW_SMART_MODULE), NewSmartModule | None)
    assert_type(device_modules.get(NEW_COMMON_MODULE, default=[1, 2]), Any)  # type: ignore[call-overload]

    iot_modules: ModuleMapping[IotModule] = cast(ModuleMapping[IotModule], {})
    smart_modules: ModuleMapping[SmartModule] = cast(ModuleMapping[SmartModule], {})

    assert_type(smart_modules["foobar"], SmartModule)
    assert_type(iot_modules["foobar"], IotModule)

    # Test for covariance
    device_modules_2: ModuleMapping[Module] = iot_modules  # noqa: F841
    device_modules_3: ModuleMapping[Module] = smart_modules  # noqa: F841
    NEW_MODULE: ModuleName[Module] = NEW_SMART_MODULE  # noqa: F841
    NEW_MODULE_2: ModuleName[Module] = NEW_IOT_MODULE  # noqa: F841

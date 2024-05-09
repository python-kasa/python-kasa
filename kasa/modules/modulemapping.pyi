"""Typing stub file for ModuleMapping."""

from abc import ABCMeta
from collections.abc import Mapping
from typing import Generic, TypeVar, overload

from ..module import Module

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
